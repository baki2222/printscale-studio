"""
Acceptance Checks 6 & 7: Aspect Ratio Preservation, Canvas Composition, and Exact AI Sizing.
"""

from PIL import Image

from printscale.core.geometry import (
    DimensionMode, CompositionMode, CropAlignment
)
from printscale.core.pipeline import JobParameters, execute_pipeline
from printscale.core.enhancement import ProcessingMode
from printscale.inference.engine import InferenceEngine


def test_acceptance_6_aspect_ratio_fit_with_padding(tmp_path):
    """
    Check 6: Aspect-ratio mismatch uses visible padding with no silent distortion.
    """
    src_file = str(tmp_path / "square_src.png")
    out_file = str(tmp_path / "padded_out.png")

    # 100x100 square source
    im = Image.new("RGBA", (100, 100), (255, 100, 0, 255))
    im.save(src_file, format="PNG")

    # Target is 200 x 400 (aspect 1:2)
    params = JobParameters(
        source_path=src_file,
        output_path=out_file,
        output_format="PNG",
        dimension_mode=DimensionMode.PIXEL_DIMS,
        pixel_width=200,
        pixel_height=400,
        dpi=300,
        composition_mode=CompositionMode.FIT_PAD,
        processing_mode=ProcessingMode.PRESERVE_ARTWORK
    )
    res = execute_pipeline(params)
    assert res.success is True
    assert res.target_width == 200
    assert res.target_height == 400

    # Content must remain square (200 x 200), centered with 100px padding top and bottom
    with Image.open(out_file) as out_im:
        alpha = out_im.getchannel("A")
        # Top padding (y=50, x=100) must be transparent (alpha 0)
        assert alpha.getpixel((100, 50)) == 0, "Top padding is not transparent!"
        # Center (y=200, x=100) must be opaque (alpha 255)
        assert alpha.getpixel((100, 200)) == 255, "Center content missing!"
        # Bottom padding (y=350, x=100) must be transparent (alpha 0)
        assert alpha.getpixel((100, 350)) == 0, "Bottom padding is not transparent!"


def test_acceptance_6_explicit_crop(tmp_path):
    """
    Check 6: Explicit crop mode covers target canvas without distortion.
    """
    src_file = str(tmp_path / "rect_src.png")
    out_file = str(tmp_path / "crop_out.png")

    # 100x200 source (aspect 1:2)
    im = Image.new("RGBA", (100, 200), (0, 150, 255, 255))
    im.save(src_file, format="PNG")

    # Target is 300 x 300 (square)
    params = JobParameters(
        source_path=src_file,
        output_path=out_file,
        output_format="PNG",
        dimension_mode=DimensionMode.PIXEL_DIMS,
        pixel_width=300,
        pixel_height=300,
        dpi=300,
        composition_mode=CompositionMode.CROP,
        crop_alignment=CropAlignment.CENTER,
        processing_mode=ProcessingMode.PRESERVE_ARTWORK
    )
    res = execute_pipeline(params)
    assert res.success is True
    assert res.target_width == 300
    assert res.target_height == 300


def test_acceptance_7_exact_target_dimensions_after_ai_inference(tmp_path):
    """
    Check 7: Exact target dimensions are achieved after AI inference and final sizing.
    Tests an arbitrary non-multiple size (e.g. 753 x 887 pixels) from a 200x220 source.
    """
    src_file = str(tmp_path / "src_small.png")
    out_file = str(tmp_path / "src_ai_exact.png")

    im = Image.new("RGB", (200, 220), (100, 150, 200))
    im.save(src_file, format="PNG")

    engine = InferenceEngine(prefer_gpu=True)
    target_w, target_h = 753, 887

    params = JobParameters(
        source_path=src_file,
        output_path=out_file,
        output_format="PNG",
        dimension_mode=DimensionMode.PIXEL_DIMS,
        pixel_width=target_w,
        pixel_height=target_h,
        dpi=300,
        processing_mode=ProcessingMode.AI_ILLUSTRATION,
        prefer_gpu=True
    )
    res = execute_pipeline(params, engine=engine)
    assert res.success is True
    assert res.target_width == target_w
    assert res.target_height == target_h

    # Reopen file and verify exact pixel dimensions
    with Image.open(out_file) as reloaded:
        assert reloaded.size == (target_w, target_h), f"Expected {(target_w, target_h)}, got {reloaded.size}"
