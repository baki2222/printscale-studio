"""
Proof of End-to-End Image Pipeline for PrintScale Studio
Tests import, actual enhancement, exact sizing, PNG alpha, DPI metadata, and reopen verification.
"""

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PIL import Image, ImageDraw

from printscale.core.geometry import DimensionMode, PhysicalUnit
from printscale.core.pipeline import JobParameters, execute_pipeline
from printscale.core.metadata import read_file_metadata
from printscale.core.enhancement import ProcessingMode
from printscale.inference.engine import InferenceEngine


def create_sample_transparent_graphic(path: str, size=(210, 240)):
    """Creates a clean transparent PNG graphic with colored shape and smooth antialiased edges."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    w, h = size
    # Draw vibrant shape with anti-aliasing
    draw.ellipse([20, 20, w - 20, h - 20], fill=(220, 50, 80, 255), outline=(255, 200, 50, 255), width=8)
    draw.rectangle([w // 4, h // 4, 3 * w // 4, 3 * h // 4], fill=(40, 160, 220, 220))
    img.save(path, format="PNG")
    return path


def test_reference_dimensions(tmp_path):
    """Check 1 & 2: 14x16 inch print produces exact 300, 400, 500, 600 DPI pixel dimensions."""
    src_file = str(tmp_path / "input_graphic.png")
    create_sample_transparent_graphic(src_file)

    expected_dims = {
        300: (4200, 4800),
        400: (5600, 6400),
        500: (7000, 8000),
        600: (8400, 9600)
    }

    for dpi, (exp_w, exp_h) in expected_dims.items():
        out_file = str(tmp_path / f"output_14x16_{dpi}dpi.png")
        params = JobParameters(
            source_path=src_file,
            output_path=out_file,
            output_format="PNG",
            dimension_mode=DimensionMode.PRINT_SIZE,
            print_width=14.0,
            print_height=16.0,
            print_unit=PhysicalUnit.INCHES,
            dpi=dpi,
            processing_mode=ProcessingMode.PRESERVE_ARTWORK
        )

        res = execute_pipeline(params)
        assert res.success, f"Failed at {dpi} DPI: {res.error_message}"
        assert res.target_width == exp_w, f"Width mismatch at {dpi} DPI: expected {exp_w}, got {res.target_width}"
        assert res.target_height == exp_h, f"Height mismatch at {dpi} DPI: expected {exp_h}, got {res.target_height}"
        assert res.has_alpha is True, f"Alpha channel lost at {dpi} DPI"

        # Verify reopen metadata
        meta = read_file_metadata(out_file)
        assert meta.width == exp_w
        assert meta.height == exp_h
        assert meta.has_alpha is True
        assert meta.dpi_x is not None
        dpi_diff = abs(meta.dpi_x - dpi)
        assert dpi_diff < 0.03, f"DPI roundtrip diff too high: {dpi_diff} at {dpi} DPI"
        print(f"PASS: 14x16 in at {dpi} DPI -> {meta.width}x{meta.height} px, verified DPI: {meta.dpi_x:.4f} (diff: {dpi_diff:.6f})")


def test_ai_model_enhancement(tmp_path):
    """Proves actual AI model inference (RealESRGAN Anime 6B) and alpha preservation."""
    src_file = create_sample_transparent_graphic(str(tmp_path / "input_graphic.png"))
    out_file = str(tmp_path / "output_ai_enhanced_300dpi.png")
    
    engine = InferenceEngine(prefer_gpu=True)
    params = JobParameters(
        source_path=src_file,
        output_path=out_file,
        output_format="PNG",
        dimension_mode=DimensionMode.PIXEL_DIMS,
        pixel_width=840,
        pixel_height=960,  # 4x of 210x240
        dpi=300,
        processing_mode=ProcessingMode.AI_ILLUSTRATION,
        prefer_gpu=True
    )

    res = execute_pipeline(params, engine=engine)
    assert res.success, f"AI pipeline failed: {res.error_message}"
    assert res.target_width == 840
    assert res.target_height == 960
    assert res.has_alpha is True
    assert "AI Illustration" in res.method_used
    print(f"PASS: AI Model Enhancement ({res.method_used}) on {res.device_used} -> {res.target_width}x{res.target_height} px")
