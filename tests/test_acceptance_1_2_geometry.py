"""
Acceptance Checks 1 & 2: Mathematical Precision of DPI, Print Sizes, and Pixel Dimensions.
"""

import pytest
from printscale.core.geometry import (
    PhysicalUnit, calculate_target_pixels, calculate_physical_size
)


def test_acceptance_1_14x16_exact_dimensions():
    """
    Check 1: A 14 x 16 inch target produces all four exact dimensions:
    - 300 DPI = 4200 x 4800 pixels
    - 400 DPI = 5600 x 6400 pixels
    - 500 DPI = 7000 x 8000 pixels
    - 600 DPI = 8400 x 9600 pixels
    """
    pw, ph = 14.0, 16.0
    unit = PhysicalUnit.INCHES

    assert calculate_target_pixels(pw, ph, 300, unit) == (4200, 4800)
    assert calculate_target_pixels(pw, ph, 400, unit) == (5600, 6400)
    assert calculate_target_pixels(pw, ph, 500, unit) == (7000, 8000)
    assert calculate_target_pixels(pw, ph, 600, unit) == (8400, 9600)


def test_acceptance_2_fixed_pixel_canvas_dpi_updates():
    """
    Check 2: A fixed 4200 x 4800 pixel target stays unchanged when DPI changes;
    its reported physical size updates correctly.
    """
    fixed_w, fixed_h = 4200, 4800

    # At 300 DPI -> 14 x 16 inches
    in_w_300, in_h_300 = calculate_physical_size(fixed_w, fixed_h, 300, PhysicalUnit.INCHES)
    assert pytest.approx(in_w_300, rel=1e-5) == 14.0
    assert pytest.approx(in_h_300, rel=1e-5) == 16.0

    # At 400 DPI -> 10.5 x 12.0 inches
    in_w_400, in_h_400 = calculate_physical_size(fixed_w, fixed_h, 400, PhysicalUnit.INCHES)
    assert pytest.approx(in_w_400, rel=1e-5) == 10.5
    assert pytest.approx(in_h_400, rel=1e-5) == 12.0

    # At 500 DPI -> 8.4 x 9.6 inches
    in_w_500, in_h_500 = calculate_physical_size(fixed_w, fixed_h, 500, PhysicalUnit.INCHES)
    assert pytest.approx(in_w_500, rel=1e-5) == 8.4
    assert pytest.approx(in_h_500, rel=1e-5) == 9.6

    # At 600 DPI -> 7.0 x 8.0 inches
    in_w_600, in_h_600 = calculate_physical_size(fixed_w, fixed_h, 600, PhysicalUnit.INCHES)
    assert pytest.approx(in_w_600, rel=1e-5) == 7.0
    assert pytest.approx(in_h_600, rel=1e-5) == 8.0


def test_centimeter_to_pixel_conversion():
    """Tests metric centimeters conversion precision."""
    # 25.4 cm at 300 DPI = 10 inches * 300 = 3000 pixels
    assert calculate_target_pixels(25.4, 50.8, 300, PhysicalUnit.CENTIMETERS) == (3000, 6000)
