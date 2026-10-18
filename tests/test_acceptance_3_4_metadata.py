"""
Acceptance Checks 3 & 4: Metadata Precision, Round-Tripping, and Lossless Metadata Updates.
"""

import os
import numpy as np
from PIL import Image

from printscale.core.geometry import DimensionMode
from printscale.core.pipeline import JobParameters, execute_pipeline
from printscale.core.metadata import read_file_metadata


def test_acceptance_3_metadata_only_preserves_pixels(tmp_path):
    """
    Check 3: Metadata-only PNG export preserves decoded color and alpha values exactly.
    """
    src_file = str(tmp_path / "original_artwork.png")
    out_file = str(tmp_path / "metadata_updated.png")

    # Create distinct pattern with translucent and opaque RGBA pixels
    np.random.seed(42)
    original_arr = np.random.randint(0, 256, (120, 150, 4), dtype=np.uint8)
    # Ensure variety of alpha
    original_arr[:, :, 3] = np.random.randint(0, 256, (120, 150), dtype=np.uint8)
    
    orig_img = Image.fromarray(original_arr, mode="RGBA")
    orig_img.save(src_file, format="PNG")

    # Run metadata-only pipeline to update resolution to 600 DPI
    params = JobParameters(
        source_path=src_file,
        output_path=out_file,
        output_format="PNG",
        dimension_mode=DimensionMode.METADATA_ONLY,
        dpi=600
    )
    result = execute_pipeline(params)
    assert result.success is True

    # Reopen and compare every single byte of decoded color and alpha
    with Image.open(out_file) as reloaded:
        reloaded_arr = np.array(reloaded, dtype=np.uint8)

    # Must be 100% bitwise identical
    assert np.array_equal(original_arr, reloaded_arr), "Metadata-only altered decoded pixels or alpha!"

    # Verify that DPI was updated to 600
    meta = read_file_metadata(out_file)
    assert meta.dpi_x is not None
    assert abs(meta.dpi_x - 600) < 0.03


def test_acceptance_4_png_dpi_roundtrip(tmp_path):
    """
    Check 4: PNG DPI round-trips within 0.03 DPI across all standard and custom DPI values.
    """
    for dpi in [300, 400, 500, 600, 350, 720]:
        src_file = str(tmp_path / f"test_src_{dpi}.png")
        out_file = str(tmp_path / f"test_out_{dpi}.png")

        im = Image.new("RGBA", (100, 100), (120, 140, 180, 255))
        im.save(src_file, format="PNG")

        params = JobParameters(
            source_path=src_file,
            output_path=out_file,
            output_format="PNG",
            dimension_mode=DimensionMode.METADATA_ONLY,
            dpi=dpi
        )
        res = execute_pipeline(params)
        assert res.success is True

        meta = read_file_metadata(out_file)
        assert meta.dpi_x is not None
        diff = abs(meta.dpi_x - dpi)
        assert diff < 0.03, f"Failed roundtrip for {dpi} DPI: got {meta.dpi_x}, diff {diff}"


def test_acceptance_4_jpeg_density_agreement(tmp_path):
    """
    Check 4: JPEG density metadata agrees between JFIF and EXIF tags.
    """
    src_file = str(tmp_path / "test_photo.jpg")
    out_file = str(tmp_path / "test_photo_out.jpg")

    im = Image.new("RGB", (200, 200), (200, 100, 50))
    im.save(src_file, format="JPEG", quality=95)

    params = JobParameters(
        source_path=src_file,
        output_path=out_file,
        output_format="JPEG",
        dimension_mode=DimensionMode.PIXEL_DIMS,
        pixel_width=400,
        pixel_height=400,
        dpi=400
    )
    res = execute_pipeline(params)
    assert res.success is True

    # Inspect reopen metadata
    meta = read_file_metadata(out_file)
    assert meta.dpi_x is not None
    assert abs(meta.dpi_x - 400) < 0.01

    with Image.open(out_file) as jimg:
        # Check JFIF density
        jfif_dpi = jimg.info.get("dpi")
        if jfif_dpi:
            assert abs(jfif_dpi[0] - 400) < 0.1
        # Check EXIF density tags
        exif = jimg.getexif()
        assert float(exif.get(0x011A)) == 400.0  # XResolution
        assert float(exif.get(0x011B)) == 400.0  # YResolution
        assert exif.get(0x0128) == 2            # ResolutionUnit = inches


