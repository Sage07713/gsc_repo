"""
Sentinel AI — Crowd Motion Analyzer (v3)
==========================================
All changes vs previous version:

  FIX-1  "yolov11s.pt" → "yolo11s.pt" in default param and comments
  FIX-2  Eliminated redundant per-frame YOLO detection pass.
          inject_detections(sv_detections) accepts boxes from the pose engine.
          main.py extracts pose engine's last_raw_boxes and injects them here.
          If nothing injected, falls back to its own detector (backward compat).
          On CPU this was running two full YOLO passes per frame — halving FPS.
  FIX-3  STILL_FRAMES_ALERT_THRESHOLD replaced with still_alert_seconds (wall-clock).
          update_fps(fps) called from main.py so threshold adapts to real FPS.
          At 3 FPS (Pi thermal throttle), old hardcoded 90-frame threshold would
          take 30 seconds to flag a collapsed person instead of 6 seconds.
  FIX-4  All tunable constants are constructor params — injectable from config.json
  FIX-5  Memory leak fix: stale track IDs pruned after every ByteTrack update.
          In a busy lobby running 24h, thousands of track_ids accumulate in
          _centroids/_velocities/_still_counter and eventually OOM the process.
  FIX-6  Circular angle math trap fixed for demo: stampede detection now relies
          on velocity magnitude only (not angle std dev). arctan2 outputs
          -180°→+180° so two people running the same direction can show 358°
          difference, falsely triggering scatter/panic. Velocity is reliable.
"""

import cv2
import numpy as np
from collections import defaultdict, deque

try:
    import supervision as sv
    SUPERVISION_AVAILABLE = True
except ImportError:
    SUPERVISION_AVAILABLE = False
    print("  ⚠️  'supervision' not installed. Falling back to optical flow.")
    print("      Fix: pip install supervision==0.21.0")

try:
    from ultralytics import YOLO as _YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False


