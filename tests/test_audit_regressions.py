"""
Regression tests for defects confirmed during the v1.0.2 audit. Each test reproduces the
v1.0.1 failure mode and checks the saved file with independent inspection (raw bytes,
Pillow decoding, or arithmetic), not with the writer's own helpers.
"""

import io
import os
import struct
import zlib
import numpy as np
import pytest
from PIL import Image, ImageCms

from printscale.core.geometry import DimensionMode, CompositionMode
from printscale.core.pipeline import JobParameters, execute_pipeline, CANCELLED_MESSAGE
from printscale.core.enhancement import ProcessingMode
from printscale.core.metadata import lossless_update_jpeg_dpi, lossless_update_png_dpi
from printscale.inference.engine import InferenceEngine
from printscale.inference.tiling import run_tiled_inference


def run(src, out, **kw):
    params = dict(source_path=str(src), output_path=str(out), output_format="PNG",
                  dimension_mode=DimensionMode.PIXEL_DIMS, pixel_width=200, pixel_height=200, dpi=300)
    params.update(kw)
    return execute_pipeline(JobParameters(**params))


# --------------------------------------------------------------------------- alpha / halo
def test_fit_pad_png_keeps_semi_transparent_pixels_exact(tmp_path):
    """v1.0.1 pasted with mask=alpha onto a transparent canvas: (255,255,255,128) became (128,128,128,64),
    producing grey halos/double outlines around white lettering."""
    src = tmp_path / "white_half_alpha.png"
    Image.new("RGBA", (50, 100), (255, 255, 255, 128)).save(src)
    res = run(src, tmp_path / "out.png", pixel_width=200, pixel_height=200)  # 2x, padded left/right
    assert res.success, res.error_message
    arr = np.array(Image.open(res.output_path))
    content = arr[:, 50:150]
    assert np.all(content[..., 3] == 128), "alpha must not be squared by compositing"
    assert np.all(content[..., :3] == 255), "white must stay white (no grey halo)"
    assert np.all(arr[:, :50, 3] == 0) and np.all(arr[:, 150:, 3] == 0)


def test_antialiased_white_edge_has_no_dark_fringe_on_white(tmp_path):
    """White artwork with soft edges composited on white must stay white; any darkening is a halo."""
    yy, xx = np.mgrid[0:120, 0:90]
    alpha = np.clip(255 - np.abs(xx - 45) * 6, 0, 255).astype(np.uint8)
    arr = np.dstack([np.full((120, 90, 3), 255, np.uint8), alpha])
    arr[alpha == 0, :3] = 0  # black hidden RGB, as common in exported artwork
    src = tmp_path / "soft_white.png"
    Image.fromarray(arr, "RGBA").save(src)
    res = run(src, tmp_path / "out.png", pixel_width=480, pixel_height=480)
    assert res.success, res.error_message
    out = np.array(Image.open(res.output_path)).astype(float)
    on_white = out[..., :3] * out[..., 3:] / 255 + 255 * (1 - out[..., 3:] / 255)
    assert on_white.min() >= 254, f"dark fringe on white: min {on_white.min()}"


@pytest.mark.parametrize("composition", [CompositionMode.FIT_PAD, CompositionMode.CROP])
def test_jpeg_flattens_transparency_onto_chosen_background(tmp_path, composition):
    """Transparent areas must be composited over the JPEG background colour, including padded canvases."""
    arr = np.zeros((100, 80, 4), np.uint8)
    arr[30:70, 20:60] = (200, 30, 30, 255)
    arr[30:70, 60:70] = (200, 30, 30, 128)
    src = tmp_path / "t.png"
    Image.fromarray(arr, "RGBA").save(src)
    res = run(src, tmp_path / "out.jpg", output_format="JPEG", pixel_width=200, pixel_height=200,
              composition_mode=composition, jpeg_bg_color=(10, 200, 10))
    assert res.success, res.error_message
    out = np.array(Image.open(res.output_path)).astype(int)
    assert np.abs(out[3, 3] - (10, 200, 10)).max() <= 6, out[3, 3]  # transparent area -> background
    assert np.abs(out[100, 100] - (200, 30, 30)).max() <= 8, out[100, 100]


def test_opaque_source_without_padding_stays_rgb(tmp_path):
    src = tmp_path / "opaque.png"
    Image.new("RGB", (100, 100), (10, 20, 30)).save(src)
    res = run(src, tmp_path / "out.png", pixel_width=300, pixel_height=300)
    assert res.success
    with Image.open(res.output_path) as im:
        assert im.mode == "RGB"
    assert res.has_alpha is False


