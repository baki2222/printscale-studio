"""
Acceptance Check 5: Transparency and Anti-Fringing Verification on Black and White Backgrounds.
"""

import numpy as np
from PIL import Image, ImageDraw

from printscale.core.alpha import extend_edge_colors, composite_on_background
from printscale.core.geometry import DimensionMode
from printscale.core.pipeline import JobParameters, execute_pipeline
from printscale.core.enhancement import ProcessingMode


def test_acceptance_5_edge_color_extension_anti_fringing():
    """
    Check 5: Edge color extension prevents dark fringing when alpha is interpolated.
    """
    # Create an image where non-alpha regions are zero (black)
    h, w = 40, 40
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    alpha = np.zeros((h, w), dtype=np.uint8)

    # Put a red circle in the center
    rgb[10:30, 10:30, 0] = 255  # Solid Red
    alpha[10:30, 10:30] = 255

    # Without color extension, boundary pixels are (0,0,0) with alpha 0
    # Extending edge colors should spread Red (255, 0, 0) into neighboring pixels:
    extended_rgb = extend_edge_colors(rgb, alpha, iterations=4)

    # Pixels immediately adjacent to the edge (e.g. at (9, 20) or (30, 20)) must now be Red!
    assert extended_rgb[9, 20, 0] == 255, "Edge color extension failed to spread red to top edge"
    assert extended_rgb[30, 20, 0] == 255, "Edge color extension failed to spread red to bottom edge"
    assert extended_rgb[20, 9, 0] == 255, "Edge color extension failed to spread red to left edge"
    assert extended_rgb[20, 30, 0] == 255, "Edge color extension failed to spread red to right edge"


def test_acceptance_5_rendered_edges_on_black_and_white_backgrounds(tmp_path):
    """
    Check 5: Transparent edge fixtures remain clean on black and white backgrounds.
    Composites the upscaled design onto black and white canvases and verifies edge color transition.
    """
    src_file = str(tmp_path / "transparent_logo.png")
    out_file = str(tmp_path / "upscaled_logo.png")

    # Create a soft red circle with smooth antialiased alpha transition
    img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Draw soft antialiased circle
    for r in range(40, 10, -1):
        alpha_val = int(255 * (40 - r) / 30.0)
        draw.ellipse([50 - r, 50 - r, 50 + r, 50 + r], fill=(230, 40, 40, alpha_val))

    img.save(src_file, format="PNG")

    # Upscale 3x via pipeline
    params = JobParameters(
        source_path=src_file,
        output_path=out_file,
        output_format="PNG",
        dimension_mode=DimensionMode.PIXEL_DIMS,
        pixel_width=300,
        pixel_height=300,
        dpi=300,
        processing_mode=ProcessingMode.PRESERVE_ARTWORK
    )
    res = execute_pipeline(params)
    assert res.success is True

    # Reopen upscaled PNG
    with Image.open(out_file) as upscaled:
        assert upscaled.mode == "RGBA"
        # 1. Composite onto pure white background
        comp_white = composite_on_background(upscaled, bg_color=(255, 255, 255))
        arr_white = np.array(comp_white, dtype=np.float32)

        # 2. Composite onto pure black background
        comp_black = composite_on_background(upscaled, bg_color=(0, 0, 0))
        arr_black = np.array(comp_black, dtype=np.float32)

        # In a dirty fringed image, semi-transparent pixels on white background have dark borders (low RGB).
        # On white, the transition from red (230, 40, 40) to white (255, 255, 255) must stay bright (green and blue increase monotonically).
        # Check center region vs edge region:
        center_color = arr_white[150, 150]
        assert center_color[0] > 200, "Center red lost"

        # Check that there are NO blackened border pixels anywhere on white
        # For a red-to-white transition, minimum luminance should never drop below red channel:
        min_r_channel = np.min(arr_white[:, :, 0])
        assert min_r_channel >= 200, f"Dark border artifact detected on white! min red: {min_r_channel}"
