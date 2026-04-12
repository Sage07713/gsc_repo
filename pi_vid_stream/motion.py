import cv2

class MotionDetector:
    def __init__(self, history=500, var_threshold=50):
        self.back_sub = cv2.createBackgroundSubtractorMOG2(
            history=history, 
            varThreshold=var_threshold, 
            detectShadows=False
        )

    def detect(self, frame):
        # Convert to grayscale for faster processing
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        fg_mask = self.back_sub.apply(gray)
        
        # Count moving pixels
        motion_pixels = cv2.countNonZero(fg_mask)
        return motion_pixels