# --------------------------------------------------------------------------- input formats
def test_16bit_grayscale_png_is_scaled_not_clipped(tmp_path):
    """v1.0.1 converted 16-bit grey via Pillow's I->RGBA clip: almost everything became white."""
    ramp = np.tile(np.linspace(0, 65535, 64).astype("<u2"), (48, 1))
    src = tmp_path / "g16.png"
    Image.frombytes("I;16", (64, 48), ramp.tobytes()).save(src)
    res = run(src, tmp_path / "out.png", pixel_width=64, pixel_height=48)  # same size: pure conversion
    assert res.success, res.error_message
    out = np.array(Image.open(res.output_path).convert("L")).astype(int)
    expected = (ramp.astype(np.int64) * 255 + 32767) // 65535
    assert np.abs(out - expected).max() <= 2
    assert any("16-bit" in n for n in res.notes)


def _png_16bit_rgba(path, rgba16):
    h, w, _ = rgba16.shape
    raw = b"".join(b"\x00" + rgba16[y].astype(">u2").tobytes() for y in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 16, 6, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def test_16bit_rgba_reports_bit_depth_reduction(tmp_path):
    src = tmp_path / "rgba16.png"
    _png_16bit_rgba(src, np.full((20, 20, 4), 40000, dtype=np.uint16))
    res = run(src, tmp_path / "out.png", pixel_width=40, pixel_height=40)
    assert res.success
    assert any("8 bits" in n for n in res.notes), res.notes
    a = np.array(Image.open(res.output_path))
    assert abs(int(a[..., 3].min()) - 155) <= 1  # 40000/65535*255 = 155.6, not squared


def _matrix_icc(primaries, gamma=2.2, desc=b"Test AdobeRGB-like"):
    """Minimal ICC v2 RGB matrix/TRC display profile (independent of the code under test)."""
    def s15(v):
        return struct.pack(">i", int(round(v * 65536)))

    def xyz(x, y, z):
        return b"XYZ " + b"\0" * 4 + s15(x) + s15(y) + s15(z)

    curv = b"curv" + b"\0" * 4 + struct.pack(">I", 1) + struct.pack(">H", int(gamma * 256)) + b"\0\0"
    d = b"desc" + b"\0" * 4 + struct.pack(">I", len(desc) + 1) + desc + b"\0" + b"\0" * 8 + b"\0\0\0" + b"\0" * 67
    tags = [(b"desc", d), (b"wtpt", xyz(0.9642, 1.0, 0.8249)), (b"rXYZ", xyz(*primaries[0])),
            (b"gXYZ", xyz(*primaries[1])), (b"bXYZ", xyz(*primaries[2])),
            (b"rTRC", curv), (b"gTRC", curv), (b"bTRC", curv), (b"cprt", b"text" + b"\0" * 4 + b"none\0")]
    offset = 128 + 4 + 12 * len(tags)
    table, data = b"", b""
    for sig, body in tags:
        while (offset + len(data)) % 4:
            data += b"\0"
        table += sig + struct.pack(">II", offset + len(data), len(body))
        data += body
    body = struct.pack(">I", len(tags)) + table + data
    size = 128 + len(body)
    header = (struct.pack(">I", size) + b"lcms" + struct.pack(">I", 0x02100000) + b"mntrRGB XYZ " + b"\0" * 12
              + b"acsp" + b"MSFT" + b"\0" * 4 + b"\0" * 8 + b"\0" * 8 + struct.pack(">I", 0)
              + s15(0.9642) + s15(1.0) + s15(0.8249) + b"\0" * 4 + b"\0" * 16 + b"\0" * 28)
    assert len(header) == 128
    return header + body


ADOBE_D50 = [(0.6097, 0.3111, 0.0195), (0.2053, 0.6257, 0.0609), (0.1492, 0.0632, 0.7446)]


def test_non_srgb_rgba_profile_is_converted_and_output_tagged_srgb(tmp_path):
    icc = _matrix_icc(ADOBE_D50)
    ImageCms.getOpenProfile(io.BytesIO(icc))  # profile must be valid for LittleCMS
    src = tmp_path / "adobe.png"
    Image.new("RGBA", (40, 40), (30, 160, 60, 200)).save(src, icc_profile=icc)
    res = run(src, tmp_path / "out.png", pixel_width=40, pixel_height=40)
    assert res.success, res.error_message
    with Image.open(res.output_path) as im:
        out_icc = im.info.get("icc_profile")
        px = im.getpixel((20, 20))
    name = ImageCms.getProfileName(ImageCms.getOpenProfile(io.BytesIO(out_icc))).lower()
    assert "srgb" in name
    expected = ImageCms.profileToProfile(Image.new("RGB", (1, 1), (30, 160, 60)), ImageCms.getOpenProfile(io.BytesIO(icc)),
                                         ImageCms.createProfile("sRGB"), outputMode="RGB",
                                         renderingIntent=ImageCms.Intent.PERCEPTUAL).getpixel((0, 0))
    assert max(abs(a - b) for a, b in zip(px[:3], expected)) <= 1
    assert px[:3] != (30, 160, 60), "colours must actually be converted, not relabelled"
    assert px[3] == 200


def test_cmyk_jpeg_with_profile_is_converted_through_profile(tmp_path):
    rswop = r"C:\Windows\System32\spool\drivers\color\RSWOP.icm"
    if not os.path.exists(rswop):
        pytest.skip("Windows RSWOP CMYK profile not available on this machine")
    icc = open(rswop, "rb").read()
    src = tmp_path / "cmyk.jpg"
    Image.new("CMYK", (32, 32), (0, 255, 255, 0)).save(src, icc_profile=icc, quality=100)
    res = run(src, tmp_path / "out.png", pixel_width=32, pixel_height=32)
    assert res.success, res.error_message
    assert any("Converted from" in n for n in res.notes), res.notes
    with Image.open(res.output_path) as im:
        assert im.mode == "RGB"
        r, g, b = im.getpixel((16, 16))
    assert r > 180 and g < 90 and b < 90  # a press red, not naive (255,0,0) relabelled


# --------------------------------------------------------------------------- file safety
def test_never_overwrites_source(tmp_path):
    src = tmp_path / "keep.png"
    Image.new("RGB", (20, 20), (1, 2, 3)).save(src)
    before = src.read_bytes()
    res = run(src, src, pixel_width=40, pixel_height=40)
    assert not res.success and "source" in res.error_message.lower()
    assert src.read_bytes() == before


def test_existing_destination_not_silently_replaced(tmp_path):
    src = tmp_path / "a.png"
    Image.new("RGB", (20, 20), (1, 2, 3)).save(src)
    dest = tmp_path / "Out.PNG"
    dest.write_bytes(b"user file")
    # Windows names are case-insensitive: out.png is the same file as Out.PNG
    res = run(src, tmp_path / "out.png", pixel_width=40, pixel_height=40, overwrite_existing=False)
    assert res.success
    assert dest.read_bytes() == b"user file"
    assert os.path.basename(res.output_path) == "out_1.png"
    assert any("instead of overwriting" in n for n in res.notes)


def test_cancel_after_processing_writes_nothing(tmp_path):
    src = tmp_path / "a.png"
    Image.new("RGB", (64, 64), (1, 2, 3)).save(src)
    out = tmp_path / "out.png"
    calls = {"n": 0}

    def cancel_late():
        calls["n"] += 1
        return calls["n"] > 3  # cancel after processing has started

    res = execute_pipeline(JobParameters(source_path=str(src), output_path=str(out), output_format="PNG",
                                         dimension_mode=DimensionMode.PIXEL_DIMS, pixel_width=128, pixel_height=128),
                           is_cancelled_callback=cancel_late)
    assert res.error_message == CANCELLED_MESSAGE
    assert os.listdir(tmp_path) == ["a.png"], "no output or temporary file may remain"


def test_oversized_canvas_refused_before_allocation(tmp_path):
    src = tmp_path / "a.png"
    Image.new("RGB", (20, 20)).save(src)
    res = run(src, tmp_path / "out.png", dimension_mode=DimensionMode.PRINT_SIZE,
              print_width=500.0, print_height=500.0, dpi=1200)
    assert not res.success and "per-axis limit" in res.error_message
    assert os.listdir(tmp_path) == ["a.png"]


def test_upload_profile_checked_on_saved_file(tmp_path):
    src = tmp_path / "noise.png"
    Image.fromarray(np.random.default_rng(0).integers(0, 256, (300, 300, 3), dtype=np.uint8)).save(src)
    res = run(src, tmp_path / "out.png", pixel_width=1200, pixel_height=1200, upload_max_bytes=100_000)
    assert res.success
    assert res.upload_compliant is False and "bytes" in res.upload_message
    assert os.path.getsize(res.output_path) == res.file_size_bytes > 100_000  # output was not altered to fit


def test_method_label_is_honest_when_ai_cannot_apply(tmp_path):
    src = tmp_path / "big.png"
    Image.new("RGB", (400, 400)).save(src)
    res = run(src, tmp_path / "out.png", pixel_width=200, pixel_height=200, processing_mode=ProcessingMode.AI_PHOTO)
    assert res.success
    assert "AI model not applied" in res.method_used and "Real-ESRGAN" not in res.method_used


# --------------------------------------------------------------------------- metadata integrity
def _phys_chunks(data):
    idx, out, first_idat = 8, [], None
    while idx < len(data):
        n = struct.unpack(">I", data[idx:idx + 4])[0]
        t = data[idx + 4:idx + 8]
        if t == b"pHYs":
            out.append((idx, struct.unpack(">IIB", data[idx + 8:idx + 17])))
        if t == b"IDAT" and first_idat is None:
            first_idat = idx
        idx += 12 + n
    return out, first_idat


def test_png_exif_resolution_kept_consistent(tmp_path):
    src = tmp_path / "with_exif.png"
    ex = Image.Exif()
    ex[0x011A] = 72.0
    ex[0x011B] = 72.0
    ex[0x0128] = 2
    ex[0x010F] = "CameraMaker"
    Image.new("RGB", (16, 16)).save(src, exif=ex, dpi=(72, 72))
    out = tmp_path / "out.png"
    lossless_update_png_dpi(str(src), str(out), 500)
    data = out.read_bytes()
    phys, first_idat = _phys_chunks(data)
    assert len(phys) == 1 and phys[0][0] < first_idat and phys[0][1] == (19685, 19685, 1)
    with Image.open(out) as im:
        e = im.getexif()
        assert float(e[0x011A]) == 500 and float(e[0x011B]) == 500 and e[0x010F] == "CameraMaker"


def _jpeg_segments(data):
    idx, segs = 2, []
    while True:
        assert data[idx] == 0xFF
        m = data[idx + 1]
        if m == 0xDA:
            return segs, idx
        n = struct.unpack(">H", data[idx + 2:idx + 4])[0]
        segs.append((m, data[idx:idx + 2 + n]))
        idx += 2 + n


def _exif_with_inline_short_resolution(endian):
    """IFD0 with a malformed XResolution stored as SHORT inline (v1.0.1 wrote 8 bytes at that 'offset')."""
    e = "<" if endian == b"II" else ">"
    entries = [(0x010F, 2, 4, b"Cam\0"), (0x011A, 3, 1, struct.pack(f"{e}Hxx", 300)), (0x0112, 3, 1, struct.pack(f"{e}Hxx", 6))]
    ifd = struct.pack(f"{e}H", len(entries))
    for tag, typ, cnt, raw in entries:
        ifd += struct.pack(f"{e}HHI", tag, typ, cnt) + raw
    ifd += struct.pack(f"{e}I", 0)
    tiff = endian + struct.pack(f"{e}HI", 42, 8) + ifd
    return b"\xff\xe1" + struct.pack(">H", len(tiff) + 8) + b"Exif\0\0" + tiff


@pytest.mark.parametrize("endian", [b"II", b"MM"])
def test_jpeg_malformed_resolution_entry_rebuilt_safely(tmp_path, endian):
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), (200, 10, 10)).save(buf, format="JPEG", quality=90)
    jpg = buf.getvalue()
    exif_seg = _exif_with_inline_short_resolution(endian)
    data = jpg[:2] + exif_seg + jpg[2:]
    src = tmp_path / "in.jpg"
    src.write_bytes(data)
    out = tmp_path / "out.jpg"
    lossless_update_jpeg_dpi(str(src), str(out), 400)
    od = out.read_bytes()
    (_, sos_in), (_, sos_out) = _jpeg_segments(data), _jpeg_segments(od)
    assert data[sos_in:] == od[sos_out:], "scan data must be byte-identical"
    with Image.open(out) as im:
        e = im.getexif()
        assert float(e[0x011A]) == 400 and float(e[0x011B]) == 400 and e[0x0128] == 2
        assert e[0x0112] == 6 and e[0x010F] == "Cam"
        assert im.info["jfif_density"] == (400, 400)


