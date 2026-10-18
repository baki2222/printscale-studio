"""
Acceptance Checks 12 & 13: Unicode Path Support (including Bangla), Destination Collisions, and Truthful Upload Preset Audits.
"""

import os
from PIL import Image

from printscale.core.geometry import DimensionMode
from printscale.core.pipeline import JobParameters, execute_pipeline
from printscale.core.batch import generate_collision_safe_filename
from printscale.core.config import UPLOAD_MAX_BYTES, UPLOAD_MAX_PIXELS_PER_AXIS
from printscale.inference.models import verify_model_integrity


def test_acceptance_12_unicode_paths_bangla_and_spaces(tmp_path):
    """
    Check 12: Unicode paths, including spaces and Bangla script (নকশা), work seamlessly for import and export.
    """
    # Create directory with Bangla characters and spaces: 'আমার নকশা টি-শার্ট'
    bangla_dir = tmp_path / "আমার নকশা টি-শার্ট"
    bangla_dir.mkdir(parents=True, exist_ok=True)

    src_file = str(bangla_dir / "লোগো ডিজাইন_logo.png")
    out_file = str(bangla_dir / "রপ্তানি_export_4200x4800_300dpi.png")

    # Create image
    im = Image.new("RGBA", (150, 150), (240, 80, 120, 255))
    im.save(src_file, format="PNG")
    assert os.path.exists(src_file)

    # Process through pipeline
    params = JobParameters(
        source_path=src_file,
        output_path=out_file,
        output_format="PNG",
        dimension_mode=DimensionMode.PIXEL_DIMS,
        pixel_width=300,
        pixel_height=300,
        dpi=300
    )
    res = execute_pipeline(params)
    assert res.success is True
    assert os.path.exists(out_file)

    # Reopen to verify
    with Image.open(out_file) as reloaded:
        assert reloaded.size == (300, 300)


def test_acceptance_12_destination_collisions(tmp_path):
    """
    Check 12: Destination collision resolution generates unique indexed filenames (_1, _2) without silent overwrite.
    """
    base_dir = str(tmp_path)
    stem = "design"
    w, h, dpi = 4200, 4800, 300

    # First file
    f0 = generate_collision_safe_filename(base_dir, stem, w, h, dpi, "png")
    assert f0.endswith("design_4200x4800_300dpi.png")
    with open(f0, "w") as f:
        f.write("first")

    # Second file must not collide
    f1 = generate_collision_safe_filename(base_dir, stem, w, h, dpi, "png")
    assert f1.endswith("design_4200x4800_300dpi_1.png")
    with open(f1, "w") as f:
        f.write("second")

    # Third file
    f2 = generate_collision_safe_filename(base_dir, stem, w, h, dpi, "png")
    assert f2.endswith("design_4200x4800_300dpi_2.png")


def test_acceptance_12_missing_model_behavior():
    """
    Check 12: Missing model ID produces clear, non-crashing error status.
    """
    ok, err_msg = verify_model_integrity("non_existent_fake_model_xyz")
    assert ok is False
    assert "Unknown model id" in err_msg


def test_acceptance_13_truthful_upload_preset_validation(tmp_path):
    """
    Check 13: Upload preset checks actual output bytes (max 50 MB) and dimensions (max 23,000 px).
    Never silently changes settings or downsizes to pass.
    """
    src_file = str(tmp_path / "test_upload.png")
    out_file = str(tmp_path / "test_upload_out.png")

    im = Image.new("RGBA", (100, 100), (255, 0, 0, 255))
    im.save(src_file, format="PNG")

    # Request 4200 x 4800 px at 300 DPI (recommended POD canvas)
    params = JobParameters(
        source_path=src_file,
        output_path=out_file,
        output_format="PNG",
        dimension_mode=DimensionMode.PIXEL_DIMS,
        pixel_width=4200,
        pixel_height=4800,
        dpi=300
    )
    res = execute_pipeline(params)
    assert res.success is True

    # 1. Output dimensions must match exactly what user asked for: 4200 x 4800
    assert res.target_width == 4200
    assert res.target_height == 4800
    assert res.target_width <= UPLOAD_MAX_PIXELS_PER_AXIS
    assert res.target_height <= UPLOAD_MAX_PIXELS_PER_AXIS

    # 2. Actual file size on disk must be under 50 MB
    actual_bytes = os.path.getsize(out_file)
    assert actual_bytes == res.file_size_bytes
    assert actual_bytes < UPLOAD_MAX_BYTES
    print(f"\n[Upload Audit] Encoded size: {actual_bytes:,} bytes (Limit: {UPLOAD_MAX_BYTES:,} bytes). Passed!")
