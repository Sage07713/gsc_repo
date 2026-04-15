import json
from datetime import datetime

class ThreatFusionEngine:
    def __init__(self):
        self.device_id = "pi-001"
        self.camera_id = "lobby_cam_1"
        self.location = "Building A - Ground Floor"

    def calculate_severity(self, fire_conf, smoke_conf, people_count, posture, gas_leak, fire_trend, sustained_lying_sec,stampede_risk):
        # A dynamic algorithm to determine the risk level for Gemini
        score = 0.0
        
        # Environmental / Vision Threats
        if fire_conf > 0.80: score += 5.0
        if gas_leak: score += 3.0
        if smoke_conf > 0.50: score += 2.0 
        
        # 🕰️ TEMPORAL BOOST: Dynamic Fire Tracking
        if fire_trend == "escalating": 
            score += 2.0 
        elif fire_trend == "diminishing":
            score -= 1.0 # 👈 De-escalate if the fire is shrinking
        
        # Crowd-scaled posture threat
        if posture in ["lying", "crouching", "arms_raised"] and people_count > 0:
            score += min(people_count * 0.5, 3.0) 
            
            # 🕰️ TEMPORAL BOOST: Verified Medical Emergency
            if posture == "lying" and sustained_lying_sec > 5.0:
                score += 3.0 
        
        # 🏃‍♂️ NEW: Stampede Threat
        if stampede_risk == "high" and people_count > 2:
            score += 4.0 # High panic in a crowd is extremely dangerous
        
        # Ensure score doesn't drop below 0
        score = max(0.0, score)
        
        if score >= 8.0: return score, "critical", "immediate"
        if score >= 5.0: return score, "high", "urgent"
        return score, "moderate", "monitor"

    def build_json_payload(self, vision_results, pose_results, motion_results,mock_sensors):
        # 1. Extract Vision Data
        fire_detected = vision_results.get("fire_detected", False)
        fire_trend = vision_results.get("fire_trend", "stable")
        
        # 2. Extract Pose Human Data
        people_count = pose_results.get("people_count", 0)
        posture = pose_results.get("primary_posture", "standing")
        sustained_lying_seconds = pose_results.get("sustained_lying_seconds", 0.0)
        
        # 🏃‍♂️ Extract Motion Data
        stampede_risk = motion_results.get("stampede_risk", "low")
        
        # 3. Calculate Risk
        severity, risk, priority = self.calculate_severity(
            vision_results.get("fire_conf", 0.0), 
            vision_results.get("smoke_conf", 0.0),
            people_count, 
            posture, 
            mock_sensors["gas_leak"],
            fire_trend,
            sustained_lying_seconds,
            stampede_risk
        )
        
        # 4. Smart Hazard Type Flagging 👈 THE GRANULAR UPDATE
        if fire_detected and mock_sensors["gas_leak"]:
            hazard = "fire_gas_leak"
        elif fire_detected:
            hazard = "fire"
        elif stampede_risk == "high": 
            hazard = "stampede_panic" # 👈 NEW
        elif mock_sensors["gas_leak"]:
            hazard = "gas_leak"
        elif posture == "lying":
            hazard = "medical_emergency"
        elif posture == "crouching":
            hazard = "panic"
        elif posture == "arms_raised":
            hazard = "distress_signal"
        else:
            hazard = "normal"

        # 5. Construct the Final JSON schema
        payload = {
            "device_id": self.device_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "environment": mock_sensors,
            "vision": {
                "fire_detected": fire_detected,
                "fire_confidence": vision_results.get("fire_conf", 0.0),
                "smoke_detected": vision_results.get("smoke_detected", False),
                "smoke_confidence": vision_results.get("smoke_conf", 0.0),
                "fire_spread_rate": vision_results.get("fire_spread_rate", 0.0),
                "fire_trend": fire_trend 
            },
            "human_analysis": {
                "human_present": people_count > 0,
                "people_count": people_count,
                "posture": posture,
                "sustained_lying_seconds": sustained_lying_seconds, 
                "motion_state": pose_results.get("motion_state", "none")
            },
            # 🏃‍♂️ NEW BLOCK FOR GEMINI
            "crowd_dynamics": {
                "avg_motion_magnitude": motion_results.get("avg_motion_magnitude", 0.0),
                "panic_detected": motion_results.get("panic_detected", False),
                "stampede_risk": stampede_risk
            },

            "situation": {
                "hazard_type": hazard,
                "severity_score": round(severity, 1), 
                "risk_level": risk,
                "priority": priority
            },
            "meta": {
                "camera_id": self.camera_id,
                "location": self.location
            }
        }
        return payload

# --- Quick Test ---
if __name__ == "__main__":
    fusion = ThreatFusionEngine()
    
    mock_vision = {
        "fire_detected": False, "fire_conf": 0.0,
        "smoke_detected": False, "smoke_conf": 0.0,
        "fire_spread_rate": 0.0, "fire_trend": "stable"
    }
    mock_pose = {
        "people_count": 1, 
        "primary_posture": "lying", # Let's test the medical emergency!
        "sustained_lying_seconds": 6.0
    }
    mock_motion = {
        "avg_motion_magnitude": 0.0,
        "panic_detected": False,
        "stampede_risk": "low"
    }
    mock_env = {"temperature_c": 72, "gas_leak": False, "abnormal_sound": False}
    
    final_json = fusion.build_json_payload(mock_vision, mock_pose,mock_motion, mock_env)
    print(json.dumps(final_json, indent=2))