def test_acceptance_6_jpeg_lossless_metadata_scan_data_unchanged(tmp_path):
    """
    Check 6: For JPEG metadata-only updates, demonstrates that the compressed image
    scan data is unchanged and confirms unchanged decoded pixels using the same decoder.
    """
    src_file = str(tmp_path / "scan_data_test.jpg")
    out_file = str(tmp_path / "scan_data_updated.jpg")

    # Create random textured JPEG
    np.random.seed(123)
    pixels = np.random.randint(0, 256, (128, 128, 3), dtype=np.uint8)
    orig_im = Image.fromarray(pixels, mode="RGB")
    orig_im.save(src_file, format="JPEG", quality=90)

    # Read original file bytes
    with open(src_file, "rb") as f:
        orig_bytes = f.read()

    # Update metadata to 500 DPI via pipeline
    params = JobParameters(
        source_path=src_file,
        output_path=out_file,
        output_format="JPEG",
        dimension_mode=DimensionMode.METADATA_ONLY,
        dpi=500
    )
    res = execute_pipeline(params)
    assert res.success is True

    # Verify scan data using proper marker parsing
    orig_scan = parse_jpeg_metadata_and_scan(src_file)["scan_data"]
    updated_scan = parse_jpeg_metadata_and_scan(out_file)["scan_data"]
    assert orig_scan == updated_scan, "JPEG scan data was altered or re-encoded!"

    # Verify decoded pixels are 100% bitwise identical
    with Image.open(src_file) as img1, Image.open(out_file) as img2:
        assert np.array_equal(np.array(img1), np.array(img2)), "Decoded pixels differ after lossless metadata update!"
        assert img2.info.get("dpi") == (500, 500)


def parse_png_chunks_raw(filepath: str):
    """Independent PNG chunk parser and CRC validator."""
    import struct
    import zlib
    with open(filepath, "rb") as f:
        data = f.read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "Invalid PNG signature"
    idx = 8
    chunks = []
    while idx < len(data):
        chunk_len = struct.unpack(">I", data[idx:idx+4])[0]
        chunk_type = data[idx+4:idx+8]
        chunk_data = data[idx+8:idx+8+chunk_len]
        chunk_crc = struct.unpack(">I", data[idx+8+chunk_len:idx+12+chunk_len])[0]
        expected_crc = zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
        assert chunk_crc == expected_crc, f"CRC mismatch in chunk {chunk_type}"
        chunks.append((chunk_type, chunk_data, chunk_crc))
        idx += 12 + chunk_len
    return chunks


def parse_jpeg_metadata_and_scan(filepath: str):
    """Independent JPEG top-level marker parser extracting JFIF, EXIF, and scan data."""
    import struct
    with open(filepath, "rb") as f:
        data = f.read()
    assert data[:2] == b"\xff\xd8", "Missing JPEG SOI marker"
    idx = 2
    segments = []
    first_sos = None
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
        if marker in (0xD8, 0xD9) or (0xD0 <= marker <= 0xD7) or marker == 0x01:
            continue
        if marker == 0xDA:
            first_sos = idx - 2
            break
        seg_len = struct.unpack(">H", data[idx:idx+2])[0]
        seg_bytes = data[idx-2:idx+seg_len]
        segments.append((marker, seg_bytes))
        idx += seg_len

    assert first_sos is not None, "Missing SOS marker in JPEG"
    scan_data = data[first_sos:]

    # Parse JFIF APP0
    jfif_info = None
    jfif_count = 0
    for m, s in segments:
        if m == 0xE0 and s[4:9] == b"JFIF\x00":
            jfif_count += 1
            if jfif_info is None:
                units = s[11]
                xd, yd = struct.unpack(">HH", s[12:16])
                jfif_info = {"units": units, "x": xd, "y": yd}

    # Parse EXIF APP1
    exif_info = None
    exif_count = 0
    for m, s in segments:
        if m == 0xE1 and s[4:10] == b"Exif\x00\x00":
            exif_count += 1
            if exif_info is None:
                tiff = s[10:]
                endian = "<" if tiff[:2] == b"II" else ">"
                ifd0_off = struct.unpack(f"{endian}I", tiff[4:8])[0]
                num_e = struct.unpack(f"{endian}H", tiff[ifd0_off:ifd0_off+2])[0]
                tags = {}
                for i in range(num_e):
                    pos = ifd0_off + 2 + i * 12
                    tag, typ, cnt, val = struct.unpack(f"{endian}HHII", tiff[pos:pos+12])
                    if tag in (0x011A, 0x011B) and typ == 5:
                        num, den = struct.unpack(f"{endian}II", tiff[val:val+8])
                        tags[tag] = float(num) / float(den) if den else 0.0
                    elif tag == 0x0128 and typ == 3:
                        u_val = struct.unpack(f"{endian}H", tiff[pos+8:pos+10])[0]
                        tags[tag] = u_val
                    else:
                        tags[tag] = val
                tags["_endian"] = endian
                exif_info = tags

    return {
        "segments": segments,
        "jfif": jfif_info,
        "jfif_count": jfif_count,
        "exif": exif_info,
        "exif_count": exif_count,
        "scan_data": scan_data
    }


