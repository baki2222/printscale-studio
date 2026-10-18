"""
PrintScale Studio - Model Conversion Tool
Converts the official Real-ESRGAN PyTorch checkpoints to ONNX (dynamic spatial axes) and checks
numerical parity against PyTorch. Development-time only; see docs/MODELS.md.

    pip install -r requirements-convert.txt
    python scripts/fetch_models.py --checkpoints     # official .pth files, SHA-256 verified
    python scripts/convert_torch_to_onnx.py

The RRDBNet / RRDB / ResidualDenseBlock definitions below are adapted from BasicSR
(https://github.com/XPixelGroup/BasicSR, basicsr/archs/rrdbnet_arch.py), Copyright (c) Xintao Wang,
licensed under the Apache License 2.0 (LICENSES/Apache-2.0.txt). Layer names match the checkpoints.
"""

import os
import hashlib
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import onnx
import onnxruntime as ort


class ResidualDenseBlock_5C(nn.Module):
    def __init__(self, nf=64, gc=32, bias=True):
        super().__init__()
        self.conv1 = nn.Conv2d(nf, gc, 3, 1, 1, bias=bias)
        self.conv2 = nn.Conv2d(nf + gc, gc, 3, 1, 1, bias=bias)
        self.conv3 = nn.Conv2d(nf + 2 * gc, gc, 3, 1, 1, bias=bias)
        self.conv4 = nn.Conv2d(nf + 3 * gc, gc, 3, 1, 1, bias=bias)
        self.conv5 = nn.Conv2d(nf + 4 * gc, nf, 3, 1, 1, bias=bias)
        self.lrelu = nn.LeakyReLU(negative_slope=0.2, inplace=True)

    def forward(self, x):
        x1 = self.lrelu(self.conv1(x))
        x2 = self.lrelu(self.conv2(torch.cat((x, x1), 1)))
        x3 = self.lrelu(self.conv3(torch.cat((x, x1, x2), 1)))
        x4 = self.lrelu(self.conv4(torch.cat((x, x1, x2, x3), 1)))
        x5 = self.conv5(torch.cat((x, x1, x2, x3, x4), 1))
        return x5 * 0.2 + x


class RRDB(nn.Module):
    def __init__(self, nf, gc=32):
        super().__init__()
        self.rdb1 = ResidualDenseBlock_5C(nf, gc)
        self.rdb2 = ResidualDenseBlock_5C(nf, gc)
        self.rdb3 = ResidualDenseBlock_5C(nf, gc)

    def forward(self, x):
        out = self.rdb1(x)
        out = self.rdb2(out)
        out = self.rdb3(out)
        return out * 0.2 + x


class RRDBNet(nn.Module):
    def __init__(self, in_nc=3, out_nc=3, nf=64, nb=23, gc=32):
        super().__init__()
        self.conv_first = nn.Conv2d(in_nc, nf, 3, 1, 1, bias=True)
        self.body = nn.Sequential(*[RRDB(nf, gc) for _ in range(nb)])
        self.conv_body = nn.Conv2d(nf, nf, 3, 1, 1, bias=True)
        self.conv_up1 = nn.Conv2d(nf, nf, 3, 1, 1, bias=True)
        self.conv_up2 = nn.Conv2d(nf, nf, 3, 1, 1, bias=True)
        self.conv_hr = nn.Conv2d(nf, nf, 3, 1, 1, bias=True)
        self.conv_last = nn.Conv2d(nf, out_nc, 3, 1, 1, bias=True)
        self.lrelu = nn.LeakyReLU(negative_slope=0.2, inplace=True)

    def forward(self, x):
        feat = self.conv_first(x)
        body_feat = self.conv_body(self.body(feat))
        feat = feat + body_feat
        feat = self.lrelu(self.conv_up1(F.interpolate(feat, scale_factor=2.0, mode='nearest')))
        feat = self.lrelu(self.conv_up2(F.interpolate(feat, scale_factor=2.0, mode='nearest')))
        out = self.conv_last(self.lrelu(self.conv_hr(feat)))
        return out


def compute_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(8192 * 1024):
            h.update(chunk)
    return h.hexdigest().lower()


def convert_model(pth_path: str, onnx_path: str, nb: int, opset: int = 17):
    print("\n==========================================")
    print(f"Converting {pth_path} -> {onnx_path} (blocks: {nb}, opset: {opset})")
    print(f"Input pth SHA-256: {compute_sha256(pth_path)}")
    
    model = RRDBNet(nb=nb)
    # weights_only=True: the checkpoint is a plain state dict; never unpickle arbitrary objects
    checkpoint = torch.load(pth_path, map_location='cpu', weights_only=True)
    if 'params_ema' in checkpoint:
        state_dict = checkpoint['params_ema']
    elif 'params' in checkpoint:
        state_dict = checkpoint['params']
    else:
        state_dict = checkpoint
    model.load_state_dict(state_dict, strict=True)
    model.eval()

    # Create dummy input with representative patch size
    dummy_input = torch.randn(1, 3, 64, 64, dtype=torch.float32)

    # Export to ONNX with dynamic spatial dimensions using classic TorchScript exporter
    print("Exporting to ONNX...")
    torch.onnx.export(
        model,
        dummy_input,
        onnx_path,
        export_params=True,
        opset_version=17,
        do_constant_folding=True,
        input_names=['input'],
        output_names=['output'],
        dynamic_axes={
            'input': {0: 'batch_size', 2: 'height', 3: 'width'},
            'output': {0: 'batch_size', 2: 'height', 3: 'width'}
        },
        dynamo=False
    )

    # Check ONNX model validity
    onnx_model = onnx.load(onnx_path)
    onnx.checker.check_model(onnx_model)
    onnx_hash = compute_sha256(onnx_path)
    print(f"Export successful. ONNX SHA-256: {onnx_hash}")
    print(f"ONNX file size: {os.path.getsize(onnx_path):,} bytes")

    # Reference inference verification
    print("Verifying numerical parity against PyTorch reference...")
    test_input = torch.rand(1, 3, 48, 48, dtype=torch.float32)
    with torch.no_grad():
        torch_out = model(test_input).numpy()

    sess = ort.InferenceSession(onnx_path, providers=['CPUExecutionProvider'])
    ort_out = sess.run(None, {'input': test_input.numpy()})[0]

    max_abs_diff = np.max(np.abs(torch_out - ort_out))
    mean_abs_diff = np.mean(np.abs(torch_out - ort_out))
    mse = np.mean((torch_out - ort_out) ** 2)
    psnr = 20 * np.log10(1.0 / np.sqrt(mse)) if mse > 0 else float('inf')

    print(f"Max absolute difference:  {max_abs_diff:.6e}")
    print(f"Mean absolute difference: {mean_abs_diff:.6e}")
    print(f"Reference parity PSNR:    {psnr:.2f} dB")

    # Check parity tolerance (FP32 differences should be under 1e-4)
    assert max_abs_diff < 1e-4, f"Parity check failed: max_diff={max_abs_diff}"
    print("Numerical parity check PASSED!")
    return onnx_hash


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.makedirs('models', exist_ok=True)
    anime_hash = convert_model('models/RealESRGAN_x4plus_anime_6B.pth', 'models/RealESRGAN_x4plus_anime_6B.onnx', nb=6)
    photo_hash = convert_model('models/RealESRGAN_x4plus.pth', 'models/RealESRGAN_x4plus.onnx', nb=23)
    print("\nSummary of converted ONNX models:")
    print(f"Illustration Model (Anime 6B): {anime_hash}")
    print(f"Photo Model (x4plus 23B):      {photo_hash}")
