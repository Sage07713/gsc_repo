"""
Sentinel AI — Main Pipeline (v3)
==================================
All changes vs previous version:

  FIX-1  cv2.VideoCapture("PI_STREAM_URL") passed the string literal.
          Changed to cv2.VideoCapture(config["pi_stream_url"]) from config.json.
  FIX-2  All hardcoded values replaced with _load_config("config.json").
  FIX-3  _merge_frames blend changed 0.5/0.5 → 0.65/0.35 (YOLO fire boxes
          stay bright, not dimmed to 50%).
  FIX-4  pose_engine.tick(elapsed_sec) called every frame with real wall-clock
          delta. Without this, the rolling FPS in predict_pose.py never updates
          and sustained_lying_seconds stays wrong on throttled hardware.
  FIX-5  motion_engine.update_fps() called every frame — keeps still-person
          threshold accurate at actual stream FPS (Pi may run at 3–5 FPS).
  FIX-6  True zero-cost detection injection:
          pose engine saves last_raw_boxes after its YOLO pass.
          main.py extracts them and injects into motion_engine via
          inject_detections() BEFORE motion analyze() runs.
          This eliminates the redundant second YOLO inference call that was
          halving FPS on CPU. Old comment claiming "ultralytics caches results"
          was incorrect — every model.predict() runs full inference.
  FIX-7  Smart alert dispatch: immediate on state change, throttled during
          ongoing threats, heartbeat during normal. Replaces flat 2s cooldown.
  FIX-8  Auto-reconnect WebSocket — on send failure, connection is dropped and
          re-attempted on next dispatch cycle.
  FIX-9  base64 encoding: buffer.tobytes() called explicitly to prevent
          TypeErrors when base64 receives a numpy memoryview.
"""

import cv2
import asyncio
import json
import time
import numpy as np
import base64
import websockets
import os
import pika

from concurrent.futures import ThreadPoolExecutor
_EXECUTOR = ThreadPoolExecutor(max_workers=2)

async def _encode_frame_async(frame: np.ndarray, quality: int) -> str:
    loop = asyncio.get_running_loop()
    def _encode():
        ret, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return base64.b64encode(buf.tobytes()).decode("utf-8") if ret else ""
    return await loop.run_in_executor(_EXECUTOR, _encode)

from inference.predict_vision import VisionAnalyzer
from inference.predict_pose   import PoseAnalyzer
from fusion.fusion_logic      import ThreatFusionEngine
from inference.predict_motion import MotionAnalyzer

try:
    import supervision as sv
    _SV_AVAILABLE = True
except ImportError:
    _SV_AVAILABLE = False


# ── Config loader ──────────────────────────────────────────────────────────────
def _load_config(path: str = "config.json") -> dict:
    defaults = {
            "pi_stream_url":    "http://192.168.1.100:5000/video_feed",
            "go_backend_url":   "ws://localhost:3000/ws/stream",
            "compute_device":   "cpu", 
            "vision_weights":   "ml_consumer/weights/best.pt",
            "pose_weights":     "weights/yolo11s-pose.pt",
            "motion_weights":   "yolo11s.pt",
            "crisis_cooldown":  5.0,
            "heartbeat_cooldown": 30.0,
            "jpeg_quality":     80,
            "device": {                # <--- ADD THIS structure to the defaults
                "device_id": "pi-001",
                "camera_id": "lobby_cam_1",
                "location": "Building A"
            }
        }
    if os.path.exists(path):
        with open(path) as f:
            user_cfg = json.load(f)
        defaults.update(user_cfg)
    else:
        print(f"  ⚠️  {path} not found — using defaults")
    return defaults


def get_mock_sensors() -> dict:
    return {"temperature_c": 78, "gas_leak": False, "abnormal_sound": False}


async def run_sentinel_ml():
    # Load config from the correct folder
    cfg = _load_config("ml_consumer/config.json")
    
    print("🚀 Initializing Sentinel AI v3...")

    # Since your config is flat, we read keys directly from 'cfg'
    COMPUTE_DEVICE = cfg.get("compute_device", "cpu")

    vision_engine = VisionAnalyzer(
        weights_path = cfg.get("vision_weights", "ml_consumer/weights/best.pt"),
        **cfg.get("vision", {})
    )

    pose_engine = PoseAnalyzer(
        fallback_weights = cfg.get("pose_weights", "weights/yolo11n-pose.pt"),
        device           = COMPUTE_DEVICE,
        **cfg.get("pose", {})
    )

    motion_engine = MotionAnalyzer(
        person_weights = cfg.get("motion_weights", "yolo11n.pt"),
        device         = COMPUTE_DEVICE,
        **cfg.get("motion", {})
    )

    fusion_engine = ThreatFusionEngine(
        device_id = cfg.get("device_id", "pi-001"),
        camera_id = cfg.get("camera_id", "lobby_cam_1"),
        location  = cfg.get("location",  "Building A - Ground Floor"),
    )

    # ── Backend connection ─────────────────────────────────────────────────────