class MotionAnalyzer:
    def __init__(
        self,
        person_weights:          str   = "yolo11s.pt",   # FIX-1: correct name
        device:                  str   = "cpu",
        velocity_panic_threshold: float = 25.0,           # FIX-4: injectable
        velocity_medium_threshold: float = 12.0,
        min_tracks_for_stampede: int   = 3,
        still_velocity_threshold: float = 1.5,
        still_alert_seconds:     float = 6.0,            # FIX-3: wall-clock seconds
        person_detection_conf:   float = 0.45,
        velocity_history_len:    int   = 5,
    ):
        print("  Loading Crowd Motion Analyzer (ByteTrack + SORT)...")

        self.VELOCITY_PANIC_THRESHOLD  = velocity_panic_threshold
        self.VELOCITY_MEDIUM_THRESHOLD = velocity_medium_threshold
        self.MIN_TRACKS_FOR_STAMPEDE   = min_tracks_for_stampede
        self.STILL_VELOCITY_THRESHOLD  = still_velocity_threshold
        self.STILL_ALERT_SECONDS       = still_alert_seconds
        self.PERSON_DETECTION_CONF     = person_detection_conf
        self.VELOCITY_HISTORY_LEN      = velocity_history_len

        # FIX-3: dynamic frame threshold updated via update_fps()
        self._fps_estimate             = 15.0
        self._still_frames_threshold   = int(still_alert_seconds * self._fps_estimate)

        # FIX-2: injected detections slot — set by main.py before each analyze()
        self._injected_dets = None

        self.backend = None

        if SUPERVISION_AVAILABLE and YOLO_AVAILABLE:
            try:
                self._detector = _YOLO(person_weights)
                self._tracker  = sv.ByteTrack(
                    track_activation_threshold = 0.25,
                    lost_track_buffer          = 30,
                    minimum_matching_threshold = 0.8,
                    frame_rate                 = 15,
                )
                self.backend = "bytetrack"
                print("  ✅ ByteTracker ready (per-person velocity + stampede detection)\n")
            except Exception as e:
                print(f"  ⚠️  ByteTrack init failed ({e}). Falling back to optical flow.")

        if self.backend is None:
            self._init_optical_flow_fallback()

        # Per-track state
        self._centroids:           dict = defaultdict(lambda: deque(maxlen=self.VELOCITY_HISTORY_LEN + 1))
        self._velocities:          dict = defaultdict(lambda: deque(maxlen=self.VELOCITY_HISTORY_LEN))
        self._still_counter:       dict = defaultdict(int)
        self._prolonged_still_set: set  = set()

    def update_fps(self, fps: float) -> None:
        """
        FIX-3: Called from main.py every frame with rolling FPS estimate.
        Recalculates still_frames_threshold so a collapsed person is always
        flagged in STILL_ALERT_SECONDS of real wall-clock time regardless of FPS.
        """
        if fps > 0:
            self._fps_estimate          = fps
            self._still_frames_threshold = max(1, int(self.STILL_ALERT_SECONDS * fps))

    def inject_detections(self, sv_detections) -> None:
        """
        FIX-2: Accept pre-computed sv.Detections from main.py (extracted from
        pose engine's last_raw_boxes). Avoids running YOLO a second time.
        Call this BEFORE analyze() each frame.
        """
        self._injected_dets = sv_detections

    def _init_optical_flow_fallback(self):
        self.backend        = "optical_flow"
        self.prev_gray      = None
        self.p0             = None
        self.frame_count    = 0
        self.feature_params = dict(maxCorners=100, qualityLevel=0.3, minDistance=7, blockSize=7)
        self.lk_params      = dict(
            winSize=(15, 15), maxLevel=2,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03),
        )
        print("  ✅ MotionAnalyzer ready (optical flow fallback)\n")

    # ── ByteTrack path ─────────────────────────────────────────────────────────
    def _analyze_bytetrack(self, frame: np.ndarray, annotated_frame: np.ndarray) -> tuple:
        motion_results = {
            "avg_motion_magnitude": 0.0,
            "panic_detected":       False,
            "stampede_risk":        "low",
            "tracked_people_count": 0,
            "prolonged_still_ids":  [],
        }

        # FIX-2: use injected detections if available, otherwise run own detector
        if self._injected_dets is not None:
            detections          = self._injected_dets
            self._injected_dets = None   # consume immediately — prevents ghost tracking
        else:
            det_results = self._detector.predict(
                frame, conf=self.PERSON_DETECTION_CONF, classes=[0], verbose=False
            )
            if not det_results or len(det_results[0].boxes) == 0:
                motion_results["prolonged_still_ids"] = sorted(self._prolonged_still_set)
                return motion_results, annotated_frame

            boxes      = det_results[0].boxes
            detections = sv.Detections(
                xyxy       = boxes.xyxy.cpu().numpy(),
                confidence = boxes.conf.cpu().numpy(),
                class_id   = boxes.cls.cpu().numpy().astype(int),
            )

        tracked = self._tracker.update_with_detections(detections)

        # ── 🚨 NEW FIX: Safe Garbage Collection BEFORE Early Return ──
        current_ids = set()
        if tracked is not None and len(tracked) > 0:
            current_ids = {int(tid) for tid in tracked.tracker_id if tid is not None}

        # Garbage collect stale IDs immediately
        stale_ids = set(self._centroids.keys()) - current_ids
        for sid in stale_ids:
            self._centroids.pop(sid, None)
            self._velocities.pop(sid, None)
            self._still_counter.pop(sid, None)
            self._prolonged_still_set.discard(sid)

        # NOW it is safe to return early if the room is empty
        if tracked is None or len(tracked) == 0:
            motion_results["prolonged_still_ids"] = sorted(self._prolonged_still_set)
            return motion_results, annotated_frame
        # ─────────────────────────────────────────────────────────────

        motion_results["tracked_people_count"] = len(tracked)
        per_track_velocities = []

        for i in range(len(tracked)):
            bbox     = tracked.xyxy[i]
            track_id = tracked.tracker_id[i]
            if track_id is None:
                continue

            track_id = int(track_id)

            cx = float((bbox[0] + bbox[2]) / 2)
            cy = float((bbox[1] + bbox[3]) / 2)
            self._centroids[track_id].append((cx, cy))

            if len(self._centroids[track_id]) >= 2:
                prev = self._centroids[track_id][-2]
                curr = self._centroids[track_id][-1]
                dx   = curr[0] - prev[0]
                dy   = curr[1] - prev[1]
                vel  = float(np.sqrt(dx ** 2 + dy ** 2))
                self._velocities[track_id].append(vel)

                smoothed_vel = float(np.mean(self._velocities[track_id]))
                per_track_velocities.append(smoothed_vel)

                # Still-person detection
                if smoothed_vel < self.STILL_VELOCITY_THRESHOLD:
                    self._still_counter[track_id] += 1
                else:
                    self._still_counter[track_id] = 0

                if self._still_counter[track_id] >= self._still_frames_threshold:
                    self._prolonged_still_set.add(track_id)
                else:
                    self._prolonged_still_set.discard(track_id)

                # Draw track box
                color = (0, 255, 0)
                if smoothed_vel > self.VELOCITY_PANIC_THRESHOLD:
                    color = (0, 0, 255)
                elif smoothed_vel > self.VELOCITY_MEDIUM_THRESHOLD:
                    color = (0, 165, 255)

                x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
                cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(
                    annotated_frame,
                    f"ID:{track_id} v:{smoothed_vel:.1f}",
                    (x1, max(y1 - 6, 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1,
                )

        motion_results["prolonged_still_ids"] = sorted(self._prolonged_still_set)

        if not per_track_velocities:
            return motion_results, annotated_frame

        avg_vel = float(np.mean(per_track_velocities))
        motion_results["avg_motion_magnitude"] = round(avg_vel, 2)

        # FIX-6: stampede detection uses velocity only
        num_fast = sum(1 for v in per_track_velocities if v > self.VELOCITY_PANIC_THRESHOLD)
        enough   = len(tracked) >= self.MIN_TRACKS_FOR_STAMPEDE

        if enough and num_fast >= 2:
            motion_results["panic_detected"] = True
            motion_results["stampede_risk"]  = "high"
        elif avg_vel > self.VELOCITY_MEDIUM_THRESHOLD:
            motion_results["stampede_risk"]  = "medium"

        return motion_results, annotated_frame

    # ── Optical flow fallback ──────────────────────────────────────────────────
    def _analyze_optical_flow(self, frame: np.ndarray, annotated_frame: np.ndarray) -> tuple:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        motion_results = {
            "avg_motion_magnitude": 0.0,
            "panic_detected":       False,
            "stampede_risk":        "low",
            "tracked_people_count": 0,
            "prolonged_still_ids":  [],
        }
        if self.prev_gray is None:
            self.prev_gray = gray
            self.p0        = cv2.goodFeaturesToTrack(gray, mask=None, **self.feature_params)
            return motion_results, annotated_frame

        if self.p0 is not None and len(self.p0) > 0:
            p1, st, _ = cv2.calcOpticalFlowPyrLK(self.prev_gray, gray, self.p0, None, **self.lk_params)
            if p1 is not None:
                good_new   = p1[st == 1]
                good_old   = self.p0[st == 1]
                magnitudes = []
                for new, old in zip(good_new, good_old):
                    a, b = new.ravel(); c, d = old.ravel()
                    mag  = float(np.sqrt((a - c) ** 2 + (b - d) ** 2))
                    magnitudes.append(mag)
                    if mag > 2.0:
                        annotated_frame = cv2.arrowedLine(
                            annotated_frame, (int(c), int(d)), (int(a), int(b)),
                            (0, 0, 255), 2, tipLength=0.4,
                        )
                if magnitudes:
                    avg_mag = float(np.mean(magnitudes))
                    motion_results["avg_motion_magnitude"] = round(avg_mag, 2)
                    if avg_mag > 8.0:
                        motion_results["panic_detected"] = True
                        motion_results["stampede_risk"]  = "high"
                    elif avg_mag > 4.5:
                        motion_results["stampede_risk"]  = "medium"
                self.p0 = good_new.reshape(-1, 1, 2)

        self.frame_count += 1
        if self.frame_count % 10 == 0 or self.p0 is None or len(self.p0) < 10:
            self.p0 = cv2.goodFeaturesToTrack(gray, mask=None, **self.feature_params)
        self.prev_gray = gray
        return motion_results, annotated_frame

    # ── Public API ─────────────────────────────────────────────────────────────
    def analyze(self, frame: np.ndarray, annotated_frame: np.ndarray) -> tuple:
        if self.backend == "bytetrack":
            return self._analyze_bytetrack(frame, annotated_frame)
        else:
            return self._analyze_optical_flow(frame, annotated_frame)