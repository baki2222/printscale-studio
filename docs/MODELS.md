# AI models

PrintScale Studio's two AI modes run the Real-ESRGAN networks through ONNX Runtime. The models are bundled in the
installer and portable ZIP, so end users never download anything and the app works offline. Developers fetch
them once with a hash-verified script. Model files are never committed to Git.

| Mode | ONNX file | Network | Size | SHA-256 |
|---|---|---|---|---|
| AI Illustration | `RealESRGAN_x4plus_anime_6B.onnx` | RRDBNet, 6 blocks, ×4 | 17,939,979 bytes | `6b04d9c09399e24f2ad6171246f2c21da3571383561f46a4bb93b1f4c18af40f` |
| AI Photo | `RealESRGAN_x4plus.onnx` | RRDBNet, 23 blocks, ×4 | 67,051,654 bytes | `ec45cb356739c0086893db4e6fcfefb3dc0af087816a13175cae2386532db8ff` |

The machine-readable record is [`models/manifest.json`](../models/manifest.json). `tests/test_models_and_gpu.py`
checks that the app's model registry matches it.

## Downloading

```powershell
python scripts/fetch_models.py
```

- **Source:** the ONNX files from the [`models-v1`](https://github.com/baki2222/printscale-studio/releases/tag/models-v1) release of this repository. No account or token is needed.
- **Verification:** each file is written to a `.part` file first and checked against its pinned size and SHA-256. Only then is it renamed into `models\`. An interrupted or altered download never replaces a good file.
- **Existing files:** files that already match are kept.
- **Failures:** the script retries 3 times, then exits with code 1. To retry, run the same command again.
- **`--check`:** verifies the existing files without downloading.
- **`--dest <folder>`:** downloads to another folder. Set `PRINTSCALE_MODEL_DIR=<folder>` so the app finds them when run from source. The packaged app always uses its own bundled `_internal\models`.
- **`--checkpoints`:** also downloads the official PyTorch checkpoints, for re-conversion.

## Provenance and license

| ONNX file | Official checkpoint | Checkpoint SHA-256 |
|---|---|---|
| `RealESRGAN_x4plus_anime_6B.onnx` | [Real-ESRGAN v0.2.2.4 `RealESRGAN_x4plus_anime_6B.pth`](https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth) (17,938,799 bytes) | `f872d837d3c90ed2e05227bed711af5671a6fd1c9f7d7e91c911a61f155e99da` |
| `RealESRGAN_x4plus.onnx` | [Real-ESRGAN v0.1.0 `RealESRGAN_x4plus.pth`](https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth) (67,040,989 bytes) | `4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1` |

- **Authors and license:** the checkpoints are published by the Real-ESRGAN project (Xintao Wang et al.), whose repository is under the [BSD 3-Clause License](../LICENSES/Real-ESRGAN-BSD-3-Clause.txt). The ONNX files are redistributed under the same terms, with attribution.
- **Origin of the ONNX files:** they are conversions made by this project, not upstream files.
- **Not used in the app:** the PyTorch checkpoints themselves are pickle files that the app never loads. They are only conversion inputs.

## Re-creating the ONNX files

```powershell
pip install -r requirements-convert.txt -c constraints.txt   # adds torch 2.14.1 and onnx 1.23.2
python scripts/fetch_models.py --checkpoints
python scripts/convert_torch_to_onnx.py
```

The script:
- loads each state dict with `weights_only=True`;
- exports it with the TorchScript exporter (`dynamo=False`, opset 17, dynamic batch/height/width);
- runs `onnx.checker`;
- compares PyTorch with ONNX Runtime (CPU) on a random 48×48 input.

The export fails if the maximum absolute difference is 1e-4 or more. The original conversion, with Python 3.11, torch 2.14.1, onnx 1.23.2 and onnxruntime-directml 1.24.4, measured 3.5e-6 on a real 96×96 image patch, on both CPU and DirectML.

**What is and isn't guaranteed:**
- **Numerical parity:** checked, as above.
- **Identical bytes:** not guaranteed. Other torch/onnx versions can serialize the same weights differently. The published files are the reference, pinned by SHA-256. If you convert again and get a different hash, the parity check still tells you whether the network is equivalent.

## Hosting and size limits

- **Release assets:** the ONNX files are assets of the `models-v1` GitHub release. GitHub allows Release assets up to 2 GiB each.
- **Why not Git or Git LFS:** ordinary Git pushes reject files over 100 MiB and warn above 50 MiB. Model weights are binary payloads, so they stay out of history entirely.
- **Changing models:** a new model set gets a new release tag (`models-v2`, …) and a new manifest entry. It never replaces assets of an existing tag.
