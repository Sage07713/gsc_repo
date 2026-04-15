"""
Sentinel AI — Multi-Person Pose Analyzer (YOLOv8-Pose)
========================================================
Bug fixes applied:
  1. (0,0) Phantom Filter  → ignores off-screen hallucinated keypoints
  2. Stricter Crouch Angle → ignores sitting on chairs or cross-legged
  3. Temporal Memory       → tracks how long a person is on the ground
"""

import cv2
import numpy as np
from ultralytics import YOLO
from collections import deque

# ── Tunable constants — adjust per camera installation ────────────────────────
POSE_CONF_THRESHOLD    = 0.65   
MIN_VISIBLE_KEYPOINTS  = 3      # Allows webcam upper-body detection
KP_VISIBILITY_MIN      = 0.3    
LYING_PIXEL_THRESHOLD  = 120    # Generous for close-up webcams
HIP_SHOULDER_THRESHOLD = 60     
CROUCH_ANGLE_MAX       = 80     # 👈 LOWERED: Filters out sitting on chairs/beds!
CROUCH_ANGLE_MIN       = 10     

# ── COCO Pose keypoint indices ─────────────────────────────────────────────────
L_SHOULDER, R_SHOULDER = 5,  6
L_ELBOW,    R_ELBOW    = 7,  8
L_WRIST,    R_WRIST    = 9,  10
L_HIP,      R_HIP      = 11, 12
L_KNEE,     R_KNEE     = 13, 14
L_ANKLE,    R_ANKLE    = 15, 16


