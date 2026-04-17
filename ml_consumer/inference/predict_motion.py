import cv2
import numpy as np

class MotionAnalyzer:
    def __init__(self):
        print("  Loading Optical Flow Engine (Crowd Dynamics)...")
        self.prev_gray = None
        self.p0 = None
        # How many points to track and how sensitive it should be
        self.feature_params = dict(maxCorners=100, qualityLevel=0.3, minDistance=7, blockSize=7)
        self.lk_params = dict(winSize=(15, 15), maxLevel=2, criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03))
        self.frame_count = 0
        print("  ✅ MotionAnalyzer ready (Stampede & Panic tracking)\n")

    def analyze(self, frame, annotated_frame):
        """
        Calculates optical flow. We pass in the annotated_frame from YOLO so we 
        can draw the motion arrows directly on top of the YOLO bounding boxes.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        motion_results = {
            "avg_motion_magnitude": 0.0,
            "panic_detected": False,
            "stampede_risk": "low"
        }

        if self.prev_gray is None:
            self.prev_gray = gray
            self.p0 = cv2.goodFeaturesToTrack(gray, mask=None, **self.feature_params)
            return motion_results, annotated_frame

        if self.p0 is not None and len(self.p0) > 0:
            p1, st, err = cv2.calcOpticalFlowPyrLK(self.prev_gray, gray, self.p0, None, **self.lk_params)
            
            if p1 is not None:
                good_new = p1[st == 1]
                good_old = self.p0[st == 1]
                
                magnitudes = []
                
                for i, (new, old) in enumerate(zip(good_new, good_old)):
                    a, b = new.ravel()
                    c, d = old.ravel()
                    
                    mag = np.sqrt((a - c)**2 + (b - d)**2)
                    magnitudes.append(mag)
                    
                    # 🔴 VISUAL WOW FACTOR: Draw red motion vectors (arrows)
                    if mag > 2.0: # Only draw if it's actual movement, not camera noise
                        annotated_frame = cv2.arrowedLine(annotated_frame, (int(c), int(d)), (int(a), int(b)), (0, 0, 255), 2, tipLength=0.4)
                
                if len(magnitudes) > 0:
                    avg_mag = np.mean(magnitudes)
                    motion_results["avg_motion_magnitude"] = round(float(avg_mag), 2)
                    
                    # 🚨 THRESHOLDS FOR PANIC
                    if avg_mag > 8.0: 
                        motion_results["panic_detected"] = True
                        motion_results["stampede_risk"] = "high"
                    elif avg_mag > 4.5:
                        motion_results["stampede_risk"] = "medium"

                # Update the tracking points for the next frame
                self.p0 = good_new.reshape(-1, 1, 2)

        # Refresh the feature points every 10 frames so we track new people entering the camera
        self.frame_count += 1
        if self.frame_count % 10 == 0 or self.p0 is None or len(self.p0) < 10:
            self.p0 = cv2.goodFeaturesToTrack(gray, mask=None, **self.feature_params)

        self.prev_gray = gray
        return motion_results, annotated_frame