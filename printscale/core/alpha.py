"""
PrintScale Studio - Alpha Channel and Transparency Processing
Comprehensive alpha handling:
- Support for RGBA, LA, palette transparency (mode P).
- Edge color extension / color bleeding (dilation) to eliminate black/white halos & fringing.
- Isolated alpha upscaling pipeline (preventing photographic hallucination on alpha mask).
- Edge verification fixtures against black, white, and checkerboard backgrounds.
"""

from typing import Tuple
import numpy as np
from PIL import Image


def extract_rgba_and_transparency_state(img: Image.Image) -> Tuple[Image.Image, bool]:
    """
    Normalizes any input image to RGBA (if transparent) or RGB (if opaque).
    Returns (normalized_image, has_true_transparency).
    Handles RGBA, LA, PA, and palette PNG with transparency index/dict.
    """
    has_alpha = False
    
    if img.mode == "RGBA":
        # Check if alpha actually contains any non-255 pixels
        alpha = img.getchannel("A")
        extrema = alpha.getextrema()
        if extrema[0] < 255:
            has_alpha = True
        return img, has_alpha

    elif img.mode == "LA":
        # Grayscale with alpha
        rgba = img.convert("RGBA")
        alpha = rgba.getchannel("A")
        if alpha.getextrema()[0] < 255:
            has_alpha = True
        return rgba, has_alpha

    elif img.mode == "P":
        # Palette mode with possible transparency
        if "transparency" in img.info:
            rgba = img.convert("RGBA")
            alpha = rgba.getchannel("A")
            if alpha.getextrema()[0] < 255:
                has_alpha = True
            return rgba, has_alpha
        else:
            return img.convert("RGB"), False

    elif img.mode == "RGB":
        return img, False

    elif img.mode == "L":
        return img.convert("RGB"), False

    else:
        # Generic conversion
        converted = img.convert("RGBA")
        if converted.getchannel("A").getextrema()[0] < 255:
            return converted, True
        return converted.convert("RGB"), False


def extend_edge_colors(
    rgb_arr: np.ndarray,
    alpha_arr: np.ndarray,
    iterations: int = 5
) -> np.ndarray:
    """
    Edge color extension / color bleeding:
    Propagates the RGB values of non-transparent edge pixels outward into 
    the zero-alpha region using iterative nearest-neighbor diffusion.
    
    This guarantees that when spatial convolutions or resampling kernels 
    sample across the alpha boundary, they sample matching color rather than 
    default black (0,0,0) or white (255,255,255), completely preventing fringing.
    
    rgb_arr: shape (H, W, 3), dtype uint8
    alpha_arr: shape (H, W), dtype uint8
    """
    extended_rgb = rgb_arr.copy()

    # Mask of pixels that have valid color: alpha > 0
    valid_mask = alpha_arr > 0

    if np.all(valid_mask) or not np.any(valid_mask):
        # Either fully opaque or completely empty
        return extended_rgb

    # Morphological color dilation. Integer accumulators keep peak memory near
    # 15 bytes per pixel so very large canvases stay within budget.
    h, w, _ = extended_rgb.shape
    for _ in range(iterations):
        if valid_mask.all():
            break

        sum_rgb = np.zeros((h, w, 3), dtype=np.uint16)
        count = np.zeros((h, w), dtype=np.uint8)
        # (destination slice, source slice) for top, bottom, left and right neighbours
        shifts = (
            ((slice(1, None), slice(None)), (slice(None, -1), slice(None))),
            ((slice(None, -1), slice(None)), (slice(1, None), slice(None))),
            ((slice(None), slice(1, None)), (slice(None), slice(None, -1))),
            ((slice(None), slice(None, -1)), (slice(None), slice(1, None))),
        )
        for dst, src in shifts:
            src_valid = valid_mask[src]
            sum_rgb[dst] += extended_rgb[src] * src_valid[:, :, None]
            count[dst] += src_valid

        # Empty pixels with at least one valid neighbour
        update_mask = ~valid_mask & (count > 0)
        if not np.any(update_mask):
            break

        extended_rgb[update_mask] = (sum_rgb[update_mask] // count[update_mask][:, None]).astype(np.uint8)
        valid_mask[update_mask] = True

    return extended_rgb


def edge_extension_iterations(scale: float, uses_model: bool) -> int:
    """
    Number of dilation passes needed so every resampling tap that touches a visible pixel
    reads a real edge colour. Lanczos-3 reaches 3 source pixels when enlarging and
    3 / scale source pixels when reducing. Model inference sees a wider neighbourhood,
    so AI paths extend further.
    """
    reach = 3.0 / min(1.0, max(scale, 1e-6))
    iterations = int(np.ceil(reach)) + 2
    if uses_model:
        iterations = max(iterations, 16)
    return max(6, iterations)


def upscale_alpha_channel(
    alpha_img: Image.Image,
    target_size: Tuple[int, int]
) -> Image.Image:
    """
    Upscales the alpha channel using high-quality anti-aliased Lanczos resampling.
    Guarantees that the alpha channel retains soft, smooth antialiased edges
    without photographic hallucination artifacts.
    """
    return alpha_img.resize(target_size, resample=Image.Resampling.LANCZOS)


def composite_on_background(
    rgba_img: Image.Image,
    bg_color: Tuple[int, int, int] = (255, 255, 255)
) -> Image.Image:
    """
    Composites RGBA image onto a solid background color (e.g. for JPEG export or preview inspection).
    """
    if rgba_img.mode != "RGBA":
        return rgba_img.convert("RGB")
    
    bg = Image.new("RGB", rgba_img.size, bg_color)
    bg.paste(rgba_img, mask=rgba_img.split()[3])
    return bg


def generate_checkerboard(width: int, height: int, square_size: int = 16) -> Image.Image:
    """
    Generates a high-contrast neutral checkerboard image for viewer preview.
    (This is viewer-only and never baked into exports).
    """
    row_count = (height + square_size - 1) // square_size
    col_count = (width + square_size - 1) // square_size
    
    # Create checkerboard tile grid
    grid = np.indices((row_count, col_count)).sum(axis=0) % 2
    color1 = np.array([238, 238, 238], dtype=np.uint8)
    color2 = np.array([204, 204, 204], dtype=np.uint8)
    
    board = np.where(grid[:, :, None] == 0, color1, color2)
    # Resize up to full dimensions
    board_img = Image.fromarray(board, mode="RGB")
    board_scaled = board_img.resize((col_count * square_size, row_count * square_size), resample=Image.Resampling.NEAREST)
    return board_scaled.crop((0, 0, width, height))
