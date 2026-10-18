"""
PrintScale Studio - End-to-End Image Processing Pipeline
Orchestrates validation, orientation normalization, color management, alpha handling,
geometric planning, enhancement, export encoding, and reopen verification.
"""

import os
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Tuple, Optional, Callable, List
import numpy as np
from PIL import Image

from printscale.core.geometry import (
    DimensionMode, PhysicalUnit, CompositionMode, CropAlignment,
    calculate_target_pixels, calculate_physical_size, plan_canvas_sizing,
    estimate_job_memory_bytes, get_available_memory_bytes, MAX_CANVAS_AXIS_PX
)
from printscale.core.metadata import (
    normalize_image_orientation, convert_to_srgb, save_image_with_resolution,
    update_metadata_only, read_file_metadata, detect_source_bits_per_channel,
    normalize_pixel_format
)
from printscale.core.alpha import (
    extract_rgba_and_transparency_state, extend_edge_colors, edge_extension_iterations,
    upscale_alpha_channel, composite_on_background
)
from printscale.core.enhancement import (
    ProcessingMode, process_rgb_artwork_preserve, process_rgb_model
)
from printscale.core.config import UPLOAD_MAX_BYTES, UPLOAD_MAX_PIXELS_PER_AXIS
from printscale.inference.engine import InferenceEngine
from printscale.inference.tiling import CancellationException


CANCELLED_MESSAGE = "Cancelled by user"

# Extension expected for each encoded format
_FORMAT_EXTENSIONS = {"PNG": (".png",), "JPEG": (".jpg", ".jpeg")}


@dataclass
class JobParameters:
    source_path: str
    output_path: str
    output_format: str  # 'PNG' or 'JPEG'
    dimension_mode: DimensionMode
    dpi: int = 300
    # For PRINT_SIZE mode
    print_width: float = 14.0
    print_height: float = 16.0
    print_unit: PhysicalUnit = PhysicalUnit.INCHES
    # For PIXEL_DIMS mode
    pixel_width: int = 4200
    pixel_height: int = 4800
    # Processing options
    processing_mode: ProcessingMode = ProcessingMode.PRESERVE_ARTWORK
    composition_mode: CompositionMode = CompositionMode.FIT_PAD
    crop_alignment: CropAlignment = CropAlignment.CENTER
    sharpen_percent: int = 0
    jpeg_quality: int = 95
    jpeg_bg_color: Tuple[int, int, int] = (255, 255, 255)
    # Hardware preference
    prefer_gpu: bool = True
    # When False an existing destination is never replaced; a unique "_N" name is used instead.
    overwrite_existing: bool = False
    # Upload profile checked against the actual encoded file (never used to alter the output)
    upload_max_bytes: int = UPLOAD_MAX_BYTES
    upload_max_axis_px: int = UPLOAD_MAX_PIXELS_PER_AXIS


@dataclass
class JobExecutionResult:
    success: bool
    output_path: str
    target_width: int
    target_height: int
    output_dpi: float
    physical_width_in: float
    physical_height_in: float
    file_size_bytes: int
    has_alpha: bool
    format: str
    method_used: str
    device_used: str
    verification_passed: bool
    warning_message: Optional[str] = None
    error_message: Optional[str] = None
    notes: List[str] = field(default_factory=list)
    upload_compliant: Optional[bool] = None
    upload_message: str = ""


def _failure(params: JobParameters, message: str) -> JobExecutionResult:
    return JobExecutionResult(
        success=False, output_path=params.output_path, target_width=0, target_height=0,
        output_dpi=0, physical_width_in=0, physical_height_in=0, file_size_bytes=0,
        has_alpha=False, format=params.output_format, method_used="", device_used="",
        verification_passed=False, error_message=message
    )


