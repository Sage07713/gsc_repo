import time
import atexit
import cv2
from flask import Flask, Response

# Import your custom modules
import config
from camera import Camera
from motion import MotionDetector

app = Flask(__name__)

# Initialize hardware and logic
try:
    cam = Camera(index=config.CAMERA_INDEX)
except RuntimeError as e:
    print(e)
    exit()

detector = MotionDetector(
    history=config.MOTION_HISTORY, 
    var_threshold=config.MOTION_VAR_THRESHOLD
)

# Register the cleanup function
atexit.register(cam.release)

def generate_frames():
    idle_print_timer = 0
    while True:
        frame = cam.get_frame()
        if frame is None:
            print("❌ Failed to grab frame")
            break
        
        # Run the frame through your motion module
        motion_pixels = detector.detect(frame)
        
        # 🛑 THE GATEKEEPER
        if motion_pixels > config.MOTION_PIXEL_THRESHOLD:
            idle_print_timer = 0 
            # Motion detected: Encode and stream
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, config.JPEG_QUALITY])
            if not ret:
                continue
            frame_bytes = buffer.tobytes()
            
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        else:
            # No motion: Save CPU
            idle_print_timer += 1
            if idle_print_timer % 30 == 0:
                print("Gate closed. Waiting for motion...")
        
        # FPS Control
        time.sleep(0.03)

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == "__main__":
    print("✅ Raspberry Pi Edge Node Active.")
    print(f"📡 Streaming server ready on port {config.STREAM_PORT}")
    app.run(host='0.0.0.0', port=config.STREAM_PORT, threaded=True)