class PoseAnalyzer:
    def __init__(self, weights_path: str = "weights/yolov8s-pose.pt"):
        print(f"  Loading YOLOv8-Pose model: {weights_path}")
        self.model = YOLO(weights_path)
        print("  ✅ PoseAnalyzer ready (multi-person, biomechanics-based)\n")
        
        # 🕰️ TEMPORAL MEMORY: Track scene posture over the last 150 frames (~10 seconds)
        self.posture_history = deque(maxlen=150)
        self.FPS_ASSUMPTION = 15.0 

    # ── Geometry helpers ───────────────────────────────────────────────────────
    @staticmethod
    def _angle(p1, p2, p3) -> float:
        p1, p2, p3 = np.array(p1), np.array(p2), np.array(p3)
        v1, v2 = p1 - p2, p3 - p2
        n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
        if n1 == 0 or n2 == 0: return 0.0
        cos_a = np.dot(v1, v2) / (n1 * n2)
        return float(np.degrees(np.arccos(np.clip(cos_a, -1.0, 1.0))))

    @staticmethod
    def _kp(person_kpts, idx) -> tuple:
        return person_kpts[idx][0], person_kpts[idx][1]

    @staticmethod
    def _visible(person_kpts, *indices) -> bool:
        """
        Returns True if ALL specified keypoints have visibility > threshold 
        AND ignores YOLO's (0.0, 0.0) phantom padding bug.
        """
        for i in indices:
            x, y, conf = person_kpts[i]
            if conf < KP_VISIBILITY_MIN or (x == 0.0 and y == 0.0):
                return False
        return True

    # ── Per-person posture classifier ──────────────────────────────────────────
    def _classify_posture(self, person_kpts) -> str:
        ls, rs = self._kp(person_kpts, L_SHOULDER), self._kp(person_kpts, R_SHOULDER)
        la, ra = self._kp(person_kpts, L_ANKLE),    self._kp(person_kpts, R_ANKLE)
        lh, rh = self._kp(person_kpts, L_HIP),      self._kp(person_kpts, R_HIP)
        lk, rk = self._kp(person_kpts, L_KNEE),     self._kp(person_kpts, R_KNEE)
        lw, rw = self._kp(person_kpts, L_WRIST),    self._kp(person_kpts, R_WRIST)

        avg_shoulder_y = (ls[1] + rs[1]) / 2.0
        avg_ankle_y    = (la[1] + ra[1]) / 2.0
        avg_hip_y      = (lh[1] + rh[1]) / 2.0

        # ── Check 1: LYING (man-down / medical emergency) ──────────────────────
        if self._visible(person_kpts, L_HIP, R_HIP):
            hip_shoulder_diff = abs(avg_hip_y - avg_shoulder_y)
            
            if hip_shoulder_diff < HIP_SHOULDER_THRESHOLD:
                if self._visible(person_kpts, L_ANKLE, R_ANKLE):
                    abs_y_distance = abs(avg_ankle_y - avg_shoulder_y)
                    if abs_y_distance < LYING_PIXEL_THRESHOLD:
                        return "lying"
                else:
                    return "lying"

        # ── Check 2: CROUCHING / PANIC ─────────────────────────────────────────
        if self._visible(person_kpts, L_HIP, L_KNEE, L_ANKLE):
            leg_angle = self._angle(lh, lk, la)
            if CROUCH_ANGLE_MIN < leg_angle < CROUCH_ANGLE_MAX:
                return "crouching"

        if self._visible(person_kpts, R_HIP, R_KNEE, R_ANKLE):
            leg_angle = self._angle(rh, rk, ra)
            if CROUCH_ANGLE_MIN < leg_angle < CROUCH_ANGLE_MAX:
                return "crouching"

        # ── Check 3: ARMS RAISED / SURRENDER ──────────────────────────────────
        if self._visible(person_kpts, L_WRIST, R_WRIST, L_SHOULDER, R_SHOULDER):
            left_raised  = lw[1] > 0 and lw[1] < ls[1]
            right_raised = rw[1] > 0 and rw[1] < rs[1]
            if left_raised and right_raised:
                return "arms_raised"

        return "standing"

    # ── Main inference method ──────────────────────────────────────────────────
    def analyze(self, frame) -> tuple[dict, object]:
        pose_results = {
            "human_present":   False,
            "people_count":    0,
            "primary_posture": "standing",
            "sustained_lying_seconds": 0.0, # 👈 TEMPORAL MEMORY FIELD
            "motion_state":    "none",
            "people_lying":    0,
            "people_crouching": 0,
            "posture_breakdown": [],
        }

        results = self.model.predict(frame, conf=POSE_CONF_THRESHOLD, verbose=False)

        if not results or results[0].keypoints is None:
            return pose_results, frame

        raw_keypoints = results[0].keypoints.data.cpu().numpy()  # (N, 17, 3)

        valid_people = [
            person for person in raw_keypoints
            if sum(1 for kp in person if kp[2] > KP_VISIBILITY_MIN) >= MIN_VISIBLE_KEYPOINTS
        ]

        num_people = len(valid_people)
        if num_people == 0:
            annotated_frame = results[0].plot()
            return pose_results, annotated_frame

        pose_results["human_present"] = True
        pose_results["people_count"]  = num_people
        pose_results["motion_state"]  = "low"

        posture_counts = {"lying": 0, "crouching": 0, "arms_raised": 0, "standing": 0}
        breakdown      = []

        for person_kpts in valid_people:
            posture = self._classify_posture(person_kpts)
            posture_counts[posture] += 1
            breakdown.append(posture)

        pose_results["posture_breakdown"]  = breakdown
        pose_results["people_lying"]       = posture_counts["lying"]
        pose_results["people_crouching"]   = posture_counts["crouching"]

        # ── Primary posture ──────────────────────────────
        if posture_counts["lying"] > 0:
            pose_results["primary_posture"] = "lying"
        elif posture_counts["crouching"] > 0:
            pose_results["primary_posture"] = "crouching"
        elif posture_counts["arms_raised"] > 0:
            pose_results["primary_posture"] = "arms_raised"
        else:
            pose_results["primary_posture"] = "standing"

        # 🕰️ TEMPORAL REASONING: SUSTAINED LYING CALCULATION
        self.posture_history.append(pose_results["primary_posture"])
        
        lying_frames = 0
        for p in reversed(self.posture_history):
            if p == "lying": lying_frames += 1
            else: break 
            
        pose_results["sustained_lying_seconds"] = round(lying_frames / self.FPS_ASSUMPTION, 1)

        annotated_frame = results[0].plot()
        return pose_results, annotated_frame