def test_png_prevent_duplicate_phys_and_repeated_updates(tmp_path):
    """
    Edge Case 1: Tests that metadata-only PNG export:
    - Guarantees exactly one pHYs chunk strictly before the first IDAT.
    - Eliminates pre-existing duplicate pHYs chunks.
    - Preserves IDAT payloads 100% byte-for-byte across repeated cycles (300 -> 400 -> 500 -> 600 -> 300).
    - Preserves decoded pixels and alpha bitwise identically.
    - Handles transparent RGBA, palette PNG ('P'), and images with no DPI.
    """
    import struct
    import zlib

    # 1. Prepare 5 test fixtures
    fixtures = {}

    # Fixture A: PNG with no DPI
    im_no_dpi = Image.new("RGB", (64, 64), (100, 150, 200))
    path_a = str(tmp_path / "fixture_a_no_dpi.png")
    im_no_dpi.save(path_a, format="PNG")
    fixtures["no_dpi"] = path_a

    # Fixture B: PNG already at 300 DPI
    im_300 = Image.new("RGB", (64, 64), (50, 80, 120))
    path_b = str(tmp_path / "fixture_b_300dpi.png")
    im_300.save(path_b, format="PNG", dpi=(300, 300))
    fixtures["already_300"] = path_b

    # Fixture C: PNG with duplicate pHYs chunks crafted intentionally
    im_base = Image.new("RGB", (64, 64), (200, 100, 50))
    path_c_temp = str(tmp_path / "fixture_c_temp.png")
    path_c = str(tmp_path / "fixture_c_duplicate_phys.png")
    im_base.save(path_c_temp, format="PNG", dpi=(300, 300))
    with open(path_c_temp, "rb") as f:
        c_bytes = f.read()
    # Inject an extra pHYs chunk immediately after IHDR
    ppm = int(round(300 / 0.0254))
    phys_pay = struct.pack(">IIB", ppm, ppm, 1)
    phys_crc = zlib.crc32(b"pHYs" + phys_pay) & 0xFFFFFFFF
    extra_phys = struct.pack(">I", 9) + b"pHYs" + phys_pay + struct.pack(">I", phys_crc)
    # Put extra_phys after IHDR (which is at index 8, length 12+13 = 25)
    ihdr_end = 8 + 12 + 13
    double_phys_data = c_bytes[:ihdr_end] + extra_phys + c_bytes[ihdr_end:]
    with open(path_c, "wb") as f:
        f.write(double_phys_data)
    assert double_phys_data.count(b"pHYs") == 2, "Fixture C must have 2 pHYs chunks"
    fixtures["duplicate_phys"] = path_c

    # Fixture D: Transparent RGBA PNG
    np.random.seed(99)
    rgba_arr = np.random.randint(0, 256, (64, 64, 4), dtype=np.uint8)
    im_rgba = Image.fromarray(rgba_arr, mode="RGBA")
    path_d = str(tmp_path / "fixture_d_transparent.png")
    im_rgba.save(path_d, format="PNG")
    fixtures["transparent"] = path_d

    # Fixture E: Palette PNG ('P' mode with palette and transparency)
    im_p = Image.new("P", (64, 64))
    im_p.putpalette([i % 256 for i in range(768)])
    path_e = str(tmp_path / "fixture_e_palette.png")
    im_p.save(path_e, format="PNG", transparency=0)
    fixtures["palette"] = path_e

    # Cycle through 300 -> 400 -> 500 -> 600 -> 300
    cycle_dpis = [300, 400, 500, 600, 300]

    for name, initial_path in fixtures.items():
        # Record original IDAT bytes and decoded pixels
        orig_chunks = parse_png_chunks_raw(initial_path)
        orig_idat_payload = b"".join(c[1] for c in orig_chunks if c[0] == b"IDAT")
        with Image.open(initial_path) as orig_img:
            orig_pixels = np.array(orig_img)

        curr_src = initial_path
        for step, target_dpi in enumerate(cycle_dpis):
            curr_out = str(tmp_path / f"output_{name}_step{step}_{target_dpi}dpi.png")
            params = JobParameters(
                source_path=curr_src,
                output_path=curr_out,
                output_format="PNG",
                dimension_mode=DimensionMode.METADATA_ONLY,
                dpi=target_dpi
            )
            result = execute_pipeline(params)
            assert result.success is True, f"Failed at {name} step {step} ({target_dpi} DPI): {result.error_message}"

            # Independent chunk assertions
            chunks = parse_png_chunks_raw(curr_out)
            phys_chunks = [c for c in chunks if c[0] == b"pHYs"]
            idat_chunks = [c for c in chunks if c[0] == b"IDAT"]

            # 1. Assert EXACTLY ONE pHYs chunk
            assert len(phys_chunks) == 1, f"Expected 1 pHYs chunk in {name} step {step}, found {len(phys_chunks)}"

            # 2. Assert pHYs is before the first IDAT
            phys_index = [i for i, c in enumerate(chunks) if c[0] == b"pHYs"][0]
            first_idat_index = [i for i, c in enumerate(chunks) if c[0] == b"IDAT"][0]
            assert phys_index < first_idat_index, f"pHYs chunk ({phys_index}) must precede first IDAT ({first_idat_index})"

            # 3. Assert valid density and CRC
            expected_ppm = int(round(target_dpi / 0.0254))
            c_type, c_data, c_crc = phys_chunks[0]
            ppm_x, ppm_y, unit = struct.unpack(">IIB", c_data)
            assert unit == 1, f"Unit specifier must be 1 (meters), got {unit}"
            assert ppm_x == expected_ppm and ppm_y == expected_ppm, f"Expected {expected_ppm} ppm, got {ppm_x}x{ppm_y}"

            # 4. Assert IDAT payloads are 100% byte-for-byte identical to original
            current_idat_payload = b"".join(c[1] for c in idat_chunks)
            assert current_idat_payload == orig_idat_payload, f"IDAT payload altered in {name} step {step}!"

            # 5. Assert decoded pixels and alpha are 100% bitwise identical
            with Image.open(curr_out) as updated_img:
                updated_pixels = np.array(updated_img)
                assert np.array_equal(orig_pixels, updated_pixels), f"Decoded pixels altered in {name} step {step}!"

            # Advance chain to test repeated edits on the same file
            curr_src = curr_out


