import cv2
import asyncio
import websockets
import base64
import json
import time

# Import your modules
# (Assuming you wrap your logic in simple classes in these files)
from inference.predict_vision import VisionAnalyzer
from inference.predict_pose import PoseAnalyzer
from fusion.fusion_logic import ThreatFusionEngine
from inference.predict_motion import MotionAnalyzer

# Configuration
PI_STREAM_URL = "http://192.168.X.X:5000/video_feed" # Replace with Pi's IP
GO_BACKEND_URL = "ws://localhost:3000/ws/stream"

def get_mock_sensors():
    """Simulates real-time IoT sensor data for the MVP"""
    return {
        "temperature_c": 78,
        "gas_leak": True,
        "abnormal_sound": True
    }

async def run_sentinel_ml():
    print("🚀 Initializing Sentinel ML Consumer...")
    
    # Initialize the AI engines (Loads weights into RAM once)
    vision_engine = VisionAnalyzer(weights_path="ml_consumer/weights/fire_model.pt")
    pose_engine = PoseAnalyzer()
    fusion_engine = ThreatFusionEngine()
    motion_engine = MotionAnalyzer()
    
    # Connect to the Go Backend
    # async with websockets.connect(GO_BACKEND_URL) as websocket:
    websocket = None
    print("⚠️ Backend disabled. Running ML pipeline only.")
        # print(f"✅ Connected to Go Core Backend at {GO_BACKEND_URL}")
        # print(f"📡 Connecting to Raspberry Pi stream at {PI_STREAM_URL}...")
        
    cap = cv2.VideoCapture("ml_consumer/testing_data/yoga.mp4")
    if not cap.isOpened():
        print("⚠️ Pi not available, switching to webcam")
        cap = cv2.VideoCapture(0)
        
        if not cap.isOpened():
            print("❌ Both Pi stream and local webcam failed. Exiting.")
            return

    print("🧠 AI Pipeline Active. Analyzing live feed...")
    
    last_alert_time = 0.0
    ALERT_COOLDOWN = 2.0
    
    while True:
        ret, frame = cap.read()
        if not ret:
            await asyncio.sleep(0.5)
            continue
        
        # --- THE CORE PIPELINE ---
        
        # 1. Vision Analysis (YOLO)
        vision_results, annotated_frame = vision_engine.analyze(frame)
        
        # 2. Pose/Human Analysis (MediaPipe)
        pose_results, final_frame = pose_engine.analyze(annotated_frame)
        
        # 3.Crowd Motion Analysis
        motion_results, final_frame = motion_engine.analyze(frame, annotated_frame)
        
        # 4. Sensor Data
        sensor_data = get_mock_sensors()
        
        # 5. Data Fusion (Build the JSON)
        payload = fusion_engine.build_json_payload(
            vision_results=vision_results, 
            pose_results=pose_results, 
            motion_results=motion_results,
            mock_sensors=sensor_data
        )
        
        # 5. Add the Visual Evidence (Base64)
        # Only send to backend if severity is High or Critical to save bandwidth
        # if payload["situation"]["risk_level"] in ["high", "critical"]:
        if True:
            current_time = time.time()
            
            # 🛑 NON-BLOCKING DEBOUNCE: Only send if cooldown has passed
            if current_time - last_alert_time >= ALERT_COOLDOWN:
                print(f"🚨 THREAT DETECTED: {payload['situation']['hazard_type'].upper()}")
            
                ret, buffer = cv2.imencode('.jpg', final_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if not ret:
                    continue
                # payload["visual_evidence"] = base64.b64encode(buffer).decode('utf-8')
                payload["visual_evidence"] = "image_sent"
            
                with open("ml_consumer/outputs/latest_alert.json", "w") as f:
                    json.dump(payload, f, indent=2)
            
                # Fire to Go server
                # await websocket.send(json.dumps(payload))
                # print("📤 Payload:", payload)
                print("VISION:", vision_results)
                print("POSE:", pose_results)
                print("📤 Payload sent to Go Backend!")
                
                # 🛑 CRITICAL FIX: Update the timestamp so it waits 2 seconds before sending again
                last_alert_time = current_time 
            
        
        # Show the live AI view on your laptop screen for the demo
        cv2.imshow("Sentinel ML Dashboard", final_frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
        
        await asyncio.sleep(0.01)

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    # Start the async loop
    asyncio.run(run_sentinel_ml())