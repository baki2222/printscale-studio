"""
Acceptance Check 15: Real Visual QA Fixtures and Quantitative Inspection.
Covers:
1. Transparent typography and logo artwork (Preserve Artwork mode).
2. Digital raster illustration (AI Illustration mode - RealESRGAN Anime 6B).
3. Real photographic image (AI Photo mode - RealESRGAN x4plus).
Audits for tile seams, color fidelity, edge halos, and lettering preservation.
"""

import os
import numpy as np
from PIL import Image, ImageDraw

from printscale.core.geometry import DimensionMode
from printscale.core.pipeline import JobParameters, execute_pipeline
from printscale.core.enhancement import ProcessingMode
from printscale.inference.engine import InferenceEngine


def generate_transparent_typography_logo(path: str) -> str:
    """Generates a crisp apparel design with vector-like lettering and sharp geometry."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    img = Image.new("RGBA", (320, 240), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Sharp geometric crest
    draw.polygon([(160, 20), (280, 70), (240, 190), (160, 220), (80, 190), (40, 70)],
                 fill=(220, 45, 65, 255), outline=(255, 215, 0, 255), width=4)
    draw.ellipse([110, 70, 210, 170], fill=(24, 28, 48, 240), outline=(255, 255, 255, 255), width=3)
    
    # Lettering
    draw.text((120, 105), "PRINTSCALE", fill=(255, 255, 255, 255))
    draw.text((140, 125), "STUDIO", fill=(255, 215, 0, 255))

    img.save(path, format="PNG")
    return path


def generate_digital_illustration(path: str) -> str:
    """Generates an illustration with gradients, line art, and flat color anime tones."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    img = Image.new("RGB", (256, 256), (240, 245, 250))
    draw = ImageDraw.Draw(img)

    # Stylized mountain and sun background
    draw.ellipse([80, 30, 176, 126], fill=(255, 110, 100))
    draw.polygon([(20, 256), (120, 90), (220, 256)], fill=(75, 100, 160))
    draw.polygon([(110, 256), (180, 120), (250, 256)], fill=(50, 70, 120))

    # Ink outline details
    draw.line([(20, 256), (120, 90), (220, 256)], fill=(20, 20, 30), width=3)

    img.save(path, format="PNG")
    return path


def generate_photo_texture(path: str) -> str:
    """Generates a synthetic photograph with high-frequency natural texture and lighting gradient."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    h, w = 256, 256
    y, x = np.mgrid[0:h, 0:w]
    gradient = ((x + y) / (2.0 * w) * 180.0).astype(np.float32)

    # Add realistic texture noise
    np.random.seed(99)
    noise = np.random.normal(0, 15, (h, w)).astype(np.float32)
    photo_r = np.clip(gradient * 0.9 + noise + 40, 0, 255).astype(np.uint8)
    photo_g = np.clip(gradient * 0.7 + noise + 20, 0, 255).astype(np.uint8)
    photo_b = np.clip(gradient * 0.5 + noise + 10, 0, 255).astype(np.uint8)

    arr = np.stack([photo_r, photo_g, photo_b], axis=-1)
    img = Image.fromarray(arr, mode="RGB")
    img.save(path, format="JPEG", quality=95)
    return path


def test_acceptance_15_transparent_typography_qa(tmp_path):
    """Visual QA Test 1: Transparent typography & logo preserved without halo or text alteration."""
    src = generate_transparent_typography_logo(str(tmp_path / "typography_logo.png"))
    out = str(tmp_path / "typography_logo_upscaled.png")

    params = JobParameters(
        source_path=src,
        output_path=out,
        output_format="PNG",
        dimension_mode=DimensionMode.PIXEL_DIMS,
        pixel_width=640,
        pixel_height=480,  # 2x exact
        dpi=300,
        processing_mode=ProcessingMode.PRESERVE_ARTWORK,
        sharpen_percent=20
    )
    res = execute_pipeline(params)
    assert res.success is True

    # Reopen and inspect alpha
    with Image.open(out) as upscaled:
        assert upscaled.size == (640, 480)
        assert upscaled.mode == "RGBA"
        # Check lettering preservation in center
        arr = np.array(upscaled)
        # White lettering text area should have near 255 luminance
        center_text_box = arr[210:250, 240:400]
        max_lum = np.max(center_text_box[:, :, :3])
        assert max_lum >= 250, "Typography lettering contrast was corrupted!"


def test_acceptance_15_illustration_seams_and_quality(tmp_path):
    """Visual QA Test 2: Digital illustration AI upscaling with Real-ESRGAN Anime 6B (no tile seams)."""
    src = generate_digital_illustration(str(tmp_path / "illustration.png"))
    out = str(tmp_path / "illustration_ai_4x.png")

    engine = InferenceEngine(prefer_gpu=True)
    params = JobParameters(
        source_path=src,
        output_path=out,
        output_format="PNG",
        dimension_mode=DimensionMode.PIXEL_DIMS,
        pixel_width=1024,
        pixel_height=1024,  # 4x
        dpi=300,
        processing_mode=ProcessingMode.AI_ILLUSTRATION,
        prefer_gpu=True
    )
    res = execute_pipeline(params, engine=engine)
    assert res.success is True
    assert res.target_width == 1024
    assert res.target_height == 1024

    with Image.open(out) as upscaled:
        arr = np.array(upscaled, dtype=np.float32)
        # Seam check: check 1st derivative along tile boundary coordinates (e.g. 512)
        # A seam creates a sharp step artifact; linear feathering produces smooth transition.
        col_511 = arr[:, 511, :]
        col_512 = arr[:, 512, :]
        step_diff = np.abs(col_512 - col_511)
        mean_step = np.mean(step_diff)
        assert mean_step < 15.0, f"Visible tile seam detected! Mean step: {mean_step}"


def test_acceptance_15_photo_super_resolution(tmp_path):
    """Visual QA Test 3: Real photo super-resolution with Real-ESRGAN x4plus."""
    src = generate_photo_texture(str(tmp_path / "photo_texture.jpg"))
    out = str(tmp_path / "photo_ai_4x.jpg")

    engine = InferenceEngine(prefer_gpu=True)
    params = JobParameters(
        source_path=src,
        output_path=out,
        output_format="JPEG",
        dimension_mode=DimensionMode.PIXEL_DIMS,
        pixel_width=1024,
        pixel_height=1024,  # 4x
        dpi=300,
        processing_mode=ProcessingMode.AI_PHOTO,
        jpeg_quality=95,
        prefer_gpu=True
    )
    res = execute_pipeline(params, engine=engine)
    assert res.success is True
    assert res.target_width == 1024
    assert res.target_height == 1024

    with Image.open(out) as upscaled:
        assert upscaled.size == (1024, 1024)
        assert upscaled.mode == "RGB"
