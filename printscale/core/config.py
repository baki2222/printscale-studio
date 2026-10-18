"""
PrintScale Studio - User Configuration and Preset Management
Saves and loads user preferences in %APPDATA%/PrintScaleStudio/config.json.

Every stored value is validated on load. Missing, invalid or out-of-range values fall back to
the documented default for that field only, so one bad entry never discards the others, and
unknown keys from other versions are ignored. The file is written atomically.
"""

import os
import json
import tempfile
from dataclasses import dataclass, asdict, fields
from typing import Any, Dict, List, Optional


CONFIG_DIR_NAME = "PrintScaleStudio"
CONFIG_FILE_NAME = "config.json"

# Upload Preset Constants
UPLOAD_MAX_BYTES = 50 * 1024 * 1024  # 50 MiB (52,428,800 bytes)
UPLOAD_MAX_PIXELS_PER_AXIS = 23000
RECOMMENDED_POD_WIDTH = 4200
RECOMMENDED_POD_HEIGHT = 4800
RECOMMENDED_POD_DPI = 300

PROCESSING_MODES = ("preserve_artwork", "ai_illustration", "ai_photo")
FORMATS = ("PNG", "JPEG")
COMPOSITIONS = ("fit_pad", "crop")
CROP_ALIGNMENTS = ("center", "top", "bottom", "left", "right")
DIMENSION_MODES = ("pixel_dims", "print_size")  # metadata-only is deliberately never restored
THEMES = ("dark", "light")


@dataclass
class AppConfig:
    theme: str = "dark"
    default_dpi: int = 300
    last_output_dir: str = ""
    default_format: str = "PNG"
    default_processing_mode: str = "preserve_artwork"
    default_composition_mode: str = "fit_pad"
    prefer_gpu: bool = True
    sharpen_percent: int = 0
    jpeg_quality: int = 95
    # Added in 1.0.3
    crop_alignment: str = "center"
    dimension_mode: str = "pixel_dims"
    pixel_width: int = 4200
    pixel_height: int = 4800
    print_width: float = 14.0
    print_height: float = 16.0
    print_unit: str = "in"
    lock_aspect: bool = True
    jpeg_bg_color: List[int] = None
    window_geometry: List[int] = None       # [x, y, w, h] in logical pixels
    window_maximized: bool = False
    splitter_sizes: List[int] = None
    queue_panel_visible: bool = True
    settings_panel_visible: bool = True

    def __post_init__(self):
        if self.jpeg_bg_color is None:
            self.jpeg_bg_color = [255, 255, 255]


def _int_in(value, lo, hi) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and float(value).is_integer() and lo <= int(value) <= hi:
        return int(value)
    return None


def _float_in(value, lo, hi) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if lo <= float(value) <= hi else None


def _validators() -> Dict[str, Any]:
    return {
        "theme": lambda v: v if v in THEMES else None,
        "default_dpi": lambda v: _int_in(v, 72, 1200),
        "last_output_dir": lambda v: v if isinstance(v, str) else None,
        "default_format": lambda v: ("JPEG" if v == "JPG" else v) if v in FORMATS + ("JPG",) else None,
        "default_processing_mode": lambda v: v if v in PROCESSING_MODES else None,
        "default_composition_mode": lambda v: v if v in COMPOSITIONS else None,
        "prefer_gpu": lambda v: v if isinstance(v, bool) else None,
        "sharpen_percent": lambda v: _int_in(v, 0, 100),
        "jpeg_quality": lambda v: _int_in(v, 70, 100),
        "crop_alignment": lambda v: v if v in CROP_ALIGNMENTS else None,
        "dimension_mode": lambda v: v if v in DIMENSION_MODES else None,
        "pixel_width": lambda v: _int_in(v, 16, 30000),
        "pixel_height": lambda v: _int_in(v, 16, 30000),
        "print_width": lambda v: _float_in(v, 0.1, 500.0),
        "print_height": lambda v: _float_in(v, 0.1, 500.0),
        "print_unit": lambda v: v if v in ("in", "cm") else None,
        "lock_aspect": lambda v: v if isinstance(v, bool) else None,
        "jpeg_bg_color": lambda v: [int(c) for c in v] if isinstance(v, list) and len(v) == 3 and
                         all(_int_in(c, 0, 255) is not None for c in v) else None,
        "window_geometry": lambda v: [int(c) for c in v] if isinstance(v, list) and len(v) == 4 and
                           all(_int_in(c, -100000, 100000) is not None for c in v) and v[2] > 0 and v[3] > 0 else None,
        "window_maximized": lambda v: v if isinstance(v, bool) else None,
        "splitter_sizes": lambda v: [int(c) for c in v] if isinstance(v, list) and len(v) == 3 and
                          all(_int_in(c, 0, 100000) is not None for c in v) else None,
        "queue_panel_visible": lambda v: v if isinstance(v, bool) else None,
        "settings_panel_visible": lambda v: v if isinstance(v, bool) else None,
    }


def validate_config_dict(data: Dict[str, Any]) -> (AppConfig, List[str]):
    """Builds an AppConfig from raw JSON data. Returns (config, list of fields that fell back)."""
    defaults = AppConfig()
    values, fallbacks = {}, []
    checks = _validators()
    for f in fields(AppConfig):
        if f.name not in data:
            continue
        ok = checks[f.name](data[f.name])
        if ok is None:
            fallbacks.append(f.name)
        else:
            values[f.name] = ok
    cfg = AppConfig(**{**asdict(defaults), **values})
    return cfg, fallbacks


def get_app_data_dir() -> str:
    """Returns the persistent application data directory for PrintScale Studio."""
    app_data = os.getenv("APPDATA")
    if not app_data:
        app_data = os.path.expanduser("~")
    target_dir = os.path.join(app_data, CONFIG_DIR_NAME)
    os.makedirs(target_dir, exist_ok=True)
    return target_dir


def get_config_file_path() -> str:
    return os.path.join(get_app_data_dir(), CONFIG_FILE_NAME)


def load_config() -> AppConfig:
    path = get_config_file_path()
    if not os.path.isfile(path):
        return AppConfig()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return AppConfig()
        cfg, _ = validate_config_dict(data)
        return cfg
    except Exception:
        return AppConfig()


def save_config(config: AppConfig) -> bool:
    """Atomic write (temp file + replace) so a crash never leaves a truncated config."""
    try:
        path = get_config_file_path()
        fd, tmp = tempfile.mkstemp(prefix=".config_", suffix=".tmp", dir=os.path.dirname(path))
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(asdict(config), f, indent=2)
        os.replace(tmp, path)
        return True
    except Exception:
        return False
