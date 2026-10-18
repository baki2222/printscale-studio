"""
PrintScale Studio - Batch Orchestrator and Job Management
Manages multi-image queue, frozen job parameters, safe filename collisions,
thread execution, per-file error isolation, and graceful cancellation.
"""

import os
import uuid
import threading
from enum import Enum
from dataclasses import dataclass
from typing import List, Optional, Callable

from printscale.core.pipeline import JobParameters, JobExecutionResult, execute_pipeline
from printscale.inference.engine import InferenceEngine


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


def generate_collision_safe_filename(
    base_dir: str,
    stem: str,
    width: int,
    height: int,
    dpi: int,
    ext: str
) -> str:
    """
    Constructs informative, collision-safe destination filenames such as:
    design_4200x4800_300dpi.png
    design_4200x4800_300dpi_1.png
    """
    clean_ext = ext.lstrip(".").lower()
    base_name = f"{stem}_{width}x{height}_{dpi}dpi.{clean_ext}"
    candidate = os.path.join(base_dir, base_name)
    
    if not os.path.exists(candidate):
        return candidate

    counter = 1
    while True:
        candidate = os.path.join(base_dir, f"{stem}_{width}x{height}_{dpi}dpi_{counter}.{clean_ext}")
        if not os.path.exists(candidate):
            return candidate
        counter += 1


@dataclass
class BatchJob:
    job_id: str
    source_path: str
    params: JobParameters  # Frozen snapshot of parameters at queue time
    status: JobStatus = JobStatus.PENDING
    progress: int = 0
    stage_message: str = "In queue"
    result: Optional[JobExecutionResult] = None
    error_message: Optional[str] = None


class BatchRunner:
    def __init__(self, engine: Optional[InferenceEngine] = None):
        self._engine = engine or InferenceEngine(prefer_gpu=True)
        self._jobs: List[BatchJob] = []
        self._lock = threading.Lock()
        self._is_running = False
        self._cancel_requested = False
        self._worker_thread: Optional[threading.Thread] = None

        # Callbacks
        self.on_job_started: Optional[Callable[[BatchJob], None]] = None
        self.on_job_progress: Optional[Callable[[BatchJob, int, str], None]] = None
        self.on_job_completed: Optional[Callable[[BatchJob], None]] = None
        self.on_job_failed: Optional[Callable[[BatchJob, str], None]] = None
        self.on_batch_finished: Optional[Callable[[], None]] = None

    @property
    def is_running(self) -> bool:
        return self._is_running

    def add_job(self, params: JobParameters) -> BatchJob:
        job = BatchJob(
            job_id=str(uuid.uuid4())[:8],
            source_path=params.source_path,
            params=params
        )
        with self._lock:
            self._jobs.append(job)
        return job

    def remove_job(self, job_id: str) -> bool:
        with self._lock:
            for i, job in enumerate(self._jobs):
                if job.job_id == job_id and job.status != JobStatus.RUNNING:
                    self._jobs.pop(i)
                    return True
        return False

    def clear_completed(self):
        with self._lock:
            self._jobs = [j for j in self._jobs if j.status in (JobStatus.PENDING, JobStatus.RUNNING)]

    def get_jobs(self) -> List[BatchJob]:
        with self._lock:
            return list(self._jobs)

    def cancel_all(self):
        self._cancel_requested = True

    def start_processing(self) -> bool:
        if self._is_running:
            return False

        self._cancel_requested = False
        self._is_running = True
        self._worker_thread = threading.Thread(target=self._run_queue, daemon=True)
        self._worker_thread.start()
        return True

    def _run_queue(self):
        try:
            for job in self._jobs:
                if self._cancel_requested:
                    job.status = JobStatus.CANCELLED
                    job.stage_message = "Cancelled"
                    continue

                if job.status != JobStatus.PENDING:
                    continue

                job.status = JobStatus.RUNNING
                job.stage_message = "Starting..."
                if self.on_job_started:
                    self.on_job_started(job)

                def job_progress_cb(current: int, total: int, msg: str):
                    pct = int(round((current / max(1, total)) * 100))
                    job.progress = pct
                    job.stage_message = msg
                    if self.on_job_progress:
                        self.on_job_progress(job, pct, msg)

                def is_cancelled():
                    return self._cancel_requested

                result = execute_pipeline(
                    params=job.params,
                    engine=self._engine,
                    progress_callback=job_progress_cb,
                    is_cancelled_callback=is_cancelled
                )

                job.result = result
                if result.success:
                    job.status = JobStatus.COMPLETED
                    job.progress = 100
                    job.stage_message = "Completed"
                    if self.on_job_completed:
                        self.on_job_completed(job)
                else:
                    if self._cancel_requested or result.error_message == "Cancelled by user":
                        job.status = JobStatus.CANCELLED
                        job.stage_message = "Cancelled"
                    else:
                        job.status = JobStatus.FAILED
                        job.error_message = result.error_message
                        job.stage_message = f"Failed: {result.error_message}"
                        if self.on_job_failed:
                            self.on_job_failed(job, result.error_message or "Unknown error")

        finally:
            self._is_running = False
            if self.on_batch_finished:
                self.on_batch_finished()
