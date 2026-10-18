"""
Model manifest consistency, and inference on a real DirectML GPU.
The GPU test is marked `gpu`: it needs a DirectX 12 adapter and is skipped (with the reason) on machines
without one, such as GitHub-hosted runners. CPU inference is covered by the other test modules.
"""
import json
import os

import numpy as np
import pytest

from printscale.inference.engine import InferenceEngine
from printscale.inference.models import MODEL_REGISTRY

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_registry_matches_model_manifest():
    manifest = json.load(open(os.path.join(ROOT, "models", "manifest.json"), encoding="utf-8"))
    by_file = {m["file"]: m for m in manifest["models"]}
    assert set(by_file) == {i.filename for i in MODEL_REGISTRY.values()}
    for info in MODEL_REGISTRY.values():
        m = by_file[info.filename]
        assert m["sha256"] == info.sha256 and m["bytes"] == info.size_bytes and m["id"] == info.model_id
        assert m["url"].startswith("https://") and m["checkpoint"]["url"] == info.source_url


@pytest.mark.gpu
def test_directml_gpu_inference():
    engine = InferenceEngine(prefer_gpu=True)
    engine.load_model("illustration_anime_6b")
    if not engine.gpu_verified:
        pytest.skip(f"No usable DirectML GPU: {engine.gpu_failure_reason or engine.device_description}")
    out = engine.run_patch(np.random.rand(1, 3, 32, 32).astype(np.float32))
    assert out.shape == (1, 3, 128, 128) and np.isfinite(out).all()
