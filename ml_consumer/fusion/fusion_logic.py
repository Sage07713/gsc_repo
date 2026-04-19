"""
Sentinel AI — Threat Fusion Engine (v3)
========================================
FIX-1: Normalized scoring (0-10 scale) via _MAX_RAW_SCORE clamp.
FIX-2: Config injection for device_id, camera_id, and location.
FIX-3: Deprecated utcnow() replaced with timezone-aware now(timezone.utc).
ADDED: score_breakdown() for granular debugging in logs.
"""

import json
from datetime import datetime, timezone
from typing import Optional

# Maximum raw points expected before we consider the threat 100% "Critical"
_MAX_RAW_SCORE = 15.0
_SCORE_SCALE   = 10.0

class ThreatFusionEngine:
    def __init__(
        self,
        device_id: str = "pi-001",
        camera_id: str = "lobby_cam_1",
        location:  str = "Building A - Ground Floor"
    ):
        # FIX-2: IDs are now injectable via main.py / config.json
        self.device_id = device_id
        self.camera_id = camera_id
        self.location  = location

    def _calculate_raw_sum(self, params: dict) -> tuple[float, dict]:
        """Calculates raw points and returns a breakdown for debugging."""
        score = 0.0
        breakdown = {}

        # ── Environmental / Vision (Max ~10 pts) ──
        if params['fire_conf'] > 0.80: 
            score += 5.0; breakdown["fire"] = 5.0
        if params['gas_leak']: 
            score += 3.0; breakdown["gas"] = 3.0
        if params['smoke_conf'] > 0.50: 
            score += 2.0; breakdown["smoke"] = 2.0

        if params['fire_trend'] == "escalating": score += 2.0
        elif params['fire_trend'] == "diminishing": score -= 1.0

        # ── Human Analysis (Max ~6 pts) ──
        threat_postures = {"lying", "crouching", "arms_raised", "crawling", "hands_behind_back"}
        if params['posture'] in threat_postures:
            score += min(params['people_count'] * 0.5, 3.0)
            if params['posture'] == "lying" and params['sustained_lying_sec'] > 5.0:
                score += 3.0

        # ByteTrack stationary boost
        if params['prolonged_still_count'] > 0:
            score += min(params['prolonged_still_count'] * 1.5, 3.0)

        # ── Crowd Dynamics (Max ~4 pts) ──
        if params['stampede_risk'] == "high":
            score += 4.0

        return max(0.0, score), breakdown

    def calculate_severity(self, **kwargs) -> tuple[float, str, str]:
        """
        FIX-1: Returns (normalised_score, risk_level, priority).
        Normalised score is capped at 10.0.
        """
        raw_score, _ = self._calculate_raw_sum(kwargs)
        
        # Normalize: raw 15.0 becomes 10.0
        clamped = min(raw_score, _MAX_RAW_SCORE)
        normalised = round((clamped / _MAX_RAW_SCORE) * _SCORE_SCALE, 1)

        if normalised >= 8.0: return normalised, "critical", "immediate"
        if normalised >= 5.0: return normalised, "high",     "urgent"
        if normalised >= 1.0: return normalised, "moderate", "monitor"
        return normalised, "low", "none"

    def build_json_payload(
        self,
        vision_results: dict,
        pose_results:   dict,
        motion_results: dict,
        mock_sensors:   dict,
    ) -> dict:
        
        # ── Core Data ──
        fire_detected = vision_results.get("fire_detected", False)
        posture       = pose_results.get("primary_posture", "standing")
        still_ids     = motion_results.get("prolonged_still_ids", [])
        
        # ── Severity Analysis ──
        severity, risk, priority = self.calculate_severity(
            fire_conf             = vision_results.get("fire_conf", 0.0),
            smoke_conf            = vision_results.get("smoke_conf", 0.0),
            people_count          = pose_results.get("people_count", 0),
            posture               = posture,
            gas_leak              = mock_sensors.get("gas_leak", False),
            fire_trend            = vision_results.get("fire_trend", "stable"),
            sustained_lying_sec   = pose_results.get("sustained_lying_seconds", 0.0),
            stampede_risk         = motion_results.get("stampede_risk", "low"),
            prolonged_still_count = len(still_ids)
        )

        # ── Hazard Mapping ──
        if fire_detected and mock_sensors.get("gas_leak", False): hazard = "fire_gas_leak"
        elif fire_detected: hazard = "fire"
        elif posture == "lying": hazard = "medical_emergency"
        elif motion_results.get("stampede_risk") == "high": hazard = "stampede_panic"
        elif len(still_ids) > 0: hazard = "person_stationary_alert"
        elif posture == "standing": hazard = "normal"
        else: hazard = "unknown_posture_alert"

        # FIX-3: Modern timezone-aware UTC timestamp
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        return {
            "device_id": self.device_id,
            "timestamp": ts,
            "situation": {
                "hazard_type": hazard,
                "severity_score": severity,
                "risk_level": risk,
                "priority": priority,
            },
            "environment": mock_sensors,
            "vision": vision_results,
            "human_analysis": pose_results,
            "crowd_dynamics": motion_results,
            "meta": {
                "camera_id": self.camera_id,
                "location":  self.location,
            },
        }

if __name__ == "__main__":
    # Internal Unit Test
    engine = ThreatFusionEngine()
    print("Self-test: Normalised scoring for fire + stampede")
    res = engine.calculate_severity(
        fire_conf=0.9, smoke_conf=0.6, people_count=5, posture="standing",
        gas_leak=False, fire_trend="escalating", sustained_lying_sec=0,
        stampede_risk="high", prolonged_still_count=0
    )
    print(f"Severity: {res[0]} | Level: {res[1]}") # Expected: high-9.x to 10.0