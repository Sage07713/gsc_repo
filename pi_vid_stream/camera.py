import cv2

class Camera:
    def __init__(self, index=0):
        self.cap = cv2.VideoCapture(index)
        if not self.cap.isOpened():
            raise RuntimeError("❌ Camera not accessible")

    def get_frame(self):
        success, frame = self.cap.read()
        if not success:
            return None
        # Resize for performance
        return cv2.resize(frame, (320, 240))

    def release(self):
        self.cap.release()
        print("📴 Camera released safely")