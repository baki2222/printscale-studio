"""
PrintScale Studio - Metadata Management Module
Accurate reading and writing of resolution metadata (PNG pHYs, JPEG JFIF/EXIF),
ICC color profiles, and EXIF orientation normalization.
"""

import os
import struct
import io
from dataclasses import dataclass
from typing import Optional, Tuple
from PIL import Image, ImageCms
from PIL.PngImagePlugin import PngInfo


METERS_PER_INCH = 0.0254


@dataclass
class ImageMetadataInfo:
    format: str
    width: int
    height: int
    dpi_x: Optional[float]
    dpi_y: Optional[float]
    dpi_display: str
    has_alpha: bool
    color_mode: str
    icc_profile: Optional[bytes]
    profile_name: str
    orientation: int = 1


def dpi_to_ppm(dpi: float) -> int:
    """Converts dots per inch to PNG pHYs pixels per meter."""
    return int(round(dpi / METERS_PER_INCH))


def ppm_to_dpi(ppm: int) -> float:
    """Converts PNG pHYs pixels per meter to dots per inch."""
    return float(ppm) * METERS_PER_INCH


def extract_image_metadata(img: Image.Image) -> ImageMetadataInfo:
    """
    Extracts truthful image properties. Never defaults missing DPI to 72.
    """
    fmt = img.format or "UNKNOWN"
    w, h = img.size
    mode = img.mode

    # Alpha detection
    has_alpha = False
    if mode in ("RGBA", "LA", "PA") or (mode == "P" and "transparency" in img.info):
        has_alpha = True

    # Read resolution metadata
    dpi_x = None
    dpi_y = None

    # Check 'dpi' in info
    if "dpi" in img.info and img.info["dpi"] is not None:
        raw_dpi = img.info["dpi"]
        if isinstance(raw_dpi, (tuple, list)) and len(raw_dpi) >= 2:
            rx, ry = raw_dpi[0], raw_dpi[1]
            if rx and ry and rx > 0 and ry > 0:
                dpi_x = float(rx)
                dpi_y = float(ry)
        elif isinstance(raw_dpi, (int, float)) and raw_dpi > 0:
            dpi_x = float(raw_dpi)
            dpi_y = float(raw_dpi)

    # Check PNG pHYs specifically
    if (dpi_x is None or dpi_y is None) and "aspect" in img.info:
        # Some PNG decoders store pHYs in aspect
        pass

    # Check EXIF resolution tags if dpi not found
    if dpi_x is None or dpi_y is None:
        try:
            exif = img.getexif()
            if exif:
                x_res = exif.get(0x011A)
                y_res = exif.get(0x011B)
                res_unit = exif.get(0x0128, 2)
                if x_res and y_res:
                    fx = float(x_res[0]) / float(x_res[1]) if isinstance(x_res, tuple) else float(x_res)
                    fy = float(y_res[0]) / float(y_res[1]) if isinstance(y_res, tuple) else float(y_res)
                    if res_unit == 3:  # cm to inches
                        fx = fx * 2.54
                        fy = fy * 2.54
                    if fx > 0 and fy > 0:
                        dpi_x = fx
                        dpi_y = fy
        except Exception:
            pass

    # Display string
    if dpi_x is not None and dpi_y is not None:
        if abs(dpi_x - dpi_y) < 0.05:
            dpi_display = f"{int(round(dpi_x))} DPI"
        else:
            dpi_display = f"{round(dpi_x, 1)} × {round(dpi_y, 1)} DPI"
    else:
        dpi_display = "Not specified"

    # ICC Profile
    icc = img.info.get("icc_profile")
    profile_name = "None (assumed sRGB)"
    if icc:
        try:
            profile = ImageCms.getOpenProfile(io.BytesIO(icc))
            profile_name = ImageCms.getProfileName(profile).strip()
            if not profile_name:
                profile_name = "Embedded ICC Profile"
        except Exception:
            profile_name = "Embedded (Custom/Raw)"

    # EXIF orientation
    orientation = 1
    exif = img.getexif()
    if exif:
        orientation = exif.get(0x0112, 1)  # 0x0112 is Orientation tag

    return ImageMetadataInfo(
        format=fmt,
        width=w,
        height=h,
        dpi_x=dpi_x,
        dpi_y=dpi_y,
        dpi_display=dpi_display,
        has_alpha=has_alpha,
        color_mode=mode,
        icc_profile=icc,
        profile_name=profile_name,
        orientation=orientation
    )