def validate_input_image(filepath: str) -> Tuple[bool, str, Image.Image]:
    """
    Validates that the input image exists, is supported, and is not animated or multipage.
    Pillow's decompression-bomb limit stays active (images above its hard limit are rejected).
    """
    if not os.path.isfile(filepath):
        return False, f"File not found: {filepath}", None

    try:
        img = Image.open(filepath)
    except Image.DecompressionBombError as e:
        return False, f"Image exceeds the decoded-pixel safety limit: {str(e)}", None
    except Exception as e:
        return False, f"Cannot open image: {str(e)}", None

    # Check for animated or multipage files
    is_animated = getattr(img, "is_animated", False)
    n_frames = getattr(img, "n_frames", 1)
    if is_animated or n_frames > 1:
        img.close()
        return False, "Animated or multipage images are not supported. Please supply a static single-frame image.", None

    fmt = (img.format or "").upper()
    if fmt not in ("PNG", "JPEG", "JPG", "WEBP", "TIFF", "TIF"):
        img.close()
        return False, f"Unsupported image format: {fmt}. Supported formats: PNG, JPEG, WebP, TIFF.", None

    return True, "Valid", img


def _same_file(a: str, b: str) -> bool:
    if os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b)):
        return True
    try:
        return os.path.exists(b) and os.path.samefile(a, b)
    except OSError:
        return False


def _finalize_output(temp_path: str, dest_path: str, overwrite: bool) -> str:
    """
    Moves a verified temporary file to its destination and returns the final path.
    With overwrite=False an existing file is never replaced: the move itself refuses to
    clobber (rename on Windows, hard link elsewhere), and a "_N" suffix is tried instead,
    which also closes the race with files created after the name was chosen.
    Windows paths compare case-insensitively, so "A.png" and "a.png" collide.
    """
    if overwrite:
        os.replace(temp_path, dest_path)
        return dest_path

    stem, ext = os.path.splitext(dest_path)
    candidate = dest_path
    counter = 1
    while True:
        try:
            if sys.platform == "win32":
                os.rename(temp_path, candidate)  # raises FileExistsError instead of replacing
            else:
                os.link(temp_path, candidate)
                os.remove(temp_path)
            return candidate
        except FileExistsError:
            candidate = f"{stem}_{counter}{ext}"
            counter += 1
            if counter > 10000:
                raise


def _check_upload_profile(params: JobParameters, width: int, height: int, size_bytes: int, fmt: str) -> Tuple[bool, str]:
    problems = []
    if size_bytes > params.upload_max_bytes:
        problems.append(f"file is {size_bytes:,} bytes (limit {params.upload_max_bytes:,})")
    if max(width, height) > params.upload_max_axis_px:
        problems.append(f"{width} x {height} px exceeds {params.upload_max_axis_px:,} px per axis")
    if fmt.upper() not in ("PNG", "JPEG"):
        problems.append(f"format {fmt} is not PNG/JPEG")
    if problems:
        return False, "Outside upload profile: " + "; ".join(problems)
    return True, (f"Within upload profile ({size_bytes:,} of {params.upload_max_bytes:,} bytes; "
                  f"max axis {max(width, height):,} of {params.upload_max_axis_px:,} px)")


def _verify_metadata_only_output(source_path: str, temp_path: str, fmt: str, dpi: int) -> List[str]:
    """Independent checks that a metadata-only rewrite changed nothing but resolution metadata."""
    problems = []
    with Image.open(source_path) as a, Image.open(temp_path) as b:
        if a.size != b.size or a.mode != b.mode:
            problems.append("image size or mode changed")
        else:
            a.load()
            b.load()
            if a.tobytes() != b.tobytes():
                problems.append("decoded pixels changed")
            if a.mode == "P" and a.getpalette() != b.getpalette():
                problems.append("palette changed")
    meta = read_file_metadata(temp_path)
    if meta.dpi_x is None or abs(meta.dpi_x - dpi) > 0.05 or abs((meta.dpi_y or 0) - dpi) > 0.05:
        problems.append(f"resolution reads back as {meta.dpi_x} x {meta.dpi_y}")
    if fmt == "PNG":
        with open(temp_path, "rb") as f:
            data = f.read()
        if data.count(b"pHYs") < 1:
            problems.append("pHYs chunk missing")
    return problems


