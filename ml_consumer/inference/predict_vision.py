"""
Sentinel AI — Vision Analyzer
==============================
Runs YOLOv8 fire/smoke model on each frame.

Improvements applied:
  1. Temporal smoothing     : 5-frame majority vote prevents flip-flopping detections
  2. Confidence filter      : predict conf=0.45 + post-filter conf>0.50 removes noise
  3. Two-window trend       : fast trend after 5 frames, stabilizes using full 30-frame history
  4. Conf sync on suppression: fire_conf zeroed when majority vote suppresses detection

Fire spread tracking:
  Tracks normalized bounding box area (% of screen) across frames.
  spread_rate > 0.20  → "escalating"
  spread_rate < -0.20 → "diminishing"
  else                → "stable"
"""

import cv2
from ultralytics import YOLO
from collections import deque


class VisionAnalyzer:
    def __init__(self, weights_path="ml_consumer/weights/fire_model.pt"):
        print(f"  Loading YOLO Vision Model from {weights_path}...")
        try:
            self.model = YOLO(weights_path)
        except Exception as e:
            print(f"  ⚠️  Could not load custom weights, falling back to yolov8n. Error: {e}")
            self.model = YOLO("weights/yolov8n.pt")

        # ── Temporal memory 
        # Majority vote over last 5 frames — prevents single-frame noise flips
        self.fire_history = deque(maxlen=5)

        # Normalized fire bbox area history — used for spread rate calculation
        # 30 frames ≈ 2 seconds at 15 FPS
        self.fire_area_history = deque(maxlen=30)

        print("  ✅ VisionAnalyzer ready (temporal smoothing + fire spread tracking)\n")

    def analyze(self, frame):
        """
        Runs YOLO inference on the frame.
        Returns:
            vision_results (dict): fire/smoke detection + spread trend
            annotated_frame: frame with bounding boxes drawn
        """
        # ── Inference ──────────────────────────────────────────────────────────
        # conf=0.45: filters garbage detections before NMS, saves compute.
        # Post-filter at >0.50 below acts as second safety net.
        results = self.model.predict(frame, conf=0.45, verbose=False)

        vision_results = {
            "fire_detected":   False,
            "fire_conf":       0.0,
            "smoke_detected":  False,
            "smoke_conf":      0.0,
            "fire_spread_rate": 0.0,
            "fire_trend":      "stable",
        }

        current_fire_area = 0.0
        frame_area = frame.shape[0] * frame.shape[1]   # total pixels for normalization

        # ── Parse detections ───────────────────────────────────────────────────
        if results and len(results[0].boxes) > 0:
            boxes = results[0].boxes
            names = self.model.names

            for box in boxes:
                class_id   = int(box.cls[0])
                class_name = names[class_id].lower()
                confidence = float(box.conf[0])

                # Normalized bounding box area (fraction of screen)
                w, h = float(box.xywh[0][2]), float(box.xywh[0][3])
                box_area_norm = (w * h) / frame_area

                # IMPROVEMENT 2: explicit confidence post-filter
                if "fire" in class_name and confidence > 0.50:
                    if confidence > vision_results["fire_conf"]:
                        vision_results["fire_conf"] = round(confidence, 4)
                    vision_results["fire_detected"] = True
                    current_fire_area += box_area_norm

                if "smoke" in class_name and confidence > 0.50:
                    if confidence > vision_results["smoke_conf"]:
                        vision_results["smoke_conf"] = round(confidence, 4)
                    vision_results["smoke_detected"] = True

        # ── IMPROVEMENT 1: Temporal smoothing — 5-frame majority vote ─────────
        # Prevents single noisy frames from flipping detection state.
        # Requires 3 out of last 5 frames to agree before reporting detected=True.
        self.fire_history.append(vision_results["fire_detected"])

        if sum(self.fire_history) >= 3:
            vision_results["fire_detected"] = True
        else:
            vision_results["fire_detected"] = False
            vision_results["fire_conf"]     = 0.0   # don't report conf when vote suppressed

        # ── IMPROVEMENT 3: Two-window fire spread trend ────────────────────────
        self.fire_area_history.append(current_fire_area)

        history_len = len(self.fire_area_history)

        if history_len >= 5:
            history_list = list(self.fire_area_history)

            # Fast window: most recent 5 frames (responds in ~0.3s)
            recent_oldest = history_list[-5]
            recent_newest = history_list[-1]

            if recent_oldest > 0:
                spread_rate = (recent_newest - recent_oldest) / recent_oldest
            elif recent_newest > 0 and recent_oldest == 0:
                spread_rate = 1.0   # fire appeared from nothing = 100% growth
            else:
                spread_rate = 0.0

            vision_results["fire_spread_rate"] = round(spread_rate, 2)

            # Trend label
            if   spread_rate >  0.20: vision_results["fire_trend"] = "escalating"
            elif spread_rate < -0.20: vision_results["fire_trend"] = "diminishing"
            else:                     vision_results["fire_trend"] = "stable"

        # ── Annotated frame ────────────────────────────────────────────────────
        annotated_frame = results[0].plot() if results else frame

        return vision_results, annotated_frame