# --- RabbitMQ Setup ---
    rmq_host = cfg.get("rabbitmq_host", "localhost")
    rmq_queue = cfg.get("rabbitmq_queue", "sentinel_alerts")
    rmq_conn = None
    rmq_channel = None

    print(f"🐇 Connecting to RabbitMQ at {rmq_host}...")
    try:
        rmq_conn = pika.BlockingConnection(pika.ConnectionParameters(host=rmq_host))
        rmq_channel = rmq_conn.channel()
        rmq_channel.queue_declare(queue=rmq_queue, durable=True)
        print(f"✅ RabbitMQ Ready! Queue: {rmq_queue}")
    except Exception as e:
        print(f"⚠️  RabbitMQ failed ({e}). Alerts will be local only.")

    # ── Video source ───────────────────────────────────────────────────────────
    # FIX-1: use config value, not the string literal "PI_STREAM_URL"
    pi_url = cfg["pi_stream_url"]
    cap = cv2.VideoCapture(pi_url)
    if not cap.isOpened():
        print("⚠️  Pi stream not available, trying test video...")
        cap = cv2.VideoCapture("")
    if not cap.isOpened():
        print("⚠️  Test video not found, switching to webcam...")
        cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ No video source available. Exiting.")
        return

    print("🧠 AI Pipeline Active. Press Q to quit.\n")

    # ── Dispatch state ─────────────────────────────────────────────────────────
    last_crisis_time    = 0.0
    last_heartbeat_time = 0.0
    last_hazard         = "normal"
    CRISIS_COOLDOWN     = float(cfg["crisis_cooldown"])
    HEARTBEAT_COOLDOWN  = float(cfg["heartbeat_cooldown"])
    JPEG_QUALITY        = int(cfg["jpeg_quality"])

    # FIX-4: wall-clock delta tracking for pose tick()
    _last_frame_time = time.time()

    while True:
        
        for _ in range(10):
            cap.grab()
            

        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            await asyncio.sleep(0.1)
            continue
        
        frame = cv2.resize(frame, (640, 480))

        # ── FIX-4: compute real elapsed time and tick pose engine ──────────────
        now         = time.time()
        elapsed_sec = now - _last_frame_time
        _last_frame_time = now

        pose_engine.tick(elapsed_sec)       # keeps sustained_lying_seconds accurate
        motion_engine.update_fps(pose_engine.get_fps())  # FIX-5

        # ── STEP 1: Vision ─────────────────────────────────────────────────────
        vision_results, annotated_frame = vision_engine.analyze(frame)

        # ── STEP 2: Pose — always raw frame ────────────────────────────────────
        pose_results, pose_frame = pose_engine.analyze(frame)

        # FIX-3: 0.65/0.35 blend — YOLO fire boxes stay bright
        annotated_frame = _merge_frames(annotated_frame, pose_frame)

        # ── FIX-6: inject pose engine's cached boxes into motion engine ────────
        # This eliminates the redundant second YOLO inference call.
        if _SV_AVAILABLE:
            try:
                _boxes = getattr(pose_engine, "last_raw_boxes", None)
                if _boxes is not None and len(_boxes) > 0:
                    _sv_dets = sv.Detections(
                        xyxy       = _boxes.xyxy.cpu().numpy(),
                        confidence = _boxes.conf.cpu().numpy(),
                        class_id   = _boxes.cls.cpu().numpy().astype(int),
                    )
                    motion_engine.inject_detections(_sv_dets)
            except Exception as e:
                pass  # silent fallback — motion engine will run its own detector

        # ── STEP 3: Motion ─────────────────────────────────────────────────────
        motion_results, annotated_frame = motion_engine.analyze(frame, annotated_frame)

        # ── STEP 4: Sensors ────────────────────────────────────────────────────
        sensor_data = get_mock_sensors()

        # ── STEP 5: Fusion ─────────────────────────────────────────────────────
        payload = fusion_engine.build_json_payload(
            vision_results = vision_results,
            pose_results   = pose_results,
            motion_results = motion_results,
            mock_sensors   = sensor_data,
        )

        hazard   = payload["situation"]["hazard_type"]
        risk     = payload["situation"]["risk_level"]
        severity = payload["situation"]["severity_score"]

        # ── STEP 6: HUD every frame ────────────────────────────────────────────
        _draw_hud(annotated_frame, hazard, risk, severity, pose_results, motion_results)

        # ── STEP 7: Smart dispatch ─────────────────────────────────────────────
        current_time = time.time()
        is_new_state = hazard != last_hazard
        should_send  = False

        # FIX-7: three-rule dispatch
        if is_new_state:
            should_send = True
            if hazard != "normal":
                last_crisis_time = current_time
            else:
                last_heartbeat_time = current_time
        elif hazard != "normal":
            if (current_time - last_crisis_time) >= CRISIS_COOLDOWN:
                should_send = True
                last_crisis_time = current_time
        else:
            if (current_time - last_heartbeat_time) >= HEARTBEAT_COOLDOWN:
                should_send = True
                last_heartbeat_time = current_time

        if should_send:
            prefix = "🔄 [HEARTBEAT]" if hazard == "normal" else f"🚨 [{risk.upper()}] {hazard.upper()}"
            print(
                f"{prefix} | score={severity} | fps={pose_engine.get_fps()} | "
                f"posture={pose_results.get('primary_posture')} | "
                f"stampede={motion_results.get('stampede_risk')}"
            )

            # Offload the entire heavy encoding process to the thread pool
            b64 = await _encode_frame_async(annotated_frame, quality=JPEG_QUALITY)
            
            if b64:
                payload["visual_evidence"] = f"data:image/jpeg;base64,{b64}"
            else:
                payload["visual_evidence"] = ""

            with open("ml_consumer/outputs/latest_alert.json", "w") as f:
                json.dump(payload, f, indent=2)

            # FIX-8: auto-reconnect on failure
            if rmq_channel:
                try:
                    rmq_channel.basic_publish(
                        exchange='',
                        routing_key=rmq_queue,
                        body=json.dumps(payload),
                        properties=pika.BasicProperties(
                            delivery_mode=2,  # make message persistent
                        )
                    )
                    print(f"📤 Alert published to RabbitMQ: {hazard}")
                except Exception as e:
                    print(f"❌ RabbitMQ Publish Error: {e}")
                    rmq_channel = None # Trigger a reconnect check if you want

            last_hazard = hazard

        # ── Display ────────────────────────────────────────────────────────────
        try:
            cv2.imshow("Sentinel AI v3 -- Live Dashboard", annotated_frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
        except cv2.error:
            pass  # headless build — no display, still saves JSON alerts

        await asyncio.sleep(0.01)

    cap.release()
    try:
        cv2.destroyAllWindows()
    except Exception:
        pass
    if rmq_conn and rmq_conn.is_open: rmq_conn.close()

def _merge_frames(vision_frame: np.ndarray, pose_frame: np.ndarray) -> np.ndarray:
    # FIX-3: 0.65/0.35 — fire boxes stay bright, not dimmed to 50%
    if vision_frame.shape != pose_frame.shape:
        return vision_frame
    return cv2.addWeighted(vision_frame, 0.65, pose_frame, 0.35, 0)


def _draw_hud(
    frame:          np.ndarray,
    hazard:         str,
    risk:           str,
    severity:       float,
    pose_results:   dict,
    motion_results: dict,
) -> None:
    COLOR_MAP = {
        "critical": (0,   0,   255),
        "high":     (0,   165, 255),
        "moderate": (0,   255, 255),
    }
    color     = COLOR_MAP.get(risk, (0, 200, 0))
    still_ids = motion_results.get("prolonged_still_ids", [])

    lines = [
        "SENTINEL AI v3",
        f"Risk: {risk.upper()}   Score: {severity}",
        f"Hazard: {hazard}",
        f"Posture: {pose_results.get('primary_posture', '-')}",
        f"People: {pose_results.get('people_count', 0)}   "
        f"Tracked: {motion_results.get('tracked_people_count', 0)}",
        f"Stampede: {motion_results.get('stampede_risk', 'low')}",
        f"Still IDs: {still_ids if still_ids else 'none'}",
    ]

    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (390, 12 + len(lines) * 22), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.45, frame, 0.55, 0, frame)

    for i, line in enumerate(lines):
        cv2.putText(
            frame, line, (8, 22 + i * 22),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1, cv2.LINE_AA,
        )


if __name__ == "__main__":
    asyncio.run(run_sentinel_ml())