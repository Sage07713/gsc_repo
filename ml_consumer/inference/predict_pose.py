"""
Sentinel AI — Pose Analyzer (v3)
==================================
All changes vs previous version:

  FIX-1  Weight filename: "yolov11s-pose.pt" → "yolo11s-pose.pt"
          The v prefix doesn't exist in YOLO11 naming. Wrong name = wrong download.
  FIX-2  MIN_VISIBLE_KEYPOINTS raised 3 → 7. Three keypoints can't distinguish
          postures reliably in partial-occlusion crowd scenes. 7 ensures meaningful
          upper-body geometry is present before classifying.
  FIX-3  FPS_ASSUMPTION hardcoded 15.0 replaced with rolling frame-interval
          tracking. tick(elapsed_sec) called from main.py every frame. Keeps
          sustained_lying_seconds accurate at 3 FPS or 20 FPS (thermal throttle).
  FIX-4  All tunable constants are constructor params — injectable from config.json
  FIX-5  Print message updated: "YOLOv8-Pose" → "YOLO11-Pose"
  FIX-6  Empty frame early-return now passes raw frame pointer (not .copy()) —
          saves RAM allocation when camera sees nothing (99% of lobby time)
  FIX-7  last_raw_boxes saved after YOLO predict — lets main.py extract boxes
          for motion engine injection without running YOLO a second time
  FIX-8  LYING false-positive fix: when ankles are not visible (person behind
          counter), require at least one knee visible before declaring "lying".
          Without this, someone leaning over a desk triggers medical_emergency.
"""

import cv2
import numpy as np
from collections import deque, defaultdict
from ultralytics import YOLO

MMPOSE_AVAILABLE = False  # MMPose disabled — binary incompatibility on Windows


# ── COCO Pose keypoint indices ─────────────────────────────────────────────────
NOSE                   = 0
L_EYE,  R_EYE          = 1,  2
L_SHOULDER, R_SHOULDER = 5,  6
L_ELBOW,    R_ELBOW    = 7,  8
L_WRIST,    R_WRIST    = 9,  10
L_HIP,      R_HIP      = 11, 12
L_KNEE,     R_KNEE     = 13, 14
L_ANKLE,    R_ANKLE    = 15, 16