def test_png_reject_malformed_input(tmp_path):
    """
    Verifies that malformed, corrupted, or truncated PNG files are safely rejected
    without leaving successful-looking output files on disk.
    """
    # 1. Truncated PNG
    trunc_path = str(tmp_path / "truncated.png")
    out_path = str(tmp_path / "out_trunc.png")
    with open(trunc_path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

    params = JobParameters(
        source_path=trunc_path,
        output_path=out_path,
        output_format="PNG",
        dimension_mode=DimensionMode.METADATA_ONLY,
        dpi=300
    )
    res = execute_pipeline(params)
    assert res.success is False
    assert not os.path.exists(out_path)

    # 2. Corrupt CRC PNG
    im = Image.new("RGB", (20, 20), (255, 0, 0))
    good_png = str(tmp_path / "good.png")
    im.save(good_png, format="PNG")
    with open(good_png, "rb") as f:
        good_bytes = bytearray(f.read())
    # Corrupt a byte in the IHDR CRC
    good_bytes[25] ^= 0xFF
    corrupt_png = str(tmp_path / "corrupt_crc.png")
    out_corrupt = str(tmp_path / "out_corrupt.png")
    with open(corrupt_png, "wb") as f:
        f.write(good_bytes)

    params = JobParameters(
        source_path=corrupt_png,
        output_path=out_corrupt,
        output_format="PNG",
        dimension_mode=DimensionMode.METADATA_ONLY,
        dpi=300
    )
    res2 = execute_pipeline(params)
    assert res2.success is False
    assert not os.path.exists(out_corrupt)


def test_jpeg_synchronize_jfif_and_exif_density_lossless(tmp_path):
    """
    Edge Case 2: Tests that metadata-only JPEG export:
    - Synchronizes JFIF and EXIF density headers losslessly.
    - Preserves compressed image scan data 100% byte-for-byte.
    - Preserves decoded pixels bitwise identically.
    - Does NOT overwrite camera focal-plane resolution tags or orientation.
    - Handles conflicting JFIF/EXIF, matching values, absent metadata,
      progressive encoding, and EXIF-only metadata without recompression.
    """
    # Prepare fixtures
    fixtures = {}

    # Fixture 1: Conflicting JFIF (300) and EXIF (72)
    im1 = Image.new("RGB", (64, 64), (120, 180, 220))
    ex1 = im1.getexif()
    ex1[0x011A] = 72.0
    ex1[0x011B] = 72.0
    ex1[0x0128] = 2
    ex1[0x0112] = 1  # Orientation
    path1 = str(tmp_path / "fixture1_conflicting.jpg")
    im1.save(path1, format="JPEG", dpi=(300, 300), exif=ex1, quality=92)
    fixtures["conflicting"] = path1

    # Fixture 2: Matching JFIF (300) and EXIF (300)
    im2 = Image.new("RGB", (64, 64), (220, 120, 180))
    ex2 = im2.getexif()
    ex2[0x011A] = 300.0
    ex2[0x011B] = 300.0
    ex2[0x0128] = 2
    path2 = str(tmp_path / "fixture2_matching.jpg")
    im2.save(path2, format="JPEG", dpi=(300, 300), exif=ex2, quality=92)
    fixtures["matching"] = path2

    # Fixture 3: Absent resolution metadata (no JFIF APP0, no EXIF)
    im3 = Image.new("RGB", (64, 64), (80, 160, 90))
    path3_raw = str(tmp_path / "fixture3_raw.jpg")
    im3.save(path3_raw, format="JPEG", quality=90)
    # Strip JFIF APP0 marker if Pillow created it
    with open(path3_raw, "rb") as f:
        d3 = f.read()
    if d3[2:4] == b"\xff\xe0":
        L = (d3[4] << 8) | d3[5]
        d3_no_jfif = d3[:2] + d3[2+2+L:]
    else:
        d3_no_jfif = d3
    path3 = str(tmp_path / "fixture3_absent.jpg")
    with open(path3, "wb") as f:
        f.write(d3_no_jfif)
    fixtures["absent"] = path3

    # Fixture 4: Progressive JPEG encoding
    im4 = Image.new("RGB", (64, 64), (200, 140, 70))
    path4 = str(tmp_path / "fixture4_progressive.jpg")
    im4.save(path4, format="JPEG", progressive=True, quality=90)
    fixtures["progressive"] = path4

    # Fixture 5: EXIF-only JPEG (EXIF 72 DPI, stripped JFIF)
    im5 = Image.new("RGB", (64, 64), (140, 200, 170))
    ex5 = im5.getexif()
    ex5[0x011A] = 72.0
    ex5[0x011B] = 72.0
    ex5[0x0128] = 2
    path5_tmp = str(tmp_path / "fixture5_tmp.jpg")
    im5.save(path5_tmp, format="JPEG", exif=ex5, quality=92)
    with open(path5_tmp, "rb") as f:
        d5 = f.read()
    # Strip JFIF APP0 to make it strictly EXIF-only
    if d5[2:4] == b"\xff\xe0":
        L = (d5[4] << 8) | d5[5]
        d5_exif_only = d5[:2] + d5[2+2+L:]
    else:
        d5_exif_only = d5
    path5 = str(tmp_path / "fixture5_exif_only.jpg")
    with open(path5, "wb") as f:
        f.write(d5_exif_only)
    fixtures["exif_only"] = path5

    # Fixture 6: JPEG with Camera Focal-Plane Resolution tags in Exif sub-IFD
    from PIL import ExifTags
    im6 = Image.new("RGB", (64, 64), (180, 80, 120))
    ex6 = im6.getexif()
    ex6[0x011A] = 72.0
    ex6[0x011B] = 72.0
    ex6[0x0128] = 2
    ex6[0x0112] = 3  # Orientation 180 deg
    exif_sub = ex6.get_ifd(ExifTags.IFD.Exif)
    # FocalPlaneXResolution (0xA20E) & FocalPlaneYResolution (0xA20F)
    exif_sub[0xA20E] = 3500.0
    exif_sub[0xA20F] = 3500.0
    exif_sub[0xA210] = 2  # inches
    path6 = str(tmp_path / "fixture6_camera.jpg")
    im6.save(path6, format="JPEG", exif=ex6, quality=92)
    fixtures["camera_tags"] = path6

    test_dpis = [300, 400, 500, 600]

    for name, src_path in fixtures.items():
        # Parse original metadata and extract scan data
        orig_parsed = parse_jpeg_metadata_and_scan(src_path)
        orig_scan_data = orig_parsed["scan_data"]
        with Image.open(src_path) as orig_im:
            orig_pixels = np.array(orig_im)

        for target_dpi in test_dpis:
            out_path = str(tmp_path / f"out_{name}_{target_dpi}dpi.jpg")
            params = JobParameters(
                source_path=src_path,
                output_path=out_path,
                output_format="JPEG",
                dimension_mode=DimensionMode.METADATA_ONLY,
                dpi=target_dpi
            )
            result = execute_pipeline(params)
            assert result.success is True, f"Failed for {name} at {target_dpi} DPI: {result.error_message}"

            # 1. Independent scan data comparison: must be 100% byte-for-byte identical
            updated_parsed = parse_jpeg_metadata_and_scan(out_path)
            updated_scan_data = updated_parsed["scan_data"]
            assert updated_scan_data == orig_scan_data, f"Scan data altered in {name} at {target_dpi} DPI!"

            # 2. Decoded pixel comparison: must be bitwise identical
            with Image.open(out_path) as updated_im:
                updated_pixels = np.array(updated_im)
                assert np.array_equal(orig_pixels, updated_pixels), f"Decoded pixels altered in {name} at {target_dpi} DPI!"

            # 3. Check JFIF density if present
            if updated_parsed["jfif"]:
                assert updated_parsed["jfif"]["units"] == 1, f"JFIF units must be 1 (inches), got {updated_parsed['jfif']['units']}"
                assert updated_parsed["jfif"]["x"] == target_dpi, f"JFIF X density mismatch: expected {target_dpi}, got {updated_parsed['jfif']['x']}"
                assert updated_parsed["jfif"]["y"] == target_dpi, f"JFIF Y density mismatch: expected {target_dpi}, got {updated_parsed['jfif']['y']}"

            # 4. Check EXIF density if present
            if updated_parsed["exif"]:
                assert updated_parsed["exif"].get(0x011A) == float(target_dpi), f"EXIF XResolution mismatch: expected {target_dpi}, got {updated_parsed['exif'].get(0x011A)}"
                assert updated_parsed["exif"].get(0x011B) == float(target_dpi), f"EXIF YResolution mismatch: expected {target_dpi}, got {updated_parsed['exif'].get(0x011B)}"
                assert updated_parsed["exif"].get(0x0128) == 2, f"EXIF ResolutionUnit must be 2 (inches), got {updated_parsed['exif'].get(0x0128)}"

            # 5. Check agreement when both exist
            if updated_parsed["jfif"] and updated_parsed["exif"]:
                assert updated_parsed["jfif"]["x"] == int(round(updated_parsed["exif"][0x011A]))
                assert updated_parsed["jfif"]["y"] == int(round(updated_parsed["exif"][0x011B]))

            # 6. Verify camera tags and orientation preservation
            if name == "camera_tags":
                with Image.open(out_path) as cam_im:
                    cam_exif = cam_im.getexif()
                    assert cam_exif.get(0x0112) == 3, "EXIF Orientation tag was lost or altered!"
                    sub = cam_exif.get_ifd(ExifTags.IFD.Exif)
                    assert sub.get(0xA20E) == 3500.0, "FocalPlaneXResolution in Exif sub-IFD was overwritten!"
                    assert sub.get(0xA20F) == 3500.0, "FocalPlaneYResolution in Exif sub-IFD was overwritten!"
                    assert sub.get(0xA210) == 2, "FocalPlaneResolutionUnit in Exif sub-IFD was overwritten!"

            # 7. Verify no duplicate headers
            assert updated_parsed["jfif_count"] <= 1, "Duplicate JFIF headers detected"
            assert updated_parsed["exif_count"] <= 1, "Duplicate EXIF headers detected"


def test_jpeg_marker_parsing_not_fooled_by_embedded_thumbnail(tmp_path):
    """
    Verifies that top-level marker parsing correctly ignores any 0xFF 0xDA (SOS)
    marker inside an embedded thumbnail JPEG in EXIF APP1, preserving the true
    full-resolution image scan data.
    """
    import io

    # Create thumbnail JPEG
    thumb_im = Image.new("RGB", (12, 12), (255, 100, 50))
    thumb_buf = io.BytesIO()
    thumb_im.save(thumb_buf, format="JPEG", quality=50)
    thumb_bytes = thumb_buf.getvalue()
    assert b"\xff\xda" in thumb_bytes, "Thumbnail must contain an SOS marker"

    # Create main image JPEG with thumbnail in EXIF
    main_im = Image.new("RGB", (128, 128), (40, 80, 160))
    ex = main_im.getexif()
    ex[0x011A] = 72.0
    ex[0x011B] = 72.0
    ex[0x0128] = 2
    # Attach thumbnail via Pillow
    ex._thumbnail = thumb_bytes

    src_file = str(tmp_path / "with_thumbnail.jpg")
    out_file = str(tmp_path / "with_thumbnail_updated.jpg")
    main_im.save(src_file, format="JPEG", quality=90, exif=ex)

    # Read original scan data using top-level parser
    orig_scan = parse_jpeg_metadata_and_scan(src_file)["scan_data"]

    params = JobParameters(
        source_path=src_file,
        output_path=out_file,
        output_format="JPEG",
        dimension_mode=DimensionMode.METADATA_ONLY,
        dpi=500
    )
    res = execute_pipeline(params)
    assert res.success is True

    updated_scan = parse_jpeg_metadata_and_scan(out_file)["scan_data"]
    # If the parser had been fooled by the thumbnail's SOS, updated_scan would be corrupt or truncated!
    assert orig_scan == updated_scan, "Main image scan data was corrupted due to embedded thumbnail SOS!"

    # Verify decoded pixels
    with Image.open(src_file) as im1, Image.open(out_file) as im2:
        assert np.array_equal(np.array(im1), np.array(im2)), "Decoded pixels differ after update with thumbnail!"
        assert im2.info.get("dpi") == (500, 500)


def test_jpeg_reject_malformed_input(tmp_path):
    """
    Verifies that malformed or truncated JPEG files are safely rejected
    without writing corrupted files or silently re-encoding.
    """
    trunc_file = str(tmp_path / "trunc.jpg")
    out_file = str(tmp_path / "out_trunc.jpg")
    with open(trunc_file, "wb") as f:
        f.write(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x01,\x01,")  # truncated mid-header

    params = JobParameters(
        source_path=trunc_file,
        output_path=out_file,
        output_format="JPEG",
        dimension_mode=DimensionMode.METADATA_ONLY,
        dpi=400
    )
    res = execute_pipeline(params)
    assert res.success is False
    assert not os.path.exists(out_file)


