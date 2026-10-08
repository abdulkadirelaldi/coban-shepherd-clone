"""
Central configuration, loaded from environment variables / .env file
"""
import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


def _get_str(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name, "").strip()
    return value or default


def _get_int(name: str, default: int) -> int:
    value = _get_str(name)
    return int(value) if value is not None else default


def _get_float(name: str, default: float) -> float:
    value = _get_str(name)
    return float(value) if value is not None else default


def _get_bool(name: str, default: bool) -> bool:
    value = _get_str(name)
    return value.lower() in ("1", "true", "yes", "evet") if value is not None else default


@dataclass(frozen=True)
class Settings:
    gemini_api_key: Optional[str]
    gemini_model: str
    gemini_fallback_model: Optional[str]
    camera_index: int
    camera_width: int
    camera_height: int
    serial_port: Optional[str]
    serial_baudrate: int
    ack_timeout_sec: float
    min_confidence: float
    calibration_file: str
    safe_z_mm: float
    grasp_z_mm: float
    park_x_mm: float
    park_y_mm: float
    max_steps: int
    max_retries: int
    blur_faces: bool
    episodes_dir: str
    debug_dir: str


def load_settings() -> Settings:
    """Read all settings, falling back to sensible defaults."""
    return Settings(
        gemini_api_key=_get_str("GEMINI_API_KEY"),
        gemini_model=_get_str("GEMINI_MODEL", "gemini-3.8-flash"),
        gemini_fallback_model=_get_str("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite"),
        camera_index=_get_int("CAMERA_INDEX", 0),
        camera_width=_get_int("CAMERA_WIDTH", 640),
        camera_height=_get_int("CAMERA_HEIGHT", 480),
        serial_port=_get_str("SERIAL_PORT"),
        serial_baudrate=_get_int("SERIAL_BAUDRATE", 115200),
        ack_timeout_sec=_get_float("ACK_TIMEOUT_SEC", 10.0),
        min_confidence=_get_float("MIN_CONFIDENCE", 0.6),
        calibration_file=_get_str("CALIBRATION_FILE", "calibration.json"),
        safe_z_mm=_get_float("SAFE_Z_MM", 80.0),
        grasp_z_mm=_get_float("GRASP_Z_MM", 10.0),
        park_x_mm=_get_float("PARK_X_MM", 0.0),
        park_y_mm=_get_float("PARK_Y_MM", 30.0),
        max_steps=_get_int("MAX_STEPS", 12),
        max_retries=_get_int("MAX_RETRIES", 3),
        blur_faces=_get_bool("BLUR_FACES", True),
        episodes_dir=_get_str("EPISODES_DIR", "episodes"),
        debug_dir=_get_str("DEBUG_DIR", "debug"),
    )
