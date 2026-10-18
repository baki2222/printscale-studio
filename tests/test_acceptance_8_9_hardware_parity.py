"""
Acceptance Checks 8 & 9: Hardware Execution Providers, CPU Verification, and Model Reference Parity.
"""

import numpy as np
import onnxruntime as ort

from printscale.inference.engine import InferenceEngine
from printscale.inference.models import verify_model_integrity


def test_acceptance_8_cpu_only_inference():
    """
    Check 8: CPU-only inference works reliably and independently of GPU presence.
    """
    engine = InferenceEngine(prefer_gpu=False)
    assert "CPUExecutionProvider" in engine._target_providers

    # Load illustration model on CPU
    engine.load_model("illustration_anime_6b")
    assert "CPU" in engine.active_provider
    print(f"\n[Hardware QA] Verified CPU Provider: {engine.device_description}")

    # Run real patch inference on CPU
    dummy_input = np.random.rand(1, 3, 32, 32).astype(np.float32)
    output = engine.run_patch(dummy_input)
    assert output.shape == (1, 3, 128, 128)
    assert not np.isnan(output).any()


def test_acceptance_8_gpu_hardware_record():
    """
    Check 8: Records active GPU hardware / DirectML provider.
    """
    engine = InferenceEngine(prefer_gpu=True)
    engine.load_model("illustration_anime_6b")
    print(f"\n[Hardware QA] Active Engine: {engine.active_provider}")
    print(f"[Hardware QA] Hardware Device: {engine.device_description}")
    assert engine.active_provider in ("DirectML (GPU)", "CPU")


def test_acceptance_9_model_checksum_and_parity():
    """
    Check 9: Model integrity check against pinned cryptographic SHA-256 hashes.
    """
    # 1. Illustration Anime 6B
    ok_anime, path_anime = verify_model_integrity("illustration_anime_6b")
    assert ok_anime is True, f"Anime model integrity failed: {path_anime}"

    # 2. Photo x4plus
    ok_photo, path_photo = verify_model_integrity("photo_x4plus")
    assert ok_photo is True, f"Photo model integrity failed: {path_photo}"

    # Verify session inference consistency between two identical runs
    sess = ort.InferenceSession(path_anime, providers=["CPUExecutionProvider"])
    inp = np.ones((1, 3, 16, 16), dtype=np.float32) * 0.5
    out1 = sess.run(None, {"input": inp})[0]
    out2 = sess.run(None, {"input": inp})[0]
    assert np.array_equal(out1, out2), "Model output is non-deterministic!"
