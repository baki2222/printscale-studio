"""
PrintScale Studio - Image Enhancement and Processing Modes
Implements honest, distinct processing pipelines:
1. Preserve Artwork (High-quality non-generative Lanczos resampling + restrained sharpening)
2. AI Illustration (Real-ESRGAN Anime 6B model-based enhancement)
3. AI Photo (Real-ESRGAN x4plus photographic super-resolution)
"""

from enum import Enum
from typing import Tuple, Optional, Callable
from PIL import Image, ImageFilter
import numpy as np

from printscale.inference.engine import InferenceEngine
from printscale.inference.tiling import run_tiled_inference, CancellationException


class ProcessingMode(str, Enum):
    PRESERVE_ARTWORK = "preserve_artwork"  # Non-generative high-fidelity resampling
    AI_ILLUSTRATION = "ai_illustration"    # Model-based enhancement for artwork/graphics
    AI_PHOTO = "ai_photo"                  # Model-based super-resolution for photos


class SharpeningLevel(int, Enum):
    NONE = 0
    LIGHT = 20
    BALANCED = 35
    STRONG = 50


def apply_restrained_sharpening(
    rgb_img: Image.Image,
    amount_percent: int = 25,
    radius: float = 1.0,
    threshold: int = 2
) -> Image.Image:
    """
    Applies gentle, restrained unsharp masking to enhance crisp edges in apparel graphics
    without introducing ugly white halos or amplifying noise.
    """
    if amount_percent <= 0:
        return rgb_img

    # Pillow UnsharpMask takes radius (float), percent (int), threshold (int)
    clamped_percent = max(0, min(100, amount_percent))
    usm = ImageFilter.UnsharpMask(radius=radius, percent=clamped_percent, threshold=threshold)
    return rgb_img.filter(usm)


def process_rgb_artwork_preserve(
    rgb_img: Image.Image,
    target_size: Tuple[int, int],
    sharpen_percent: int = 0
) -> Image.Image:
    """
    Preserve Artwork Mode:
    Uses mathematical Lanczos-8 resampling prioritizing flat fills, geometry, and crisp typography.
    Zero generative hallucinations.
    """
    scaled = rgb_img.resize(target_size, resample=Image.Resampling.LANCZOS)
    if sharpen_percent > 0:
        scaled = apply_restrained_sharpening(scaled, amount_percent=sharpen_percent)
    return scaled


def process_rgb_model(
    rgb_img: Image.Image,
    target_size: Tuple[int, int],
    model_id: str,
    engine: InferenceEngine,
    sharpen_percent: int = 0,
    tile_size: int = 256,
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
    is_cancelled_cb: Optional[Callable[[], bool]] = None
) -> Image.Image:
    """
    AI Model Mode (Illustration or Photo):
    1. Loads verified ONNX model.
    2. Runs seamless tiled 4x super-resolution with context overlap and feathering.
    3. Resamples from 4x intermediate to exact target dimensions using Lanczos.
    4. Applies optional restrained sharpening.
    """
    # Pipeline progress band reserved for inference (percent of the whole job)
    band_start, band_end = 30, 82

    def tile_progress(current: int, total: int, msg: str):
        if progress_cb:
            pct = band_start + int((band_end - band_start) * current / max(1, total))
            progress_cb(pct, 100, msg)

    # Load model
    if progress_cb:
        progress_cb(band_start, 100, f"Loading model {model_id}...")
    engine.load_model(model_id)

    # Convert PIL Image to numpy RGB array
    arr_rgb = np.array(rgb_img.convert("RGB"), dtype=np.uint8)

    # Run tiled inference (4x native scale). A GPU runtime failure (e.g. DirectML
    # out of memory) is retried once with smaller tiles, then once on the CPU.
    attempts = [tile_size]
    if engine.active_provider.startswith("DirectML"):
        attempts.append(max(64, tile_size // 2))
    out_arr = None
    last_error: Optional[Exception] = None
    for attempt_tile in attempts + ["cpu"]:
        if attempt_tile == "cpu":
            if not engine.active_provider.startswith("DirectML"):
                break
            engine.fall_back_to_cpu(f"{type(last_error).__name__}: {last_error}")
            attempt_tile = tile_size
        try:
            out_arr = run_tiled_inference(
                arr_rgb,
                engine=engine,
                tile_size=attempt_tile,
                overlap=16,
                scale=4,
                progress_callback=tile_progress,
                is_cancelled_fn=is_cancelled_cb
            )
            break
        except CancellationException:
            raise
        except Exception as e:  # GPU/CPU runtime failure: retry within the bounded plan
            last_error = e
    if out_arr is None:
        raise RuntimeError(f"AI inference failed: {last_error}")

    if progress_cb:
        progress_cb(band_end, 100, "Resampling to exact requested dimensions...")

    # Convert back to PIL Image
    upscaled_4x = Image.fromarray(out_arr, mode="RGB")

    # If requested target size matches 4x exactly, return directly;
    # otherwise, resample with high-quality Lanczos filter to exact target dimensions
    if upscaled_4x.size == target_size:
        final_img = upscaled_4x
    else:
        final_img = upscaled_4x.resize(target_size, resample=Image.Resampling.LANCZOS)

    if sharpen_percent > 0:
        final_img = apply_restrained_sharpening(final_img, amount_percent=sharpen_percent)

    return final_img
