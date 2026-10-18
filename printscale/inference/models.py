"""
PrintScale Studio - Model Registry and Verification
Maintains verified model records, pinned SHA-256 hashes, licenses, and file resolution.
"""

import os
import sys
import hashlib
from dataclasses import dataclass
from typing import Dict, Optional, List, Tuple


@dataclass
class ModelInfo:
    model_id: str
    name: str
    category: str
    scale: int
    filename: str
    sha256: str
    license_name: str
    source_url: str
    description: str
    size_bytes: int


MODEL_REGISTRY: Dict[str, ModelInfo] = {
    "illustration_anime_6b": ModelInfo(
        model_id="illustration_anime_6b",
        name="Real-ESRGAN Anime 6B",
        category="AI Illustration",
        scale=4,
        filename="RealESRGAN_x4plus_anime_6B.onnx",
        sha256="6b04d9c09399e24f2ad6171246f2c21da3571383561f46a4bb93b1f4c18af40f",
        license_name="BSD-3-Clause",
        source_url="https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth",
        description="Optimized for raster illustrations, clean line art, and flat color designs. Avoids noisy photographic textures.",
        size_bytes=17_939_979
    ),
    "photo_x4plus": ModelInfo(
        model_id="photo_x4plus",
        name="Real-ESRGAN x4plus",
        category="AI Photo",
        scale=4,
        filename="RealESRGAN_x4plus.onnx",
        sha256="ec45cb356739c0086893db4e6fcfefb3dc0af087816a13175cae2386532db8ff",
        license_name="BSD-3-Clause",
        source_url="https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
        description="Optimized for real-world photographic textures, portraits, apparel products, and natural scenes.",
        size_bytes=67_051_654
    )
}


def compute_file_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest().lower()


def get_candidate_model_dirs() -> List[str]:
    """
    Returns candidate directories where model files reside.
    When frozen, strictly limits resolution to the application's own bundle
    and user APPDATA, never falling back to development paths.
    """
    candidates = []
    
    if getattr(sys, "frozen", False):
        # 1. PyInstaller frozen bundled directory
        if hasattr(sys, "_MEIPASS"):
            candidates.append(os.path.join(sys._MEIPASS, "models"))
        exe_dir = os.path.dirname(sys.executable)
        candidates.append(os.path.join(exe_dir, "models"))
        candidates.append(os.path.join(exe_dir, "_internal", "models"))
    else:
        # Development mode only: an explicit model folder (scripts/fetch_models.py --dest) comes first
        if os.getenv("PRINTSCALE_MODEL_DIR"):
            candidates.append(os.getenv("PRINTSCALE_MODEL_DIR"))
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        candidates.append(os.path.join(base_dir, "models"))
        candidates.append(os.path.join(os.getcwd(), "models"))

    # User APPDATA directory
    app_data = os.getenv("APPDATA")
    if app_data:
        candidates.append(os.path.join(app_data, "PrintScaleStudio", "models"))

    return [d for d in candidates if d]


def find_model_path(model_id: str) -> Optional[str]:
    """Finds the model file path and verifies its existence."""
    info = MODEL_REGISTRY.get(model_id)
    if not info:
        return None

    for d in get_candidate_model_dirs():
        target = os.path.join(d, info.filename)
        if os.path.isfile(target):
            return target
            
    return None


def verify_model_integrity(model_id: str) -> Tuple[bool, str]:
    """
    Verifies that the model file exists and matches its pinned SHA-256 hash.
    """
    info = MODEL_REGISTRY.get(model_id)
    if not info:
        return False, f"Unknown model id: {model_id}"

    path = find_model_path(model_id)
    if not path:
        return False, f"Model file not found: {info.filename}"

    actual_hash = compute_file_sha256(path)
    if actual_hash != info.sha256:
        return False, f"SHA-256 mismatch for {info.filename}: expected {info.sha256}, got {actual_hash}"

    return True, path