class PoseAnalyzer:
    def __init__(
        self,
        fallback_weights:      str   = "weights/yolo11s-pose.pt",
        device:                str   = "cpu",
        pose_conf_threshold:   float = 0.65,   # FIX-4: injectable param
        min_visible_keypoints: int   = 7,       # FIX-2: raised from 3
        kp_visibility_min:     float = 0.30,
        lying_pixel_threshold: int   = 120,
        hip_shoulder_threshold: int  = 90,
        crouch_angle_max:      float = 80.0,
        crouch_angle_min:      float = 10.0,
        crawl_hip_height_ratio: float = 0.35,
    ):
        self.frame_h = None
        self.frame_w = None

        # FIX-3: rolling FPS tracking replaces hardcoded FPS_ASSUMPTION = 15.0
        self._frame_times: deque = deque(maxlen=30)  # last 30 frame intervals
        self._fps_estimate: float = 15.0             # starting guess

        # Temporal memory (150 frames)
        self.posture_history = deque(maxlen=150)

        # FIX-4: all tunable constants injectable
        self.POSE_CONF_THRESHOLD    = pose_conf_threshold
        self.MIN_VISIBLE_KEYPOINTS  = min_visible_keypoints
        self.KP_VISIBILITY_MIN      = kp_visibility_min
        self.LYING_PIXEL_THRESHOLD  = lying_pixel_threshold
        self.HIP_SHOULDER_THRESHOLD = hip_shoulder_threshold
        self.CROUCH_ANGLE_MAX       = crouch_angle_max
        self.CROUCH_ANGLE_MIN       = crouch_angle_min
        self.CRAWL_HIP_HEIGHT_RATIO = crawl_hip_height_ratio

        # FIX-7: storage for last raw YOLO boxes (used by motion engine injection)
        self.last_raw_boxes = None

        self._load_yolo(fallback_weights)

    def _load_yolo(self, weights_path: str):
        self.model   = YOLO(weights_path)
        self.backend = "yolo"
        # FIX-5: updated print to say YOLO11 not YOLOv8
        print(f"  ✅ PoseAnalyzer ready (YOLO11-Pose): {weights_path}\n")

    def tick(self, elapsed_sec: float) -> None:
        """
        FIX-3: Called from main.py every frame with wall-clock delta.
        Updates the rolling FPS estimate used by sustained_lying_seconds.
        Without this, thermal throttling (15→3 FPS) would make lying duration
        appear 5x shorter than it really is.
        """
        if elapsed_sec > 0:
            self._frame_times.append(elapsed_sec)
            if self._frame_times:
                avg_interval = sum(self._frame_times) / len(self._frame_times)
                self._fps_estimate = 1.0 / avg_interval if avg_interval > 0 else 15.0

    def get_fps(self) -> float:
        return round(self._fps_estimate, 1)

    # ── Geometry helpers ───────────────────────────────────────────────────────
    @staticmethod
    def _angle(p1, p2, p3) -> float:
        p1, p2, p3 = np.array(p1), np.array(p2), np.array(p3)
        v1, v2 = p1 - p2, p3 - p2
        n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
        if n1 == 0 or n2 == 0:
            return 0.0
        cos_a = np.dot(v1, v2) / (n1 * n2)
        return float(np.degrees(np.arccos(np.clip(cos_a, -1.0, 1.0))))

    @staticmethod
    def _kp(person_kpts: np.ndarray, idx: int) -> tuple:
        return float(person_kpts[idx][0]), float(person_kpts[idx][1])

    def _visible(self, person_kpts: np.ndarray, *indices: int) -> bool:
        for i in indices:
            x, y, conf = person_kpts[i]
            if conf < self.KP_VISIBILITY_MIN or (x == 0.0 and y == 0.0):
                return False
        return True

    # ── Per-person posture classifier ──────────────────────────────────────────
    def _classify_posture(self, person_kpts: np.ndarray) -> str:
        ls, rs = self._kp(person_kpts, L_SHOULDER), self._kp(person_kpts, R_SHOULDER)
        la, ra = self._kp(person_kpts, L_ANKLE),    self._kp(person_kpts, R_ANKLE)
        lh, rh = self._kp(person_kpts, L_HIP),      self._kp(person_kpts, R_HIP)
        lk, rk = self._kp(person_kpts, L_KNEE),     self._kp(person_kpts, R_KNEE)
        lw, rw = self._kp(person_kpts, L_WRIST),    self._kp(person_kpts, R_WRIST)

        avg_shoulder_y = (ls[1] + rs[1]) / 2.0
        avg_ankle_y    = (la[1] + ra[1]) / 2.0
        avg_hip_y      = (lh[1] + rh[1]) / 2.0

        # ── 1. LYING ───────────────────────────────────────────────────────────
        if self._visible(person_kpts, L_HIP, R_HIP):
            hip_shoulder_diff = abs(avg_hip_y - avg_shoulder_y)
            if hip_shoulder_diff < self.HIP_SHOULDER_THRESHOLD:
                if self._visible(person_kpts, L_ANKLE, R_ANKLE):
                    if abs(avg_ankle_y - avg_shoulder_y) < self.LYING_PIXEL_THRESHOLD:
                        return "lying"
                else:
                    # FIX-8: ankles not visible — require a knee to confirm lower-body
                    # geometry before declaring medical emergency. Without this, someone
                    # leaning over a counter (hips≈shoulder height, ankles hidden)
                    # triggers a false medical_emergency alert.
                    knee_visible = (
                        self._visible(person_kpts, L_KNEE) or
                        self._visible(person_kpts, R_KNEE)
                    )
                    if knee_visible:
                        return "lying"
                    # No knee visible — can't confirm lying, default to standing

        # ── 2. CRAWLING ────────────────────────────────────────────────────────
        if self._visible(person_kpts, L_HIP, R_HIP, L_KNEE, R_KNEE) and self.frame_h:
            hip_y_ratio = avg_hip_y / self.frame_h
            if hip_y_ratio > self.CRAWL_HIP_HEIGHT_RATIO:
                lk_angle = self._angle(lh, lk, la) if self._visible(person_kpts, L_ANKLE) else 0.0
                rk_angle = self._angle(rh, rk, ra) if self._visible(person_kpts, R_ANKLE) else 0.0
                if (0 < lk_angle < 100) or (0 < rk_angle < 100):
                    # Spine check: if shoulders are clearly above hips, person is
                    # sitting upright (yoga, floor-sitting) — not crawling
                    spine_vertical = avg_hip_y - avg_shoulder_y
                    if spine_vertical > 60:
                        return "standing"
                    return "crawling"

        # ── 3. CROUCHING ───────────────────────────────────────────────────────
        if self._visible(person_kpts, L_HIP, L_KNEE, L_ANKLE):
            if self.CROUCH_ANGLE_MIN < self._angle(lh, lk, la) < self.CROUCH_ANGLE_MAX:
                return "crouching"
        if self._visible(person_kpts, R_HIP, R_KNEE, R_ANKLE):
            if self.CROUCH_ANGLE_MIN < self._angle(rh, rk, ra) < self.CROUCH_ANGLE_MAX:
                return "crouching"

        # ── 4. ARMS RAISED ─────────────────────────────────────────────────────
        if self._visible(person_kpts, L_WRIST, R_WRIST, L_SHOULDER, R_SHOULDER):
            if lw[1] > 0 and lw[1] < ls[1] and rw[1] > 0 and rw[1] < rs[1]:
                return "arms_raised"

        # ── 5. HANDS BEHIND BACK ───────────────────────────────────────────────
        if self._visible(person_kpts, L_WRIST, R_WRIST, L_HIP, R_HIP, L_SHOULDER, R_SHOULDER):
            sx_min    = min(ls[0], rs[0])
            sx_max    = max(ls[0], rs[0])
            hip_y_avg = (lh[1] + rh[1]) / 2.0
            l_behind  = sx_min < lw[0] < sx_max and abs(lw[1] - hip_y_avg) < 80
            r_behind  = sx_min < rw[0] < sx_max and abs(rw[1] - hip_y_avg) < 80
            if l_behind and r_behind:
                return "hands_behind_back"

        return "standing"

    # ── YOLO inference ─────────────────────────────────────────────────────────
    def _analyze_yolo(self, frame: np.ndarray) -> tuple:
        results = self.model.predict(frame, conf=self.POSE_CONF_THRESHOLD, verbose=False)

        # 1. True Zero-Copy Early Return: If the room is empty, do nothing.
        if not results or len(results[0]) == 0 or results[0].keypoints is None:
            self.last_raw_boxes = None
            return [], frame  # Returns the raw, un-copied memory pointer

        # 2. Cache boxes for main.py motion injection
        self.last_raw_boxes = results[0].boxes

        # 3. Only allocate memory for a new image if there are skeletons to draw
        annotated = results[0].plot()

        raw_keypoints = results[0].keypoints.data.cpu().numpy()
        valid_people  = [
            p for p in raw_keypoints
            if sum(1 for kp in p if kp[2] > self.KP_VISIBILITY_MIN) >= self.MIN_VISIBLE_KEYPOINTS
        ]
        
        return valid_people, annotated

    # ── Public API ─────────────────────────────────────────────────────────────
    def analyze(self, frame: np.ndarray) -> tuple:
        """
        Always pass the RAW BGR frame — never an annotated frame.
        Returns: (pose_results dict, annotated_frame with skeleton drawn)
        """
        self.frame_h, self.frame_w = frame.shape[:2]

        pose_results = {
            "human_present":            False,
            "people_count":             0,
            "primary_posture":          "standing",
            "sustained_lying_seconds":  0.0,
            "motion_state":             "none",
            "people_lying":             0,
            "people_crouching":         0,
            "people_crawling":          0,
            "people_hands_behind_back": 0,
            "posture_breakdown":        [],
        }

        valid_people, annotated_frame = self._analyze_yolo(frame)

        num_people = len(valid_people)
        if num_people == 0:
            self.posture_history.append("standing")
            # FIX-6: return raw frame pointer (not .copy()) when nothing detected
            # saves repeated RAM allocation in empty-scene cameras
            return pose_results, annotated_frame

        pose_results["human_present"] = True
        pose_results["people_count"]  = num_people
        pose_results["motion_state"]  = "low"

        posture_counts = defaultdict(int)
        breakdown      = []

        KNOWN_POSTURES = {
            "standing", "lying", "crouching",
            "crawling", "arms_raised", "hands_behind_back",
        }

        for person_kpts in valid_people:
            posture = self._classify_posture(person_kpts)
            if posture not in KNOWN_POSTURES:
                print(f"  ⚠️  Unknown posture '{posture}' — defaulting to 'standing'.")
                posture = "standing"
            posture_counts[posture] += 1
            breakdown.append(posture)

        pose_results["posture_breakdown"]        = breakdown
        pose_results["people_lying"]             = posture_counts["lying"]
        pose_results["people_crouching"]         = posture_counts["crouching"]
        pose_results["people_crawling"]          = posture_counts["crawling"]
        pose_results["people_hands_behind_back"] = posture_counts["hands_behind_back"]

        if   posture_counts["lying"]             > 0: pose_results["primary_posture"] = "lying"
        elif posture_counts["crawling"]          > 0: pose_results["primary_posture"] = "crawling"
        elif posture_counts["hands_behind_back"] > 0: pose_results["primary_posture"] = "hands_behind_back"
        elif posture_counts["crouching"]         > 0: pose_results["primary_posture"] = "crouching"
        elif posture_counts["arms_raised"]       > 0: pose_results["primary_posture"] = "arms_raised"
        else:                                          pose_results["primary_posture"] = "standing"

        self.posture_history.append(pose_results["primary_posture"])

        # FIX-3: use rolling FPS estimate for accurate wall-clock timing
        lying_frames = 0
        for p in reversed(self.posture_history):
            if p == "lying":
                lying_frames += 1
            else:
                break
        fps = max(self._fps_estimate, 1.0)  # guard against divide-by-zero
        pose_results["sustained_lying_seconds"] = round(lying_frames / fps, 1)

        return pose_results, annotated_frame