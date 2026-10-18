"""
PrintScale Studio - Geometry and Resolution Module
Mathematically precise calculations for Print DPI, physical sizes, pixel dimensions,
canvas composition (padding/crop), aspect ratios, and resource budgets.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Tuple, Optional


class DimensionMode(str, Enum):
    PRINT_SIZE = "print_size"       # Physical dimensions (in/cm) + DPI -> target pixels
    PIXEL_DIMS = "pixel_dims"       # Fixed pixels + DPI -> reported physical size
    METADATA_ONLY = "metadata_only" # No resizing; DPI metadata update only


class PhysicalUnit(str, Enum):
    INCHES = "in"
    CENTIMETERS = "cm"


class CompositionMode(str, Enum):
    FIT_PAD = "fit_pad"  # Fit within target dimensions, pad remainder with transparency/color
    CROP = "crop"        # Fill target dimensions and crop overflow with alignment


class CropAlignment(str, Enum):
    CENTER = "center"
    TOP = "top"
    BOTTOM = "bottom"
    LEFT = "left"
    RIGHT = "right"


@dataclass
class PrintResolution:
    dpi: int = 300
    unit: PhysicalUnit = PhysicalUnit.INCHES

    @staticmethod
    def inches_to_pixels(inches: float, dpi: int) -> int:
        return int(round(inches * dpi))

    @staticmethod
    def cm_to_pixels(cm: float, dpi: int) -> int:
        return int(round((cm / 2.54) * dpi))

    @staticmethod
    def pixels_to_inches(pixels: int, dpi: int) -> float:
        if dpi <= 0:
            return 0.0
        return pixels / float(dpi)

    @staticmethod
    def pixels_to_cm(pixels: int, dpi: int) -> float:
        if dpi <= 0:
            return 0.0
        return (pixels / float(dpi)) * 2.54


def calculate_target_pixels(
    width: float,
    height: float,
    dpi: int,
    unit: PhysicalUnit
) -> Tuple[int, int]:
    """
    Computes exact target integer pixel dimensions from physical print size and DPI.
    Mode A: Physical print size stays fixed when DPI changes.
    """
    if dpi <= 0:
        raise ValueError(f"DPI must be positive integer, got {dpi}")
    if width <= 0 or height <= 0:
        raise ValueError(f"Width and height must be positive, got ({width}, {height})")

    if unit == PhysicalUnit.INCHES:
        target_w = PrintResolution.inches_to_pixels(width, dpi)
        target_h = PrintResolution.inches_to_pixels(height, dpi)
    elif unit == PhysicalUnit.CENTIMETERS:
        target_w = PrintResolution.cm_to_pixels(width, dpi)
        target_h = PrintResolution.cm_to_pixels(height, dpi)
    else:
        raise ValueError(f"Unknown physical unit: {unit}")

    return max(1, target_w), max(1, target_h)


def calculate_physical_size(
    pixels_w: int,
    pixels_h: int,
    dpi: int,
    unit: PhysicalUnit
) -> Tuple[float, float]:
    """
    Computes physical print size from pixel dimensions and DPI.
    Mode B: Pixel dimensions remain fixed; changing DPI updates physical size.
    """
    if dpi <= 0:
        return 0.0, 0.0
    if unit == PhysicalUnit.INCHES:
        return PrintResolution.pixels_to_inches(pixels_w, dpi), PrintResolution.pixels_to_inches(pixels_h, dpi)
    elif unit == PhysicalUnit.CENTIMETERS:
        return PrintResolution.pixels_to_cm(pixels_w, dpi), PrintResolution.pixels_to_cm(pixels_h, dpi)
    else:
        raise ValueError(f"Unknown physical unit: {unit}")


@dataclass
class SizingPlan:
    source_w: int
    source_h: int
    target_canvas_w: int
    target_canvas_h: int
    scaled_content_w: int
    scaled_content_h: int
    offset_x: int
    offset_y: int
    scale_factor_x: float
    scale_factor_y: float
    composition: CompositionMode
    crop_box: Optional[Tuple[int, int, int, int]] = None  # (left, top, right, bottom) on scaled content


def plan_canvas_sizing(
    source_w: int,
    source_h: int,
    target_w: int,
    target_h: int,
    composition: CompositionMode = CompositionMode.FIT_PAD,
    crop_align: CropAlignment = CropAlignment.CENTER
) -> SizingPlan:
    """
    Plans exact scaling and placement geometry for fitting or cropping the image.
    Never silently crops or distorts aspect ratio.
    """
    if source_w <= 0 or source_h <= 0 or target_w <= 0 or target_h <= 0:
        raise ValueError("Dimensions must be positive integers")

    if composition == CompositionMode.FIT_PAD:
        # Scale to fit completely inside target bounding box
        scale = min(target_w / source_w, target_h / source_h)
        scaled_w = max(1, int(round(source_w * scale)))
        scaled_h = max(1, int(round(source_h * scale)))
        
        # Center inside target canvas
        offset_x = (target_w - scaled_w) // 2
        offset_y = (target_h - scaled_h) // 2

        return SizingPlan(
            source_w=source_w,
            source_h=source_h,
            target_canvas_w=target_w,
            target_canvas_h=target_h,
            scaled_content_w=scaled_w,
            scaled_content_h=scaled_h,
            offset_x=offset_x,
            offset_y=offset_y,
            scale_factor_x=scaled_w / source_w,
            scale_factor_y=scaled_h / source_h,
            composition=composition
        )

    elif composition == CompositionMode.CROP:
        # Scale to cover target box completely
        scale = max(target_w / source_w, target_h / source_h)
        scaled_w = max(1, int(round(source_w * scale)))
        scaled_h = max(1, int(round(source_h * scale)))

        # Determine crop offset within scaled image
        extra_w = scaled_w - target_w
        extra_h = scaled_h - target_h

        if crop_align == CropAlignment.CENTER:
            crop_x = extra_w // 2
            crop_y = extra_h // 2
        elif crop_align == CropAlignment.TOP:
            crop_x = extra_w // 2
            crop_y = 0
        elif crop_align == CropAlignment.BOTTOM:
            crop_x = extra_w // 2
            crop_y = extra_h
        elif crop_align == CropAlignment.LEFT:
            crop_x = 0
            crop_y = extra_h // 2
        elif crop_align == CropAlignment.RIGHT:
            crop_x = extra_w
            crop_y = extra_h // 2
        else:
            crop_x = extra_w // 2
            crop_y = extra_h // 2

        crop_box = (crop_x, crop_y, crop_x + target_w, crop_y + target_h)

        return SizingPlan(
            source_w=source_w,
            source_h=source_h,
            target_canvas_w=target_w,
            target_canvas_h=target_h,
            scaled_content_w=scaled_w,
            scaled_content_h=scaled_h,
            offset_x=-crop_x,
            offset_y=-crop_y,
            scale_factor_x=scaled_w / source_w,
            scale_factor_y=scaled_h / source_h,
            composition=composition,
            crop_box=crop_box
        )
    else:
        raise ValueError(f"Unknown composition mode: {composition}")


def estimate_resource_usage(width: int, height: int, channels: int = 4) -> dict:
    """
    Computes megapixels, uncompressed frame memory, and safe working memory budget.
    """
    total_pixels = width * height
    megapixels = total_pixels / 1_000_000.0
    bytes_per_pixel = channels  # 8-bit RGBA = 4 bytes
    uncompressed_mb = (total_pixels * bytes_per_pixel) / (1024 * 1024)
    # Peak working budget estimate during multi-stage processing & tiling (approx 4x to 6x frame)
    working_budget_mb = uncompressed_mb * 5.0

    return {
        "pixels": total_pixels,
        "megapixels": round(megapixels, 2),
        "uncompressed_mb": round(uncompressed_mb, 2),
        "estimated_budget_mb": round(working_budget_mb, 2),
        "is_huge": total_pixels > (16000 * 16000),  # > 256 MP
        "is_warning": total_pixels > (8400 * 9600)  # > 80.6 MP (600 DPI 14x16 reference)
    }


# Hard per-axis canvas limit (matches the pixel inputs in the UI). Larger requests are
# refused up front instead of failing deep inside allocation or encoding.
MAX_CANVAS_AXIS_PX = 30000


def estimate_job_memory_bytes(source_w: int, source_h: int, plan: "SizingPlan", uses_model: bool) -> int:
    """
    Approximate peak memory (commit) estimate for one export job (bytes), calibrated against
    measured runs (audit: 8400x9600 Preserve 1.8 GB commit, AI Illustration on DirectML 3.8 GB).
    Source stage: decoded RGBA + RGB copy + edge-extension buffers (~22 B/px).
    Output stage: scaled RGB + alpha + merged RGBA + canvas + encoder copy (~16 B/px).
    AI stage: 4x float32 accumulation, weights and 8-bit result (~19 B per 4x pixel).
    """
    src_px = source_w * source_h
    content_px = plan.scaled_content_w * plan.scaled_content_h
    canvas_px = plan.target_canvas_w * plan.target_canvas_h
    total = src_px * 22 + content_px * 8 + canvas_px * 8
    if uses_model:
        total += src_px * 16 * 19 + 1_500_000_000  # 4x buffers + ONNX Runtime/DirectML working set
    # Allocator and encoder overhead seen in measurements (~1.5x the buffer sum, +0.5 GB runtime)
    return int(total * 1.5 + 500_000_000)


def get_available_memory_bytes() -> Optional[int]:
    """Currently available physical memory on Windows, or None when it cannot be queried."""
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
        return int(status.ullAvailPhys)
    except Exception:
        return None