def test_jpeg_photoshop_resolution_updated(tmp_path):
    buf = io.BytesIO()
    Image.new("RGB", (16, 16)).save(buf, format="JPEG", dpi=(72, 72))
    jpg = buf.getvalue()
    res_info = struct.pack(">IHHIHH", 72 << 16, 1, 1, 72 << 16, 1, 1)
    block = b"8BIM" + struct.pack(">H", 0x03ED) + b"\0\0" + struct.pack(">I", len(res_info)) + res_info
    payload = b"Photoshop 3.0\0" + block
    app13 = b"\xff\xed" + struct.pack(">H", len(payload) + 2) + payload
    src = tmp_path / "ps.jpg"
    src.write_bytes(jpg[:20] + app13 + jpg[20:])
    out = tmp_path / "out.jpg"
    lossless_update_jpeg_dpi(str(src), str(out), 600)
    segs, _ = _jpeg_segments(out.read_bytes())
    ps = [s for m, s in segs if m == 0xED][0]
    i = ps.index(b"8BIM")
    h_res, h_unit, _, v_res, v_unit, _ = struct.unpack(">IHHIHH", ps[i + 12:i + 28])
    assert (h_res >> 16, v_res >> 16, h_unit, v_unit) == (600, 600, 1, 1)


# --------------------------------------------------------------------------- tiling
def test_tiled_inference_matches_whole_frame_on_high_contrast_texture():
    """v1.0.1 tiles had no context margin: up to 185 levels deviation from whole-frame
    inference at tile borders on textured artwork. Context-padded tiles must stay close."""
    engine = InferenceEngine(prefer_gpu=False)
    engine.load_model("illustration_anime_6b")
    rng = np.random.default_rng(3)
    img = (rng.random((40, 40)) > 0.5).astype(np.uint8) * 255
    img = np.kron(img, np.ones((5, 5), np.uint8))[:200, :200]  # hard-edged texture
    rgb = np.dstack([img, 255 - img, img // 2])
    whole = np.clip(np.rint(engine.run_patch(rgb.transpose(2, 0, 1)[None].astype(np.float32) / 255)[0] * 255), 0, 255)
    whole = whole.astype(np.uint8).transpose(1, 2, 0)
    tiled = run_tiled_inference(rgb, engine, tile_size=96, overlap=16, scale=4)
    diff = np.abs(tiled.astype(int) - whole.astype(int))
    # Measured: v1.0.1 tiler max 129 levels (37% of values off by >4); 32 px context: max 2.
    # Tolerance 4 allows for floating-point differences between providers.
    assert diff.max() <= 4, f"tile seam deviation {diff.max()}"


# --------------------------------------------------------------------------- resource / robustness
def test_job_refused_when_memory_insufficient(tmp_path, monkeypatch):
    import printscale.core.pipeline as pipeline_mod
    monkeypatch.setattr(pipeline_mod, "get_available_memory_bytes", lambda: 512 * 2**20)
    src = tmp_path / "a.png"
    Image.new("RGB", (100, 100)).save(src)
    res = run(src, tmp_path / "out.png", pixel_width=8400, pixel_height=9600)
    assert not res.success and "Not enough free memory" in res.error_message
    assert os.listdir(tmp_path) == ["a.png"]


def test_decompression_bomb_rejected_without_disabling_protection(tmp_path):
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    bomb = tmp_path / "bomb.png"  # header claims 20000 x 20000 (400 MP), above Pillow's hard limit
    bomb.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 20000, 20000, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(b"\0" * 100)) + chunk(b"IEND", b""))
    res = run(bomb, tmp_path / "out.png")
    assert not res.success and "safety limit" in res.error_message
    assert Image.MAX_IMAGE_PIXELS is not None