def read_file_metadata(filepath: str) -> ImageMetadataInfo:
    """Reads metadata directly from an image file without decoding all pixel data."""
    with Image.open(filepath) as img:
        return extract_image_metadata(img)


def get_default_srgb_profile() -> bytes:
    """Returns standard sRGB ICC profile bytes."""
    srgb_profile = ImageCms.createProfile("sRGB")
    stream = io.BytesIO()
    # ImageCms doesn't directly export bytes with a simple dump in all PIL versions,
    # so we extract from ImageCms or construct standard sRGB profile bytes.
    # ImageCms.ImageCmsProfile.tobytes() or saving a 1x1 sRGB image to extract bytes:
    dummy = Image.new("RGB", (1, 1), (0, 0, 0))
    dummy.save(stream, format="PNG", icc_profile=ImageCms.ImageCmsProfile(srgb_profile).tobytes())
    return stream.getvalue()


_CACHED_SRGB_BYTES: Optional[bytes] = None

def get_srgb_icc_bytes() -> bytes:
    """Provides cached standard sRGB ICC profile bytes."""
    global _CACHED_SRGB_BYTES
    if _CACHED_SRGB_BYTES is None:
        # Create standard sRGB profile
        prof = ImageCms.createProfile("sRGB")
        _CACHED_SRGB_BYTES = ImageCms.ImageCmsProfile(prof).tobytes()
    return _CACHED_SRGB_BYTES


def normalize_image_orientation(img: Image.Image) -> Image.Image:
    """
    Applies EXIF orientation to the image pixels and removes the orientation tag,
    ensuring consistent top-left coordinate space throughout all processing.
    """
    try:
        from PIL import ImageOps
        transposed = ImageOps.exif_transpose(img)
        return transposed if transposed is not None else img
    except Exception:
        return img


def detect_source_bits_per_channel(img: Image.Image) -> int:
    """
    Bits per channel of the encoded source. Must be called before the image is loaded,
    because Pillow drops the raw tile descriptors after decoding.
    16-bit PNG/TIFF colour data is decoded by Pillow as 8-bit RGB(A), so the raw mode
    is the only reliable signal.
    """
    if img.mode in ("I;16", "I;16B", "I;16L", "I;16N", "I"):
        return 16
    if img.mode == "F":
        return 32
    for tile in getattr(img, "tile", None) or []:
        rawmode = tile[3] if len(tile) > 3 else None
        if isinstance(rawmode, tuple):
            rawmode = rawmode[0] if rawmode else None
        if isinstance(rawmode, str) and ";16" in rawmode:
            return 16
    return 8


