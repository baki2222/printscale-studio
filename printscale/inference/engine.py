"""
PrintScale Studio - ONNX Runtime Inference Engine
Provides unified hardware-accelerated (DirectML GPU) and CPU inference with
official DirectML options, concurrency protection, automatic verification,
safe fallback, and honest device reporting.
"""

import os
import threading
import subprocess
from typing import Optional
import numpy as np
import onnxruntime as ort

from printscale.inference.models import verify_model_integrity


_DETECTED_GPU_NAME: Optional[str] = None


def get_gpu_adapter_name() -> str:
    """
    Lists the Windows display adapter names for labelling (e.g. NVIDIA GeForce RTX 3090).
    DirectML runs on adapter 0 in DXGI order, which WMI does not report, so on a
    multi-adapter system every adapter name is listed instead of guessing which one ran.
    """
    global _DETECTED_GPU_NAME
    if _DETECTED_GPU_NAME is not None:
        return _DETECTED_GPU_NAME

    gpu_name = "DirectX 12 GPU"
    try:
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        powershell = os.path.join(system_root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
        if not os.path.isfile(powershell):
            powershell = "powershell"
        cmd = [powershell, "-NoProfile", "-NonInteractive", "-Command",
               "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5, creationflags=creationflags)
        if res.returncode == 0 and res.stdout.strip():
            lines = [line.strip() for line in res.stdout.strip().splitlines() if line.strip()]
            if len(lines) == 1:
                gpu_name = lines[0]
            elif lines:
                gpu_name = "adapter 0 of: " + ", ".join(lines)
    except Exception:
        pass

    _DETECTED_GPU_NAME = gpu_name
    return _DETECTED_GPU_NAME


class InferenceEngine:
    def __init__(self, prefer_gpu: bool = True):
        self.prefer_gpu = prefer_gpu
        self._current_model_id: Optional[str] = None
        self._session: Optional[ort.InferenceSession] = None
        self._active_provider: str = "Uninitialized"
        self._device_description: str = "Not loaded (models load on first AI job)"
        self._gpu_verified: bool = False
        self._gpu_failure_reason: Optional[str] = None
        self._session_lock = threading.Lock()
        self._init_providers()

    def _init_providers(self):
        available = ort.get_available_providers()
        has_dml = "DmlExecutionProvider" in available
        
        if self.prefer_gpu and has_dml:
            self._target_providers = ["DmlExecutionProvider", "CPUExecutionProvider"]
        else:
            self._target_providers = ["CPUExecutionProvider"]

    @property
    def active_provider(self) -> str:
        return self._active_provider

    @property
    def device_description(self) -> str:
        return self._device_description

    @property
    def gpu_verified(self) -> bool:
        return self._gpu_verified

    @property
    def gpu_failure_reason(self) -> Optional[str]:
        return self._gpu_failure_reason

    def load_model(self, model_id: str) -> None:
        """
        Loads the requested model into an ONNX Runtime session, testing GPU execution first
        with official DirectML settings and falling back safely to CPU if DirectML fails.
        """
        with self._session_lock:
            if self._current_model_id == model_id and self._session is not None:
                return  # Already loaded
            self._load_model_locked(model_id, allow_gpu="DmlExecutionProvider" in self._target_providers)

    def fall_back_to_cpu(self, reason: str) -> None:
        """
        Reloads the current model on the CPU provider after a GPU runtime failure
        (for example a DirectML out-of-memory or device-removed error during Run).
        """
        with self._session_lock:
            if self._current_model_id is None:
                return
            self._gpu_failure_reason = reason
            self._load_model_locked(self._current_model_id, allow_gpu=False)

    def _load_model_locked(self, model_id: str, allow_gpu: bool) -> None:
        ok, model_path_or_err = verify_model_integrity(model_id)
        if not ok:
            raise RuntimeError(f"Cannot load model '{model_id}': {model_path_or_err}")

        model_path = model_path_or_err

        # Configure session options according to official DirectML guidance:
        # https://onnxruntime.ai/docs/execution-providers/DirectML-ExecutionProvider.html
        so = ort.SessionOptions()
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        # DirectML requirement: disable memory pattern
        so.enable_mem_pattern = False
        # DirectML requirement: sequential execution mode
        so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL

        cpu_threads = max(1, os.cpu_count() or 4)
        so.intra_op_num_threads = min(cpu_threads, 8)
        so.inter_op_num_threads = 2

        session = None
        active_prov = "CPU"
        device_desc = f"CPU ({so.intra_op_num_threads} threads)"
        prior_failure = None if allow_gpu else self._gpu_failure_reason
        self._gpu_failure_reason = prior_failure
        self._gpu_verified = False

        if allow_gpu:
            try:
                # Attempt DirectML session with explicit device 0
                dml_options = {"device_id": 0}
                test_sess = ort.InferenceSession(
                    model_path,
                    sess_options=so,
                    providers=[("DmlExecutionProvider", dml_options), "CPUExecutionProvider"]
                )
                # Verify small actual inference on device
                dummy_input = np.zeros((1, 3, 32, 32), dtype=np.float32)
                _ = test_sess.run(None, {"input": dummy_input})
                
                sess_providers = test_sess.get_providers()
                if "DmlExecutionProvider" in sess_providers:
                    session = test_sess
                    active_prov = "DirectML (GPU)"
                    gpu_hardware = get_gpu_adapter_name()
                    device_desc = f"DirectML ({gpu_hardware})"
                    self._gpu_verified = True
            except Exception as e:
                self._gpu_failure_reason = str(e)
                session = None

        if session is None:
            # Fall back to CPU
            # For pure CPU, mem_pattern can be enabled
            cpu_so = ort.SessionOptions()
            cpu_so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            cpu_so.intra_op_num_threads = min(cpu_threads, 8)
            cpu_so.inter_op_num_threads = 2

            cpu_sess = ort.InferenceSession(
                model_path,
                sess_options=cpu_so,
                providers=["CPUExecutionProvider"]
            )
            # Verify CPU inference
            dummy_input = np.zeros((1, 3, 32, 32), dtype=np.float32)
            _ = cpu_sess.run(None, {"input": dummy_input})
            session = cpu_sess
            active_prov = "CPU"
            if self._gpu_failure_reason:
                device_desc = f"CPU ({cpu_so.intra_op_num_threads} threads; GPU fallback after: {self._gpu_failure_reason[:80]})"
            elif "DmlExecutionProvider" in self._target_providers:
                device_desc = f"CPU ({cpu_so.intra_op_num_threads} threads)"
            else:
                device_desc = f"CPU ({cpu_so.intra_op_num_threads} threads, GPU disabled in settings)"
            self._gpu_verified = False

        self._session = session
        self._current_model_id = model_id
        self._active_provider = active_prov
        self._device_description = device_desc

    def run_patch(self, patch_chw: np.ndarray) -> np.ndarray:
        """
        Runs inference on a single normalized RGB patch of shape (1, 3, H, W) with values [0.0, 1.0].
        Thread-safe concurrency protection serializes Run calls to prevent DirectML device removal.
        """
        if self._session is None:
            raise RuntimeError("InferenceSession not initialized. Call load_model() first.")

        inputs = {"input": patch_chw}
        # DirectML requirement: DirectML sessions are not thread-safe for concurrent Run calls
        with self._session_lock:
            outputs = self._session.run(None, inputs)
            return outputs[0]