def test_truncated_png_fails_cleanly(tmp_path):
    good = tmp_path / "good.png"
    Image.fromarray(np.random.default_rng(1).integers(0, 255, (200, 200, 3), dtype=np.uint8)).save(good)
    bad = tmp_path / "bad.png"
    bad.write_bytes(good.read_bytes()[:3000])
    res = run(bad, tmp_path / "out.png")
    assert not res.success and res.error_message
    assert sorted(os.listdir(tmp_path)) == ["bad.png", "good.png"]


@pytest.mark.parametrize("damage", ["missing", "corrupt"])
def test_ai_mode_with_missing_or_corrupt_model_fails_clearly(tmp_path, monkeypatch, damage):
    import printscale.inference.models as models_mod
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    if damage == "corrupt":
        (model_dir / models_mod.MODEL_REGISTRY["photo_x4plus"].filename).write_bytes(b"not a model")
    monkeypatch.setattr(models_mod, "get_candidate_model_dirs", lambda: [str(model_dir)])
    src = tmp_path / "a.png"
    Image.new("RGB", (32, 32)).save(src)
    res = run(src, tmp_path / "out.png", pixel_width=128, pixel_height=128, processing_mode=ProcessingMode.AI_PHOTO)
    assert not res.success
    assert ("not found" in res.error_message) if damage == "missing" else ("SHA-256 mismatch" in res.error_message)
    assert not os.path.exists(tmp_path / "out.png")