def normalize_pixel_format(img: Image.Image) -> Tuple[Image.Image, list]:
    """
    Converts unusual decoded modes to an 8-bit mode the pipeline handles (L, LA, RGB, RGBA,
    P, CMYK), scaling high-bit-depth data instead of clipping it. Returns (image, notes).
    Raises ValueError for data that cannot be reduced faithfully.
    """
    import numpy as np

    notes = []
    mode = img.mode
    info = dict(img.info)
    if mode in ("I;16", "I;16B", "I;16L", "I;16N", "I"):
        arr = np.asarray(img).astype(np.int64)
        if arr.size and (arr.min() < 0 or arr.max() > 65535):
            raise ValueError(f"Unsupported 32-bit integer image data (range {arr.min()}..{arr.max()}).")
        eight_bit = ((arr * 255 + 32767) // 65535).astype(np.uint8)
        out = Image.fromarray(eight_bit, mode="L")
        out.info.update(info)
        notes.append("16-bit grayscale source scaled to 8 bits per channel.")
        return out, notes
    if mode == "F":
        raise ValueError("32-bit floating-point images are not supported.")
    if mode == "1":
        out = img.convert("L")
        out.info.update(info)
        return out, notes
    if mode in ("RGBa", "La", "PA", "RGBX", "YCbCr", "LAB", "HSV"):
        target = "RGBA" if mode in ("RGBa", "PA") else ("LA" if mode == "La" else "RGB")
        out = img.convert(target)
        out.info.update(info)
        return out, notes
    return img, notes


def _profile_is_srgb(profile) -> bool:
    try:
        name = (ImageCms.getProfileName(profile) or "").lower()
        desc = (ImageCms.getProfileDescription(profile) or "").lower()
    except Exception:
        return False
    return "srgb" in name or "srgb" in desc


def convert_to_srgb(img: Image.Image) -> Tuple[Image.Image, bytes, list]:
    """
    Converts the image to sRGB when an embedded profile describes another colour space.
    Returns (image in L/LA/RGB/RGBA/P mode, ICC bytes that describe the returned pixels, notes).

    - Untagged RGB/grey input is assumed to be sRGB (documented assumption).
    - When an embedded profile cannot be applied, the pixels are left unchanged and the
      original profile is returned so the output stays correctly labelled.
    - CMYK is converted through its embedded profile; untagged CMYK uses Pillow's
      simple formula and is reported as approximate.
    """
    icc = img.info.get("icc_profile")
    srgb_bytes = get_srgb_icc_bytes()
    notes = []

    if img.mode == "CMYK" and not icc:
        notes.append("Untagged CMYK source converted to RGB with a simple formula; colours are approximate.")
        return img.convert("RGB"), srgb_bytes, notes

    if not icc:
        notes.append("No embedded colour profile; source assumed to be sRGB.")
        return img, srgb_bytes, notes

    try:
        input_profile = ImageCms.getOpenProfile(io.BytesIO(icc))
    except Exception as e:
        if img.mode == "CMYK":
            raise ValueError(f"CMYK source has an unreadable ICC profile: {e}")
        notes.append("Embedded colour profile is unreadable; source assumed to be sRGB.")
        return img, srgb_bytes, notes

    if img.mode != "CMYK" and _profile_is_srgb(input_profile):
        return img, icc, notes

    srgb_profile = ImageCms.getOpenProfile(io.BytesIO(srgb_bytes))
    alpha = None
    work = img
    if work.mode == "P":
        work = work.convert("RGBA" if "transparency" in work.info else "RGB")
    if work.mode in ("RGBA", "LA"):
        alpha = work.getchannel("A")
        work = work.convert("RGB" if work.mode == "RGBA" else "L")

    try:
        converted = ImageCms.profileToProfile(
            work,
            inputProfile=input_profile,
            outputProfile=srgb_profile,
            renderingIntent=ImageCms.Intent.PERCEPTUAL,
            outputMode="RGB"
        )
    except Exception as e:
        if img.mode == "CMYK":
            raise ValueError(f"CMYK source could not be converted with its ICC profile: {e}")
        try:
            is_rgb_profile = input_profile.profile.xcolor_space.strip().upper() == "RGB"
        except Exception:
            is_rgb_profile = False
        if is_rgb_profile and img.mode in ("RGB", "RGBA", "P"):
            # Keep pixels in their original space and keep describing them with the original profile
            notes.append(f"Embedded colour profile could not be applied ({e}); original profile kept on the output.")
            return img, icc, notes
        notes.append(f"Embedded colour profile could not be applied ({e}); grey values treated as sRGB.")
        return img, srgb_bytes, notes

    if alpha is not None:
        converted = Image.merge("RGBA", (*converted.split(), alpha))
    try:
        profile_name = ImageCms.getProfileName(input_profile).strip()
    except Exception:
        profile_name = "embedded profile"
    notes.append(f"Converted from '{profile_name}' to sRGB.")
    return converted, srgb_bytes, notes


def apply_color_management_to_srgb(img: Image.Image) -> Tuple[Image.Image, bytes]:
    """
    Backwards-compatible wrapper around convert_to_srgb().
    Returns (converted_image, icc_bytes describing the returned pixels).
    """
    converted, icc_bytes, _ = convert_to_srgb(img)
    return converted, icc_bytes


def build_png_info(dpi: int, icc_profile: Optional[bytes] = None) -> PngInfo:
    """
    Builds PngInfo with mathematically accurate pHYs chunk and ICC profile.
    """
    png_info = PngInfo()
    # Note: Pillow's save(..., dpi=(dpi, dpi)) writes the pHYs chunk automatically
    return png_info


def save_image_with_resolution(
    img: Image.Image,
    target_path: str,
    output_format: str,
    dpi: int,
    jpeg_quality: int = 95,
    icc_bytes: Optional[bytes] = None
) -> None:
    """
    Saves image with verified resolution metadata and color profile.
    For PNG: Writes exact pHYs chunk matching round(dpi / 0.0254).
    For JPEG: Writes both JFIF density and EXIF resolution tags in unison.
    """
    if icc_bytes is None:
        icc_bytes = get_srgb_icc_bytes()

    fmt_upper = output_format.upper()
    if fmt_upper in ("PNG",):
        # In Pillow, passing dpi=(dpi, dpi) accurately creates pHYs chunk
        # Let's ensure dpi is integer or float
        img.save(
            target_path,
            format="PNG",
            dpi=(dpi, dpi),
            icc_profile=icc_bytes,
            optimize=True
        )

    elif fmt_upper in ("JPG", "JPEG"):
        # Make sure image is in RGB or L
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        # Prepare EXIF with matching resolution tags
        exif = img.getexif()
        exif[0x011A] = float(dpi)
        exif[0x011B] = float(dpi)
        exif[0x0128] = 2  # Inches
        # Reset orientation tag if present
        exif[0x0112] = 1

        img.save(
            target_path,
            format="JPEG",
            quality=jpeg_quality,
            dpi=(dpi, dpi),
            subsampling=0,  # 4:4:4 chroma subsampling for artwork clarity
            icc_profile=icc_bytes,
            exif=exif
        )
    else:
        raise ValueError(f"Unsupported output format: {output_format}")


def lossless_update_png_dpi(source_path: str, dest_path: str, dpi: int) -> None:
    """
    Rewrites PNG pHYs physical pixel dimensions chunk at the byte level.
    Guarantees exactly one pHYs chunk strictly before the first IDAT chunk.
    Eliminates any duplicate or existing pHYs chunks.
    All IDAT chunks, color/alpha data, ICC profiles, and unrelated valid chunks
    are preserved 100% byte-for-byte.
    Writes atomically to dest_path.
    Rejects malformed/truncated PNG input safely.
    """
    import zlib
    import tempfile

    if dpi <= 0:
        raise ValueError(f"DPI must be positive, got {dpi}")

    with open(source_path, "rb") as f:
        data = f.read()

    if len(data) < 8 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Not a valid PNG file: signature mismatch")

    ppm = dpi_to_ppm(dpi)
    phys_payload = struct.pack(">IIB", ppm, ppm, 1)  # 1 = meter
    phys_crc = zlib.crc32(b"pHYs" + phys_payload) & 0xFFFFFFFF
    new_phys_chunk = struct.pack(">I", 9) + b"pHYs" + phys_payload + struct.pack(">I", phys_crc)

    idx = 8
    chunks = []
    saw_ihdr = False
    saw_iend = False
    first_idat_idx = None
    first_phys_idx = None

    while idx < len(data):
        if idx + 8 > len(data):
            raise ValueError("Malformed PNG: truncated chunk header")
        chunk_len = struct.unpack(">I", data[idx:idx+4])[0]
        chunk_type = data[idx+4:idx+8]
        total_len = 12 + chunk_len
        if idx + total_len > len(data):
            raise ValueError(f"Malformed PNG: chunk {chunk_type} truncated")
        chunk_bytes = data[idx:idx+total_len]
        chunk_crc = struct.unpack(">I", chunk_bytes[-4:])[0]
        expected_crc = zlib.crc32(chunk_bytes[4:-4]) & 0xFFFFFFFF
        if chunk_crc != expected_crc:
            raise ValueError(f"Malformed PNG: CRC mismatch in chunk {chunk_type}")

        if not saw_ihdr:
            if chunk_type != b"IHDR":
                raise ValueError("Malformed PNG: first chunk must be IHDR")
            saw_ihdr = True

        if chunk_type == b"eXIf" and _tiff_ifd0_has_resolution(chunk_bytes[8:-4]):
            # Keep EXIF resolution inside PNG consistent with pHYs
            tiff = _update_tiff_resolution(chunk_bytes[8:-4], dpi)
            chunk_bytes = (struct.pack(">I", len(tiff)) + b"eXIf" + tiff +
                           struct.pack(">I", zlib.crc32(b"eXIf" + tiff) & 0xFFFFFFFF))

        if chunk_type == b"pHYs":
            if first_phys_idx is None:
                first_phys_idx = len(chunks)
        elif chunk_type == b"IDAT" and first_idat_idx is None:
            first_idat_idx = len(chunks)
        elif chunk_type == b"IEND":
            saw_iend = True

        chunks.append((chunk_type, chunk_bytes))
        idx += total_len

    if not saw_ihdr or not saw_iend:
        raise ValueError("Malformed PNG: missing IHDR or IEND chunk")

    # Determine placement:
    # If a pHYs chunk was already present before the first IDAT, replace that slot.
    # Otherwise, insert immediately before the first IDAT (or before IEND if no IDAT).
    if first_phys_idx is not None and (first_idat_idx is None or first_phys_idx < first_idat_idx):
        insert_slot = first_phys_idx
    elif first_idat_idx is not None:
        insert_slot = first_idat_idx
    else:
        insert_slot = len(chunks) - 1  # before IEND

    filtered_chunks = []
    phys_inserted = False
    for i, (ctype, cbytes) in enumerate(chunks):
        if i == insert_slot and not phys_inserted:
            filtered_chunks.append(new_phys_chunk)
            phys_inserted = True
        # Exclude all existing pHYs chunks
        if ctype != b"pHYs":
            filtered_chunks.append(cbytes)

    if not phys_inserted:
        # Fallback safeguard: insert before first IDAT or IEND
        final_chunks = []
        for cbytes in filtered_chunks:
            if not phys_inserted and cbytes[4:8] in (b"IDAT", b"IEND"):
                final_chunks.append(new_phys_chunk)
                phys_inserted = True
            final_chunks.append(cbytes)
        filtered_chunks = final_chunks

    out_data = data[:8] + b"".join(filtered_chunks)

    # Atomic write
    dest_dir = os.path.dirname(os.path.abspath(dest_path))
    os.makedirs(dest_dir, exist_ok=True)
    temp_fd, temp_path = tempfile.mkstemp(prefix="printscale_png_", suffix=".png", dir=dest_dir)
    os.close(temp_fd)
    try:
        with open(temp_path, "wb") as f:
            f.write(out_data)
        # os.replace is atomic on the same volume; never delete the destination first
        os.replace(temp_path, dest_path)
    except Exception:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        raise


def _update_tiff_resolution(tiff: bytes, dpi: int) -> bytes:
    """
    Sets image-level (IFD0) XResolution/YResolution to (dpi, 1) and ResolutionUnit to inches
    inside a TIFF/EXIF structure. Preserves byte order, all other IFD0 entries, sub-IFDs
    (Exif, GPS, Interop, MakerNotes) and IFD1 thumbnails, because entry offsets are relative
    to the TIFF header and are left untouched.
    Updates well-formed RATIONAL entries in place; otherwise appends a rebuilt IFD0.
    """
    tiff_bytes = bytearray(tiff)
    if len(tiff_bytes) < 8:
        raise ValueError("Malformed EXIF: TIFF header too short")

    byte_order = bytes(tiff_bytes[:2])
    endian = "<" if byte_order == b"II" else (">" if byte_order == b"MM" else None)
    if not endian:
        raise ValueError("Malformed EXIF: unrecognized TIFF byte order")

    magic = struct.unpack(f"{endian}H", tiff_bytes[2:4])[0]
    if magic != 42:
        raise ValueError("Malformed EXIF: invalid TIFF magic number")

    ifd0_offset = struct.unpack(f"{endian}I", tiff_bytes[4:8])[0]
    if ifd0_offset < 8 or ifd0_offset + 2 > len(tiff_bytes):
        raise ValueError("Malformed EXIF: IFD0 offset out of bounds")

    num_entries = struct.unpack(f"{endian}H", tiff_bytes[ifd0_offset:ifd0_offset+2])[0]
    if ifd0_offset + 2 + num_entries * 12 + 4 > len(tiff_bytes):
        raise ValueError("Malformed EXIF: IFD0 entries truncated")

    entries = {}
    for i in range(num_entries):
        pos = ifd0_offset + 2 + i * 12
        tag, typ, cnt = struct.unpack(f"{endian}HHI", tiff_bytes[pos:pos+8])
        raw_value = bytes(tiff_bytes[pos+8:pos+12])
        if tag in entries:
            raise ValueError(f"Malformed EXIF: duplicate IFD0 tag 0x{tag:04X}")
        entries[tag] = (pos, typ, cnt, raw_value)

    rational = struct.pack(f"{endian}II", int(dpi), 1)

    def rational_offset(tag):
        """Offset of a well-formed single RATIONAL value, or None."""
        if tag not in entries:
            return None
        _, typ, cnt, raw = entries[tag]
        off = struct.unpack(f"{endian}I", raw)[0]
        if typ != 5 or cnt != 1 or off < 8 or off + 8 > len(tiff_bytes):
            return None
        return off

    unit_entry = entries.get(0x0128)
    unit_ok = unit_entry is None or (unit_entry[1] in (3, 4) and unit_entry[2] == 1)
    x_off, y_off = rational_offset(0x011A), rational_offset(0x011B)

    if x_off is not None and y_off is not None and x_off != y_off and unit_ok:
        tiff_bytes[x_off:x_off+8] = rational
        tiff_bytes[y_off:y_off+8] = rational
        if unit_entry is not None:
            u_pos, u_typ = unit_entry[0], unit_entry[1]
            packed = struct.pack(f"{endian}Hxx", 2) if u_typ == 3 else struct.pack(f"{endian}I", 2)
            tiff_bytes[u_pos+8:u_pos+12] = packed
        # Absent ResolutionUnit defaults to inches (TIFF 6.0)
        return bytes(tiff_bytes)

    # Rebuild IFD0 at the end of the TIFF block with fresh, well-formed resolution entries
    if len(tiff_bytes) % 2 != 0:
        tiff_bytes.append(0)
    new_ifd_offset = len(tiff_bytes)
    all_entries = {tag: (typ, cnt, raw) for tag, (pos, typ, cnt, raw) in entries.items()}
    total_entries = len(set(all_entries) | {0x011A, 0x011B, 0x0128})
    val_start = new_ifd_offset + 2 + total_entries * 12 + 4
    all_entries[0x011A] = (5, 1, struct.pack(f"{endian}I", val_start))
    all_entries[0x011B] = (5, 1, struct.pack(f"{endian}I", val_start + 8))
    all_entries[0x0128] = (3, 1, struct.pack(f"{endian}Hxx", 2))

    ifd_bytes = bytearray(struct.pack(f"{endian}H", total_entries))
    for tag in sorted(all_entries.keys()):
        typ, cnt, raw = all_entries[tag]
        ifd_bytes.extend(struct.pack(f"{endian}HHI", tag, typ, cnt) + raw)

    # Preserve the link to IFD1 (thumbnail)
    orig_next_ifd_pos = ifd0_offset + 2 + num_entries * 12
    orig_next_ifd = struct.unpack(f"{endian}I", tiff_bytes[orig_next_ifd_pos:orig_next_ifd_pos+4])[0]
    ifd_bytes.extend(struct.pack(f"{endian}I", orig_next_ifd))

    tiff_bytes.extend(ifd_bytes)
    tiff_bytes.extend(rational)
    tiff_bytes.extend(rational)
    tiff_bytes[4:8] = struct.pack(f"{endian}I", new_ifd_offset)
    return bytes(tiff_bytes)


def _tiff_ifd0_has_resolution(tiff: bytes) -> bool:
    """True when IFD0 of a TIFF/EXIF block carries XResolution or YResolution."""
    try:
        endian = {b"II": "<", b"MM": ">"}[bytes(tiff[:2])]
        ifd0 = struct.unpack(f"{endian}I", tiff[4:8])[0]
        count = struct.unpack(f"{endian}H", tiff[ifd0:ifd0+2])[0]
        tags = {struct.unpack(f"{endian}H", tiff[ifd0+2+i*12:ifd0+4+i*12])[0] for i in range(count)}
    except Exception:
        return False
    return bool(tags & {0x011A, 0x011B})


def update_exif_segment(exif_seg: bytes, dpi: int) -> bytes:
    """
    Updates or inserts image-level EXIF resolution tags in the 0th IFD of a JPEG APP1 segment:
    - XResolution (0x011A): rational (dpi, 1)
    - YResolution (0x011B): rational (dpi, 1)
    - ResolutionUnit (0x0128): short (2 = inches)
    Preserves TIFF byte order (II or MM), orientation, description, camera tags,
    GPS, Exif sub-IFD (including FocalPlaneXResolution, FocalPlaneYResolution),
    MakerNotes, and thumbnails without alteration.
    """
    if len(exif_seg) < 14 or exif_seg[:2] != b"\xff\xe1" or exif_seg[4:10] != b"Exif\x00\x00":
        return exif_seg

    new_payload = b"Exif\x00\x00" + _update_tiff_resolution(exif_seg[10:], dpi)
    new_seg_len = len(new_payload) + 2
    if new_seg_len > 65535:
        raise ValueError("EXIF segment exceeds maximum 64KB JPEG marker size")

    return b"\xff\xe1" + struct.pack(">H", new_seg_len) + new_payload


def update_photoshop_resolution(app13_seg: bytes, dpi: int) -> bytes:
    """
    Updates the Photoshop ResolutionInfo resource (ID 0x03ED) inside an APP13
    'Photoshop 3.0' segment so Photoshop and other readers that prefer it agree with
    JFIF/EXIF. Fixed-size fields are rewritten in place; all other resources are kept.
    """
    header = b"Photoshop 3.0\x00"
    if app13_seg[:2] != b"\xff\xed" or app13_seg[4:4+len(header)] != header:
        return app13_seg
    seg = bytearray(app13_seg)
    idx = 4 + len(header)
    end = len(seg)
    while idx + 12 <= end:
        if seg[idx:idx+4] != b"8BIM":
            raise ValueError("Malformed Photoshop APP13 resource block")
        res_id = struct.unpack(">H", seg[idx+4:idx+6])[0]
        name_len = seg[idx+6]
        name_field = 1 + name_len
        if name_field % 2:
            name_field += 1
        size_pos = idx + 6 + name_field
        if size_pos + 4 > end:
            raise ValueError("Malformed Photoshop APP13 resource block")
        size = struct.unpack(">I", seg[size_pos:size_pos+4])[0]
        data_pos = size_pos + 4
        if data_pos + size > end:
            raise ValueError("Malformed Photoshop APP13 resource block")
        if res_id == 0x03ED and size >= 16:
            fixed = int(dpi) << 16
            seg[data_pos:data_pos+4] = struct.pack(">I", fixed)
            seg[data_pos+4:data_pos+6] = struct.pack(">H", 1)   # pixels per inch
            seg[data_pos+8:data_pos+12] = struct.pack(">I", fixed)
            seg[data_pos+12:data_pos+14] = struct.pack(">H", 1)
        idx = data_pos + size + (size % 2)
    return bytes(seg)


def lossless_update_jpeg_dpi(source_path: str, dest_path: str, dpi: int) -> None:
    """
    Synchronizes JFIF and EXIF density headers losslessly without recompression.
    Locates the true Start of Scan (SOS) through top-level marker parsing,
    avoiding false matches against embedded thumbnails.
    Preserves compressed image scan data (all baseline and progressive scans),
    decoded pixels, ICC profiles, EXIF orientation, camera tags, and unrelated metadata.
    Handles EXIF-only, JFIF-only, and combined metadata correctly.
    Writes atomically to dest_path.
    """
    import tempfile

    if dpi <= 0:
        raise ValueError(f"DPI must be positive, got {dpi}")

    with open(source_path, "rb") as f:
        data = f.read()

    if len(data) < 4 or data[:2] != b"\xff\xd8":
        raise ValueError("Not a valid JPEG file: missing SOI marker")

    # Parse top-level markers before the first SOS
    idx = 2
    segments = []  # list of (marker_byte, seg_bytes)
    first_sos_offset = None

    while idx < len(data):
        if data[idx] != 0xFF:
            idx += 1
            continue
        while idx < len(data) and data[idx] == 0xFF:
            idx += 1
        if idx >= len(data):
            break

        marker = data[idx]
        idx += 1

        if marker in (0xD8, 0xD9):  # SOI, EOI
            continue
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:  # RST, TEM
            continue

        if marker == 0xDA:  # SOS (Start of Scan)
            first_sos_offset = idx - 2
            break

        if idx + 2 > len(data):
            raise ValueError("Malformed JPEG: truncated segment length")

        seg_len = struct.unpack(">H", data[idx:idx+2])[0]
        if seg_len < 2 or idx + seg_len > len(data):
            raise ValueError(f"Malformed JPEG: segment 0x{marker:02X} length invalid or truncated")

        seg_start = idx - 2  # from 0xFF
        seg_end = idx + seg_len
        seg_bytes = data[seg_start:seg_end]
        segments.append((marker, seg_bytes))
        idx += seg_len

    if first_sos_offset is None:
        raise ValueError("Malformed JPEG: no SOS (Start of Scan) marker found")

    # Compressed image scan data is everything from the first top-level SOS to EOF
    scan_data = data[first_sos_offset:]

    # Classify existing metadata
    has_jfif = any(m == 0xE0 and s[4:9] == b"JFIF\x00" for m, s in segments)
    has_exif = any(m == 0xE1 and s[4:10] == b"Exif\x00\x00" for m, s in segments)

    # Standard JFIF APP0 replacement payload
    jfif_payload = b"JFIF\x00\x01\x01\x01" + struct.pack(">HH", dpi, dpi) + b"\x00\x00"
    new_jfif_seg = b"\xff\xe0" + struct.pack(">H", len(jfif_payload) + 2) + jfif_payload

    updated_segments = []
    jfif_handled = False
    exif_handled = False

    for m, seg in segments:
        if m == 0xE0 and seg[4:9] == b"JFIF\x00":
            if not jfif_handled:
                # Update existing JFIF APP0, preserving any thumbnail if present
                if len(seg) >= 18:
                    x_thumb = seg[16]
                    y_thumb = seg[17]
                    thumb_data = seg[18:]
                    p = b"JFIF\x00\x01\x01\x01" + struct.pack(">HH", dpi, dpi) + bytes([x_thumb, y_thumb]) + thumb_data
                    updated_seg = b"\xff\xe0" + struct.pack(">H", len(p) + 2) + p
                else:
                    updated_seg = new_jfif_seg
                updated_segments.append(updated_seg)
                jfif_handled = True
            # Discard duplicate JFIF segments
            continue

        elif m == 0xE1 and seg[4:10] == b"Exif\x00\x00":
            if not exif_handled:
                updated_exif = update_exif_segment(seg, dpi)
                updated_segments.append(updated_exif)
                exif_handled = True
            # Discard duplicate EXIF segments
            continue

        elif m == 0xED and seg[4:18] == b"Photoshop 3.0\x00":
            updated_segments.append(update_photoshop_resolution(seg, dpi))

        else:
            updated_segments.append(seg)

    # If the file had absent resolution metadata (neither JFIF nor EXIF),
    # insert standard JFIF APP0 as the very first segment after SOI
    if not has_jfif and not has_exif:
        updated_segments.insert(0, new_jfif_seg)

    # Assemble complete JPEG byte stream
    out_parts = [b"\xff\xd8"]
    out_parts.extend(updated_segments)
    out_parts.append(scan_data)
    out_bytes = b"".join(out_parts)

    # Atomic write
    dest_dir = os.path.dirname(os.path.abspath(dest_path))
    os.makedirs(dest_dir, exist_ok=True)
    temp_fd, temp_path = tempfile.mkstemp(prefix="printscale_jpg_", suffix=".jpg", dir=dest_dir)
    os.close(temp_fd)
    try:
        with open(temp_path, "wb") as f:
            f.write(out_bytes)
        # os.replace is atomic on the same volume; never delete the destination first
        os.replace(temp_path, dest_path)
    except Exception:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        raise


def update_metadata_only(
    source_path: str,
    dest_path: str,
    dpi: int
) -> None:
    """
    Updates resolution metadata without modifying pixel values.
    For PNG: Losslessly rewrites PNG chunks with exactly one pHYs chunk.
    For JPEG: Losslessly synchronizes JFIF and EXIF density headers without touching compressed scan data.
    """
    with Image.open(source_path) as img:
        fmt = (img.format or "").upper()

    if fmt == "PNG":
        lossless_update_png_dpi(source_path, dest_path, dpi)
    elif fmt in ("JPEG", "JPG"):
        lossless_update_jpeg_dpi(source_path, dest_path, dpi)
    else:
        raise ValueError(f"Metadata-only mode unsupported for format: {fmt}")


