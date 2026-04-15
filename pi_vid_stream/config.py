import os

from dotenv import load_dotenv

load_dotenv()


def get_int(key, default):
    return int(os.getenv(key, default))


CAMERA_INDEX = get_int("CAMERA_INDEX", 0)
STREAM_PORT = get_int("STREAM_PORT", 5000)
JPEG_QUALITY = get_int("JPEG_QUALITY", 70)

# Motion Gate Settings
MOTION_HISTORY = get_int("MOTION_HISTORY", 500)
MOTION_VAR_THRESHOLD = get_int("MOTION_VAR_THRESHOLD", 50)
MOTION_PIXEL_THRESHOLD = get_int("MOTION_PIXEL_THRESHOLD", 1500)