def execute_pipeline(
    params: JobParameters,
    engine: Optional[InferenceEngine] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    is_cancelled_callback: Optional[Callable[[], bool]] = None
) -> JobExecutionResult:
    """
    Executes the complete end-to-end processing job. The output is written to a temporary
    file in the destination folder, reopened and verified, and only then moved into place.
    """
    def progress(pct: int, msg: str):
        if progress_callback:
            progress_callback(pct, 100, msg)

    def cancelled() -> bool:
        return bool(is_cancelled_callback and is_cancelled_callback())

    progress(0, "Validating input image...")
    if cancelled():
        return _failure(params, CANCELLED_MESSAGE)

    if params.dpi <= 0:
        return _failure(params, f"DPI must be positive, got {params.dpi}")
    if _same_file(params.source_path, params.output_path):
        return _failure(params, "The output path is the source file. Originals are never overwritten; choose another file name.")

    # 1. Validate input
    valid, msg, img = validate_input_image(params.source_path)
    if not valid:
        return _failure(params, msg)

    source_format = (img.format or "").upper()
    if source_format == "JPG":
        source_format = "JPEG"
    out_format = params.output_format.upper()
    if out_format == "JPG":
        out_format = "JPEG"
    notes: List[str] = []
    temp_file_path = None

    try:
        if params.dimension_mode == DimensionMode.METADATA_ONLY:
            # Metadata-only keeps the source encoding; a different output format would need re-encoding
            if source_format not in ("PNG", "JPEG"):
                raise ValueError(f"DPI metadata-only mode supports PNG and JPEG sources, not {source_format}.")
            out_format = source_format

        if out_format not in _FORMAT_EXTENSIONS:
            raise ValueError(f"Unsupported output format: {params.output_format}")
        if not params.output_path.lower().endswith(_FORMAT_EXTENSIONS[out_format]):
            raise ValueError(f"Output file name must end with {' or '.join(_FORMAT_EXTENSIONS[out_format])} for {out_format} output.")

        # Prepare atomic destination temporary file in the destination folder
        dest_dir = os.path.dirname(os.path.abspath(params.output_path))
        os.makedirs(dest_dir, exist_ok=True)
        temp_fd, temp_file_path = tempfile.mkstemp(prefix=".printscale_", suffix=".tmp", dir=dest_dir)
        os.close(temp_fd)

        # 2. Mode C: Metadata only
        if params.dimension_mode == DimensionMode.METADATA_ONLY:
            progress(30, "Updating resolution metadata (pixels untouched)...")
            img.close()
            update_metadata_only(params.source_path, temp_file_path, params.dpi)

            progress(80, "Verifying pixels are unchanged...")
            problems = _verify_metadata_only_output(params.source_path, temp_file_path, out_format, params.dpi)
            if problems:
                raise ValueError("Metadata-only verification failed: " + "; ".join(problems))

            if cancelled():
                raise CancellationException(CANCELLED_MESSAGE)
            final_path = _finalize_output(temp_file_path, params.output_path, params.overwrite_existing)
            temp_file_path = None

            meta = read_file_metadata(final_path)
            file_bytes = os.path.getsize(final_path)
            phys_w, phys_h = calculate_physical_size(meta.width, meta.height, params.dpi, PhysicalUnit.INCHES)
            upload_ok, upload_msg = _check_upload_profile(params, meta.width, meta.height, file_bytes, meta.format)
            notes.append("Decoded pixels verified identical to the source.")
            progress(100, "Complete!")

            return JobExecutionResult(
                success=True,
                output_path=final_path,
                target_width=meta.width,
                target_height=meta.height,
                output_dpi=meta.dpi_x or params.dpi,
                physical_width_in=round(phys_w, 2),
                physical_height_in=round(phys_h, 2),
                file_size_bytes=file_bytes,
                has_alpha=meta.has_alpha,
                format=meta.format,
                method_used="Metadata update only (pixels untouched)",
                device_used="None (lossless rewrite)",
                verification_passed=True,
                notes=notes,
                upload_compliant=upload_ok,
                upload_message=upload_msg
            )

        # Bit depth must be read before decoding
        source_bits = detect_source_bits_per_channel(img)

        # 3. Normalize orientation
        progress(5, "Normalizing image orientation...")
        orientation = 1
        try:
            orientation = int(img.getexif().get(0x0112, 1) or 1)
        except Exception:
            pass
        img = normalize_image_orientation(img)
        if orientation not in (1, 0):
            notes.append(f"EXIF orientation {orientation} applied to pixels; output orientation is normal.")

        img, fmt_notes = normalize_pixel_format(img)
        notes.extend(fmt_notes)
        if source_bits > 8 and not fmt_notes:
            notes.append(f"{source_bits}-bit source reduced to 8 bits per channel (8-bit output).")
        src_w, src_h = img.size

        # 4. Color management
        progress(10, "Applying color management...")
        img, icc_bytes, color_notes = convert_to_srgb(img)
        notes.extend(color_notes)

        # 5. Determine target pixel dimensions
        if params.dimension_mode == DimensionMode.PRINT_SIZE:
            target_w, target_h = calculate_target_pixels(
                params.print_width, params.print_height, params.dpi, params.print_unit
            )
        elif params.dimension_mode == DimensionMode.PIXEL_DIMS:
            target_w = int(params.pixel_width)
            target_h = int(params.pixel_height)
            if target_w <= 0 or target_h <= 0:
                raise ValueError(f"Pixel dimensions must be positive, got {target_w} x {target_h}")
        else:
            raise ValueError(f"Unknown dimension mode: {params.dimension_mode}")

        if max(target_w, target_h) > MAX_CANVAS_AXIS_PX:
            raise ValueError(f"Requested canvas {target_w} x {target_h} px exceeds the {MAX_CANVAS_AXIS_PX:,} px per-axis limit.")

        # Plan geometry and composition
        plan = plan_canvas_sizing(
            source_w=src_w,
            source_h=src_h,
            target_w=target_w,
            target_h=target_h,
            composition=params.composition_mode,
            crop_align=params.crop_alignment
        )

        scale_x = plan.scaled_content_w / src_w
        scale_y = plan.scaled_content_h / src_h
        avg_scale = (scale_x + scale_y) / 2.0
        use_model = params.processing_mode != ProcessingMode.PRESERVE_ARTWORK and avg_scale > 1.0

        # Refuse jobs that cannot fit in memory instead of failing deep inside processing
        needed = estimate_job_memory_bytes(src_w, src_h, plan, use_model)
        available = get_available_memory_bytes()
        if available is not None and needed > available * 0.85:
            raise MemoryError(
                f"Not enough free memory: this job needs about {needed / 2**30:.1f} GB, "
                f"{available / 2**30:.1f} GB is available. Use a smaller target or close other programs."
            )

        # 6. Alpha separation and edge extension
        progress(15, "Inspecting alpha channels...")
        img_norm, has_alpha = extract_rgba_and_transparency_state(img)
        alpha_channel = None
        if has_alpha:
            alpha_channel = img_norm.getchannel("A")
            # Edge color extension so resampling and inference never pull hidden RGB into visible edges
            rgb_arr = np.array(img_norm.convert("RGB"), dtype=np.uint8)
            alpha_arr = np.array(alpha_channel, dtype=np.uint8)
            iterations = edge_extension_iterations(min(scale_x, scale_y), use_model)
            dilated_rgb_arr = extend_edge_colors(rgb_arr, alpha_arr, iterations=iterations)
            color_source_img = Image.fromarray(dilated_rgb_arr, mode="RGB")
            del rgb_arr, alpha_arr, dilated_rgb_arr
        else:
            color_source_img = img_norm.convert("RGB")

        if cancelled():
            raise CancellationException(CANCELLED_MESSAGE)

        # 7. Processing method selection
        if not use_model:
            sharpen_desc = f" + unsharp mask {params.sharpen_percent}%" if params.sharpen_percent > 0 else ""
            if params.processing_mode == ProcessingMode.PRESERVE_ARTWORK:
                progress(30, "Processing with Preserve Artwork (Lanczos)...")
                method_desc = f"Preserve Artwork (Lanczos-3 resampling{sharpen_desc})"
            else:
                progress(30, "Target is not larger than the source; resampling without AI...")
                method_desc = f"Lanczos-3 resampling{sharpen_desc} (AI model not applied: target is not larger than source)"
            scaled_color = process_rgb_artwork_preserve(
                color_source_img,
                target_size=(plan.scaled_content_w, plan.scaled_content_h),
                sharpen_percent=params.sharpen_percent
            )
            device_desc = "CPU (Pillow resampling)"
        else:
            if engine is None:
                engine = InferenceEngine(prefer_gpu=params.prefer_gpu)

            model_id = "illustration_anime_6b" if params.processing_mode == ProcessingMode.AI_ILLUSTRATION else "photo_x4plus"
            model_name = "Real-ESRGAN x4plus anime 6B" if model_id == "illustration_anime_6b" else "Real-ESRGAN x4plus"
            label = "AI Illustration" if model_id == "illustration_anime_6b" else "AI Photo"
            final_scale = (plan.scaled_content_w / (src_w * 4.0))
            resize_desc = "" if (plan.scaled_content_w, plan.scaled_content_h) == (src_w * 4, src_h * 4) else \
                f" + Lanczos-3 resize of the 4x result ({final_scale:.3f}x)"
            sharpen_desc = f" + unsharp mask {params.sharpen_percent}%" if params.sharpen_percent > 0 else ""
            method_desc = f"{label} ({model_name}, 4x inference on RGB{resize_desc}{sharpen_desc})"

            scaled_color = process_rgb_model(
                color_source_img,
                target_size=(plan.scaled_content_w, plan.scaled_content_h),
                model_id=model_id,
                engine=engine,
                sharpen_percent=params.sharpen_percent,
                tile_size=256,
                progress_cb=progress_callback,
                is_cancelled_cb=is_cancelled_callback
            )
            device_desc = engine.device_description
            if has_alpha:
                notes.append("Alpha channel resampled separately with Lanczos-3 (not processed by the AI model).")

        del color_source_img
        if cancelled():
            raise CancellationException(CANCELLED_MESSAGE)

        # 8. Upscale alpha channel if transparent
        if has_alpha and alpha_channel is not None:
            progress(85, "Recombining alpha channel...")
            scaled_alpha = upscale_alpha_channel(
                alpha_channel,
                target_size=(plan.scaled_content_w, plan.scaled_content_h)
            )
            scaled_content = Image.merge("RGBA", (*scaled_color.split(), scaled_alpha))
        else:
            scaled_content = scaled_color
        del scaled_color

        # 9. Canvas Composition (Fit with padding vs Crop)
        progress(90, "Compositing canvas...")
        needs_padding = (plan.composition == CompositionMode.FIT_PAD and
                         (plan.scaled_content_w, plan.scaled_content_h) != (plan.target_canvas_w, plan.target_canvas_h))
        is_jpeg = out_format == "JPEG"

        if plan.composition == CompositionMode.CROP:
            final_canvas = scaled_content.crop(plan.crop_box)
        elif not needs_padding:
            final_canvas = scaled_content
        elif is_jpeg:
            final_canvas = Image.new("RGB", (plan.target_canvas_w, plan.target_canvas_h), params.jpeg_bg_color)
            # Opaque canvas: a masked paste is correct "over" compositing onto the background colour
            if scaled_content.mode == "RGBA":
                final_canvas.paste(scaled_content.convert("RGB"), (plan.offset_x, plan.offset_y),
                                   mask=scaled_content.getchannel("A"))
            else:
                final_canvas.paste(scaled_content, (plan.offset_x, plan.offset_y))
            notes.append(f"Padding filled with #{'%02X%02X%02X' % tuple(params.jpeg_bg_color)} to fit the canvas.")
        else:
            # Transparent padding for PNG. The content is copied without a mask: Image.paste with
            # mask=alpha blends every channel, which squares alpha and darkens semi-transparent
            # edges (the grey-halo defect). A plain paste copies RGBA values exactly.
            final_canvas = Image.new("RGBA", (plan.target_canvas_w, plan.target_canvas_h), (0, 0, 0, 0))
            final_canvas.paste(scaled_content.convert("RGBA"), (plan.offset_x, plan.offset_y))
            if not has_alpha:
                notes.append("Transparent padding added around the opaque image to fit the canvas.")

        if is_jpeg and final_canvas.mode == "RGBA":
            final_canvas = composite_on_background(final_canvas, bg_color=params.jpeg_bg_color)
        if is_jpeg and has_alpha:
            notes.append(f"Transparency flattened onto #{'%02X%02X%02X' % tuple(params.jpeg_bg_color)} for JPEG.")

        if cancelled():
            raise CancellationException(CANCELLED_MESSAGE)

        # 10. Encode to the temporary file
        progress(92, "Encoding and writing output with resolution metadata...")
        save_image_with_resolution(
            img=final_canvas,
            target_path=temp_file_path,
            output_format=out_format,
            dpi=params.dpi,
            jpeg_quality=params.jpeg_quality,
            icc_bytes=icc_bytes
        )
        out_mode = final_canvas.mode
        del final_canvas, scaled_content

        # 11. Reopen and verify the temporary output before it replaces anything
        progress(97, "Reopening export to verify resolution and metadata...")
        verified_meta = read_file_metadata(temp_file_path)
        with Image.open(temp_file_path) as check_im:
            check_im.load()  # full decode proves the file is readable end to end
        problems = []
        if (verified_meta.width, verified_meta.height) != (plan.target_canvas_w, plan.target_canvas_h):
            problems.append(f"dimensions {verified_meta.width}x{verified_meta.height}, expected {plan.target_canvas_w}x{plan.target_canvas_h}")
        if verified_meta.dpi_x is None or verified_meta.dpi_y is None:
            problems.append("resolution metadata missing")
        elif abs(verified_meta.dpi_x - params.dpi) > 0.05 or abs(verified_meta.dpi_y - params.dpi) > 0.05:
            problems.append(f"DPI reads back as {verified_meta.dpi_x:.3f} x {verified_meta.dpi_y:.3f}, expected {params.dpi}")
        if verified_meta.format.upper() != out_format:
            problems.append(f"format {verified_meta.format}, expected {out_format}")
        if verified_meta.color_mode != out_mode:
            problems.append(f"mode {verified_meta.color_mode}, expected {out_mode}")
        if problems:
            raise ValueError("Export verification failed: " + "; ".join(problems))

        if cancelled():
            raise CancellationException(CANCELLED_MESSAGE)

        # 12. Atomic finalize
        final_path = _finalize_output(temp_file_path, params.output_path, params.overwrite_existing)
        temp_file_path = None
        if final_path != params.output_path:
            notes.append(f"Destination existed; saved as {os.path.basename(final_path)} instead of overwriting.")

        actual_bytes = os.path.getsize(final_path)
        phys_w, phys_h = calculate_physical_size(verified_meta.width, verified_meta.height, params.dpi, PhysicalUnit.INCHES)
        upload_ok, upload_msg = _check_upload_profile(params, verified_meta.width, verified_meta.height, actual_bytes, verified_meta.format)

        progress(100, "Export completed and verified.")

        return JobExecutionResult(
            success=True,
            output_path=final_path,
            target_width=verified_meta.width,
            target_height=verified_meta.height,
            output_dpi=verified_meta.dpi_x,
            physical_width_in=round(phys_w, 2),
            physical_height_in=round(phys_h, 2),
            file_size_bytes=actual_bytes,
            has_alpha=verified_meta.has_alpha,
            format=verified_meta.format,
            method_used=method_desc,
            device_used=device_desc,
            verification_passed=True,
            notes=notes,
            upload_compliant=upload_ok,
            upload_message=upload_msg
        )

    except CancellationException:
        return _failure(params, CANCELLED_MESSAGE)
    except MemoryError as e:
        return _failure(params, str(e) or "Out of memory while processing this image. Use a smaller target size.")
    except Exception as e:
        return _failure(params, str(e))
    finally:
        # Clean up the temporary file whenever it was not finalized
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception:
                pass
        try:
            img.close()
        except Exception:
            pass
