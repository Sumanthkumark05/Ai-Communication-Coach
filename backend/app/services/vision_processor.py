import logging
import time
import math
import cv2
import numpy as np
from typing import Dict, Any, List, Tuple

logger = logging.getLogger("jam_analyzer")

# Global cached MediaPipe Holistic model — initialized once per server process
_holistic = None
_MAX_FRAMES = 150  # Process at most 150 sampled frames (~30 s of a 5 fps sample)

def get_holistic():
    global _holistic
    if _holistic is None:
        import mediapipe.python.solutions.holistic as mp_holistic
        logger.info("[Vision] Initializing MediaPipe Holistic model (first request)...")
        _holistic = mp_holistic.Holistic(
            static_image_mode=False,
            model_complexity=1,
            refine_face_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        logger.info("[Vision] MediaPipe Holistic model ready and cached.")
    return _holistic

def estimate_gaze_hit(left_eye_pts: List[np.ndarray], left_iris_pt: np.ndarray,
                      right_eye_pts: List[np.ndarray], right_iris_pt: np.ndarray) -> Tuple[bool, str]:
    """
    Checks if gaze is centered (looking at camera) and classifies look direction (Center, Left, Right).
    """
    left_outer, left_inner = left_eye_pts[0], left_eye_pts[1]
    left_width = np.linalg.norm(left_inner - left_outer)
    if left_width == 0:
        return False, "Unknown"
        
    left_ratio = (left_iris_pt[0] - left_outer[0]) / left_width
    
    right_inner, right_outer = right_eye_pts[0], right_eye_pts[1]
    right_width = np.linalg.norm(right_outer - right_inner)
    if right_width == 0:
        return False, "Unknown"
        
    right_ratio = (right_iris_pt[0] - right_inner[0]) / right_width

    # Gaze boundaries
    left_ok = (0.35 <= left_ratio <= 0.65)
    right_ok = (0.35 <= right_ratio <= 0.65)
    
    gaze_hit = left_ok and right_ok
    
    if gaze_hit:
        direction = "Center"
    elif left_ratio < 0.35 or right_ratio < 0.35:
        direction = "Left"
    else:
        direction = "Right"
        
    return bool(gaze_hit), direction

def estimate_head_pose(landmarks: Any, img_w: int, img_h: int) -> Tuple[float, float, float]:
    """
    Computes Euler angles (Pitch, Yaw, Roll) of the face using 6 landmark matches against generic 3D model.
    """
    # 3D model points
    model_points = np.array([
        (0.0, 0.0, 0.0),             # Nose tip
        (0.0, -330.0, -65.0),        # Chin
        (-225.0, 170.0, -135.0),     # Left eye outer corner
        (225.0, 170.0, -135.0),      # Right eye outer corner
        (-150.0, -150.0, -125.0),    # Left mouth corner
        (150.0, -150.0, -125.0)      # Right mouth corner
    ], dtype=np.float32)

    # Landmark indices for these 6 points in face mesh
    key_indices = [4, 152, 33, 263, 61, 291]
    image_points_list = []
    
    # Check if landmarks has enough items
    if hasattr(landmarks, 'landmark') and len(landmarks.landmark) > max(key_indices):
        for idx in key_indices:
            lm = landmarks.landmark[idx]
            image_points_list.append((lm.x * img_w, lm.y * img_h))
    else:
        return 0.0, 0.0, 0.0

    image_points = np.array(image_points_list, dtype=np.float32)

    focal_length = img_w
    center = (img_w / 2, img_h / 2)
    camera_matrix = np.array([
        [focal_length, 0, center[0]],
        [0, focal_length, center[1]],
        [0, 0, 1]
    ], dtype=np.float32)
    
    dist_coeffs = np.zeros((4, 1), dtype=np.float32)

    success, rvec, tvec = cv2.solvePnP(
        model_points, image_points, camera_matrix, dist_coeffs, flags=cv2.SOLVEPNP_ITERATIVE
    )

    if not success:
        return 0.0, 0.0, 0.0

    rmat, _ = cv2.Rodrigues(rvec)

    pitch = np.arcsin(-rmat[2, 0]) * 180 / np.pi
    yaw = np.arctan2(rmat[2, 1], rmat[2, 2]) * 180 / np.pi
    roll = np.arctan2(rmat[1, 0], rmat[0, 0]) * 180 / np.pi

    return float(pitch), float(yaw), float(roll)

def process_video(video_path: str) -> Dict[str, Any]:
    """
    Processes the recording using MediaPipe Holistic (Face Mesh + Pose + Hands).
    Extracts visual behavior metrics for communication analysis.
    Uses a globally cached Holistic model and caps frame processing at _MAX_FRAMES.
    """
    import av

    logger.info(f"[Vision] Opening video for MediaPipe Holistic analysis: {video_path}")
    t0 = time.time()
    try:
        container = av.open(video_path)
        video_stream = container.streams.video[0]
    except Exception as e:
        logger.error(f"[Vision] Failed to open video file {video_path}: {e}")
        return get_fallback_metrics()
        
    width = video_stream.width
    height = video_stream.height
    avg_rate = video_stream.average_rate
    fps = float(avg_rate) if avg_rate is not None else 30.0
    
    # Process at 5 FPS to satisfy <15s/min performance target
    sample_rate = max(1, int(fps / 5))
    
    processed_count = 0
    face_detected_count = 0
    pose_detected_count = 0
    
    eye_contact_frames = 0
    gaze_counts = {"Center": 0, "Left": 0, "Right": 0, "Unknown": 0}
    
    smile_frames = 0
    good_posture_frames = 0
    
    left_hand_detected_frames = 0
    right_hand_detected_frames = 0
    hand_movement_frames = 0
    effective_gesture_frames = 0
    
    head_tilts = []
    head_jitters = []
    gaze_switches = 0
    prev_gaze_dir = None
    
    prev_left_wrist = None
    prev_right_wrist = None
    
    # Use global cached model
    holistic = get_holistic()
    
    frame_idx = 0
    for frame in container.decode(video_stream):
        if frame_idx % sample_rate == 0:
            if processed_count >= _MAX_FRAMES:
                logger.info(f"[Vision] Frame cap reached ({_MAX_FRAMES} sampled frames). Stopping early.")
                break
            processed_count += 1
            rgb_frame = frame.to_ndarray(format='rgb24')
            results = holistic.process(rgb_frame)
            
            # 1. Face Landmarks Analysis
            if results.face_landmarks:
                face_detected_count += 1
                face_lm = results.face_landmarks
                
                # Pitch, Yaw, Roll pose estimation
                pitch, yaw, roll = estimate_head_pose(face_lm, width, height)
                head_tilts.append(abs(roll))
                
                # Eye Gaze check
                gaze_ok = False
                direction = "Unknown"
                if len(face_lm.landmark) >= 478:
                    left_outer = np.array([face_lm.landmark[33].x, face_lm.landmark[33].y])
                    left_inner = np.array([face_lm.landmark[133].x, face_lm.landmark[133].y])
                    left_iris = np.array([face_lm.landmark[468].x, face_lm.landmark[468].y])
                    
                    right_inner = np.array([face_lm.landmark[362].x, face_lm.landmark[362].y])
                    right_outer = np.array([face_lm.landmark[263].x, face_lm.landmark[263].y])
                    right_iris = np.array([face_lm.landmark[473].x, face_lm.landmark[473].y])
                    
                    gaze_ok, direction = estimate_gaze_hit([left_outer, left_inner], left_iris,
                                                            [right_inner, right_outer], right_iris)
                else:
                    # Gaze Fallback based on head pose
                    gaze_ok = abs(pitch) < 10 and abs(yaw) < 10
                    direction = "Center" if gaze_ok else ("Left" if yaw > 10 else "Right")
                
                gaze_counts[direction] = gaze_counts.get(direction, 0) + 1
                if gaze_ok:
                    eye_contact_frames += 1
                
                # Count gaze direction switches (darting eyes indicator)
                if direction != prev_gaze_dir:
                    if prev_gaze_dir is not None:
                        gaze_switches += 1
                    prev_gaze_dir = direction
                
                # Smile Tracking (Expression)
                m_left = np.array([face_lm.landmark[61].x * width, face_lm.landmark[61].y * height])
                m_right = np.array([face_lm.landmark[291].x * width, face_lm.landmark[291].y * height])
                e_left = np.array([face_lm.landmark[33].x * width, face_lm.landmark[33].y * height])
                e_right = np.array([face_lm.landmark[263].x * width, face_lm.landmark[263].y * height])
                
                mouth_w = np.linalg.norm(m_right - m_left)
                face_w = np.linalg.norm(e_right - e_left)
                smile_ratio = mouth_w / face_w if face_w > 0 else 0
                
                if smile_ratio > 0.54:
                    smile_frames += 1

            # 2. Pose & Posture Analysis
            if results.pose_landmarks:
                pose_detected_count += 1
                pose_lm = results.pose_landmarks
                
                # Shoulder alignment coordinates
                left_shoulder = pose_lm.landmark[11]
                right_shoulder = pose_lm.landmark[12]
                
                shoulder_y_diff = abs(left_shoulder.y - right_shoulder.y)
                # Balanced posture if difference is low
                if shoulder_y_diff < 0.05:
                    good_posture_frames += 1

            # 3. Hand & Gesture Tracking
            # Track Left Hand
            left_hand_active = results.left_hand_landmarks is not None
            if left_hand_active:
                left_hand_detected_frames += 1
                lh_wrist = results.left_hand_landmarks.landmark[0]
                
                # Measure left hand movement
                if prev_left_wrist is not None:
                    dist = math.sqrt((lh_wrist.x - prev_left_wrist.x)**2 + (lh_wrist.y - prev_left_wrist.y)**2)
                    if dist > 0.02:
                        hand_movement_frames += 1
                prev_left_wrist = lh_wrist
                
                # Check gesture effectiveness (hands raised above chest / shoulder line)
                if results.pose_landmarks:
                    avg_shoulder_y = (results.pose_landmarks.landmark[11].y + results.pose_landmarks.landmark[12].y) / 2
                    if lh_wrist.y < (avg_shoulder_y + 0.15):
                        effective_gesture_frames += 1
                        
            # Track Right Hand
            right_hand_active = results.right_hand_landmarks is not None
            if right_hand_active:
                right_hand_detected_frames += 1
                rh_wrist = results.right_hand_landmarks.landmark[0]
                
                # Measure right hand movement
                if prev_right_wrist is not None:
                    dist = math.sqrt((rh_wrist.x - prev_right_wrist.x)**2 + (rh_wrist.y - prev_right_wrist.y)**2)
                    if dist > 0.02:
                        hand_movement_frames += 1
                prev_right_wrist = rh_wrist
                
                # Check gesture effectiveness
                if results.pose_landmarks:
                    avg_shoulder_y = (results.pose_landmarks.landmark[11].y + results.pose_landmarks.landmark[12].y) / 2
                    if rh_wrist.y < (avg_shoulder_y + 0.15):
                        effective_gesture_frames += 1

        frame_idx += 1
        
    container.close()
    # NOTE: Do NOT close the global holistic model — it is reused across requests
    elapsed_vision = time.time() - t0
    logger.info(f"[Vision] MediaPipe processing finished in {elapsed_vision:.2f}s — {processed_count} frames analysed.")
    
    # Fallback to defaults if no face or pose was detected
    if face_detected_count == 0:
        return get_fallback_metrics()
        
    # Calculate Gaze and Eye contact ratios
    eye_pct = float((eye_contact_frames / face_detected_count) * 100)
    look_away_pct = 100.0 - eye_pct
    
    gaze_dist = {}
    for d, val in gaze_counts.items():
        gaze_dist[d] = float((val / face_detected_count) * 100)
        
    # Expression Ratios
    smile_freq = float((smile_frames / face_detected_count) * 100)
    
    # Posture Score calculation
    posture_pct = float((good_posture_frames / max(1, pose_detected_count)) * 100) if pose_detected_count > 0 else 50.0
    
    # Hand metrics
    hand_frames_total = max(1, left_hand_detected_frames + right_hand_detected_frames)
    hand_movement_freq = float((hand_movement_frames / face_detected_count) * 100)
    gesture_effectiveness = float((effective_gesture_frames / hand_frames_total) * 100)
    hand_detection_rate = float((hand_frames_total / (2 * face_detected_count)) * 100)
    
    # Gaze darting nervousness penalty
    nervousness = min(100.0, gaze_switches * 8.0 + (np.std(head_tilts) * 200.0 if head_tilts else 0.0))
    neutral_score = max(0.0, 100.0 - smile_freq - nervousness)
    confidence_expression_score = max(0.0, 100.0 - nervousness)

    # Head Pose Euler average Roll
    avg_tilt = float(np.mean(head_tilts)) if head_tilts else 0.0
    head_stability = max(0.0, 100.0 - (avg_tilt * 3.0) - (np.var(head_tilts) * 50.0 if head_tilts else 0.0))

    # Diagnostics information
    diagnostics = {
        "frames_processed": processed_count,
        "face_detection_rate": round(float((face_detected_count / processed_count) * 100), 1)
    }

    return {
        "eye_contact_percentage": eye_pct,
        "look_away_percentage": look_away_pct,
        "gaze_direction_distribution": gaze_dist,
        
        # Expressions
        "expressions": {
            "confidence": round(confidence_expression_score, 1),
            "neutral": round(neutral_score, 1),
            "nervousness": round(nervousness, 1),
            "happiness": round(smile_freq, 1)
        },
        
        # Body Language
        "posture_score": posture_pct,
        "head_stability": head_stability,
        "hand_movement_frequency": hand_movement_freq,
        "gesture_effectiveness": gesture_effectiveness,
        "hand_detection_rate": hand_detection_rate,
        
        # Fallback fields mapping to maintain DB schema compat
        "head_tilt_average": avg_tilt,
        "head_movement_variance": float(np.var(head_tilts)) if head_tilts else 0.0,
        "smile_frequency": smile_freq,
        "posture_stability": posture_pct,
        
        # Diagnostics
        "diagnostics": diagnostics
    }

def get_fallback_metrics() -> Dict[str, Any]:
    return {
        "eye_contact_percentage": 50.0,
        "look_away_percentage": 50.0,
        "gaze_direction_distribution": {"Center": 50.0, "Left": 25.0, "Right": 25.0},
        "expressions": {
            "confidence": 60.0,
            "neutral": 30.0,
            "nervousness": 10.0,
            "happiness": 10.0
        },
        "posture_score": 60.0,
        "head_stability": 70.0,
        "hand_movement_frequency": 20.0,
        "gesture_effectiveness": 40.0,
        "hand_detection_rate": 20.0,
        "head_tilt_average": 0.0,
        "head_movement_variance": 0.0,
        "smile_frequency": 10.0,
        "posture_stability": 60.0,
        "diagnostics": {
            "frames_processed": 0,
            "face_detection_rate": 0.0
        }
    }
