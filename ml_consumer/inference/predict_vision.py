"""
Sentinel AI — Vision Analyzer (v3 — fixed & hardened)
=====================================================
Optimized for YOLO11s with temporal majority voting and spread clamping.
"""

import numpy as np
import cv2
from ultralytics import YOLO
from collections import deque


class VisionAnalyzer:
    def __init__(
        self,
        weights_path:      str   = "weights/best.pt",
        temporal_window:   int   = 7,        # FIX-3: Now injectable
        majority_votes:    int   = 4,        # FIX-3: Now injectable
        fire_conf_thresh:  float = 0.52,     # FIX-3: Now injectable
        smoke_conf_thresh: float = 0.48,     # FIX-3: Now injectable
        infer_conf:        float = 0.40,     # FIX-3: Now injectable
    ):
        print(f"  Loading YOLO11 Vision Model from {weights_path}...")
        try:
            self.model = YOLO(weights_path)
            print(f"  Loaded custom weights: {weights_path}")
        except Exception as e:
            print(f"  ⚠️  Custom weights failed ({e}), trying yolo11s pretrained...")
            try:
                self.model = YOLO("yolo11s.pt")
                print("  Loaded yolo11s pretrained fallback.")
            except Exception as e2:
                print(f"  ⚠️  yolo11s failed ({e2}), falling back to yolov8n.")
                self.model = YOLO("yolov8n.pt")

        # FIX-7: Safety clamp — majority votes cannot exceed the window size
        self._temporal_window = temporal_window
        self._majority_votes  = min(majority_votes, temporal_window)

        self.fire_history      = deque(maxlen=self._temporal_window)
        self.smoke_history     = deque(maxlen=self._temporal_window)
        self.fire_area_history = deque(maxlen=30)

        # Store thresholds as instance variables
        self.FIRE_CONF_THRESHOLD  = fire_conf_thresh
        self.SMOKE_CONF_THRESHOLD = smoke_conf_thresh
        self.INFER_CONF           = infer_conf

        print(f"  ✅ VisionAnalyzer ready (Votes: {self._majority_votes}/{self._temporal_window})\n")

    def analyze(self, frame: np.ndarray) -> tuple:
        frame_h, frame_w = frame.shape[:2]
        frame_area = frame_h * frame_w

        results = self.model.predict(frame, conf=self.INFER_CONF, verbose=False)

        vision_results = {
            "fire_detected":    False,
            "fire_conf":        0.0,
            "smoke_detected":   False,
            "smoke_conf":       0.0,
            "fire_spread_rate": 0.0,
            "fire_trend":       "stable",
        }

        current_fire_area  = 0.0
        raw_fire_detected  = False
        raw_smoke_detected = False

        if results and len(results[0].boxes) > 0:
            boxes = results[0].boxes
            names = self.model.names

            for box in boxes:
                class_id   = int(box.cls[0])
                class_name = names[class_id].lower()
                confidence = float(box.conf[0])
                w = float(box.xywh[0][2])
                h = float(box.xywh[0][3])
                box_area_norm = (w * h) / frame_area

                if "fire" in class_name and confidence > self.FIRE_CONF_THRESHOLD:
                    if confidence > vision_results["fire_conf"]:
                        vision_results["fire_conf"] = round(confidence, 4)
                    raw_fire_detected = True
                    current_fire_area += box_area_norm

                if "smoke" in class_name and confidence > self.SMOKE_CONF_THRESHOLD:
                    if confidence > vision_results["smoke_conf"]:
                        vision_results["smoke_conf"] = round(confidence, 4)
                    raw_smoke_detected = True

        # Temporal majority voting
        self.fire_history.append(raw_fire_detected)
        self.smoke_history.append(raw_smoke_detected)

        if sum(self.fire_history) >= self._majority_votes:
            vision_results["fire_detected"] = True
        else:
            vision_results["fire_detected"] = False
            vision_results["fire_conf"]     = 0.0

        if sum(self.smoke_history) >= self._majority_votes:
            vision_results["smoke_detected"] = True
        else:
            vision_results["smoke_detected"] = False
            vision_results["smoke_conf"]     = 0.0

        # Fire spread trend tracking
        self.fire_area_history.append(current_fire_area)

        if len(self.fire_area_history) >= 5:
            # FIX-6: Direct deque indexing (prevents list allocation)
            recent_oldest = self.fire_area_history[-5]
            recent_newest = self.fire_area_history[-1]

            if recent_oldest > 0:
                spread_rate = (recent_newest - recent_oldest) / recent_oldest
            elif recent_newest > 0 and recent_oldest == 0:
                spread_rate = 1.0
            else:
                spread_rate = 0.0

            # FIX-4: Clamp spread rate to prevent extreme outliers from movement
            spread_rate = max(-5.0, min(5.0, spread_rate))
            vision_results["fire_spread_rate"] = round(spread_rate, 2)

            if   spread_rate >  0.20: vision_results["fire_trend"] = "escalating"
            elif spread_rate < -0.20: vision_results["fire_trend"] = "diminishing"
            else:                     vision_results["fire_trend"] = "stable"

        # FIX-5: Return a copy if there are no results to ensure downstream safety
        annotated_frame = results[0].plot() if results else frame.copy()
        return vision_results, annotated_frame