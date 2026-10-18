"""
PrintScale Studio - Tiling and Seam Blending Engine
Executes memory-bounded tiled inference with contextual overlap padding
and linear feathering blend weights to eliminate seam artifacts.
"""

from typing import Callable, Optional
import numpy as np

from printscale.inference.engine import InferenceEngine


class CancellationException(Exception):
    """Raised when an operation is cancelled by the user."""
    pass


def _tile_starts(length: int, tile_size: int, stride: int) -> list:
    """Tile origins covering [0, length) with the last tile flush against the far edge."""
    if length <= tile_size:
        return [0]
    starts = list(range(0, length - tile_size, stride))
    starts.append(length - tile_size)
    return sorted(set(starts))


def _feather_ramp(length: int, ramp: int, feather_start: bool, feather_end: bool) -> np.ndarray:
    """1D blend weights. Ramps only on sides that overlap a neighbouring tile;
    image borders keep full weight."""
    weights = np.ones(length, dtype=np.float32)
    ramp = min(ramp, length // 2)
    if ramp > 0:
        # Strictly positive ramp so every output pixel keeps a non-zero total weight
        ramp_vals = np.linspace(0.0, 1.0, ramp + 2, dtype=np.float32)[1:-1]
        if feather_start:
            weights[:ramp] = ramp_vals
        if feather_end:
            weights[-ramp:] = ramp_vals[::-1]
    return weights


def run_tiled_inference(
    img_rgb: np.ndarray,
    engine: InferenceEngine,
    tile_size: int = 256,
    overlap: int = 16,
    scale: int = 4,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    is_cancelled_fn: Optional[Callable[[], bool]] = None,
    context: int = 32
) -> np.ndarray:
    """
    Executes tiled super-resolution on an RGB numpy image (H, W, 3), range [0, 255] uint8.
    Returns (scale*H, scale*W, 3) uint8 array.

    Each tile is run with `context` extra source pixels on every interior side. The model
    output for that context is discarded, so no kept pixel is computed near an artificial
    tile border (where convolutional models produce edge artifacts). Neighbouring kept
    regions overlap by `overlap` source pixels and are cross-faded linearly.
    """
    h, w, c = img_rgb.shape
    assert c == 3, f"Expected 3 color channels, got {c}"

    out_h = h * scale
    out_w = w * scale

    # If image is small enough, run single patch directly
    if h <= tile_size and w <= tile_size:
        if is_cancelled_fn and is_cancelled_fn():
            raise CancellationException("Inference cancelled by user")
        if progress_callback:
            progress_callback(1, 1, "Running inference on image...")

        # Normalize to float32 [0.0, 1.0] and NCHW format
        inp = (img_rgb.transpose(2, 0, 1).astype(np.float32) / 255.0)[None, ...]
        out_patch = engine.run_patch(inp)[0]  # shape (3, out_h, out_w)
        return np.clip(np.rint(out_patch * 255.0), 0.0, 255.0).astype(np.uint8).transpose(1, 2, 0)

    stride = max(32, tile_size - overlap)
    x_starts = _tile_starts(w, tile_size, stride)
    y_starts = _tile_starts(h, tile_size, stride)
    total_tiles = len(x_starts) * len(y_starts)

    # Accumulation buffers (float32 for blending)
    accum_output = np.zeros((out_h, out_w, 3), dtype=np.float32)
    accum_weight = np.zeros((out_h, out_w), dtype=np.float32)

    tile_index = 0
    for y0 in y_starts:
        y1 = min(h, y0 + tile_size)
        py0, py1 = max(0, y0 - context), min(h, y1 + context)

        for x0 in x_starts:
            if is_cancelled_fn and is_cancelled_fn():
                raise CancellationException("Inference cancelled by user")

            x1 = min(w, x0 + tile_size)
            px0, px1 = max(0, x0 - context), min(w, x1 + context)

            tile_index += 1
            if progress_callback:
                progress_callback(tile_index, total_tiles, f"Enhancing tile {tile_index} / {total_tiles}...")

            # Extract tile plus surrounding context and normalize
            patch = img_rgb[py0:py1, px0:px1, :]
            patch_nchw = (patch.transpose(2, 0, 1).astype(np.float32) / 255.0)[None, ...]

            out_patch_chw = engine.run_patch(patch_nchw)[0]
            out_patch_hwc = out_patch_chw.transpose(1, 2, 0) * 255.0

            # Discard the output produced for the context margin
            out_patch_hwc = out_patch_hwc[
                (y0 - py0) * scale:(y1 - py0) * scale,
                (x0 - px0) * scale:(x1 - px0) * scale
            ]

            ramp = overlap * scale
            wy = _feather_ramp(out_patch_hwc.shape[0], ramp, y0 > 0, y1 < h)
            wx = _feather_ramp(out_patch_hwc.shape[1], ramp, x0 > 0, x1 < w)
            w_mask = wy[:, None] * wx[None, :]

            accum_output[y0 * scale:y1 * scale, x0 * scale:x1 * scale, :] += out_patch_hwc * w_mask[:, :, None]
            accum_weight[y0 * scale:y1 * scale, x0 * scale:x1 * scale] += w_mask

    # Final normalization
    accum_weight = np.maximum(accum_weight, 1e-6)
    return np.clip(np.rint(accum_output / accum_weight[:, :, None]), 0.0, 255.0).astype(np.uint8)
