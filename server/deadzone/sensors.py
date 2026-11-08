"""Sensor geometry shared by IO, onboard exploration and the camera renderer."""

import math

THERMAL_RANGE = 5.0
THERMAL_FOV = math.radians(120)
CAMERA_HEIGHT = 0.4


def camera_config():
    return {
        "enabled": True,
        "range_m": THERMAL_RANGE,
        "fov_rad": THERMAL_FOV,
        "height_m": CAMERA_HEIGHT,
    }
