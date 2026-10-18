"""
Acceptance Checks 10 & 11: Batch Queue Resilience, Per-File Error Isolation, and Cancellation Cleanup.
"""

import os
import time
from PIL import Image

from printscale.core.geometry import DimensionMode
from printscale.core.pipeline import JobParameters, execute_pipeline
from printscale.core.batch import BatchRunner, JobStatus


def test_acceptance_10_corrupt_file_batch_isolation(tmp_path):
    """
    Check 10: A batch with one corrupt file still completes the other valid jobs.
    """
    valid_file1 = str(tmp_path / "valid1.png")
    corrupt_file = str(tmp_path / "corrupt.png")
    valid_file2 = str(tmp_path / "valid2.png")

    out1 = str(tmp_path / "out1.png")
    out_corrupt = str(tmp_path / "out_corrupt.png")
    out2 = str(tmp_path / "out2.png")

    # Create valid image 1
    im1 = Image.new("RGB", (50, 50), (255, 0, 0))
    im1.save(valid_file1, format="PNG")

    # Create corrupt file (garbage bytes)
    with open(corrupt_file, "wb") as f:
        f.write(b"NOT_A_VALID_IMAGE_HEADER_GARBAGE_BYTES_123456789")

    # Create valid image 2
    im2 = Image.new("RGB", (60, 60), (0, 255, 0))
    im2.save(valid_file2, format="PNG")

    # Setup BatchRunner
    runner = BatchRunner()

    job1 = runner.add_job(JobParameters(
        source_path=valid_file1,
        output_path=out1,
        output_format="PNG",
        dimension_mode=DimensionMode.PIXEL_DIMS,
        pixel_width=100,
        pixel_height=100
    ))

    job_bad = runner.add_job(JobParameters(
        source_path=corrupt_file,
        output_path=out_corrupt,
        output_format="PNG",
        dimension_mode=DimensionMode.PIXEL_DIMS,
        pixel_width=100,
        pixel_height=100
    ))

    job2 = runner.add_job(JobParameters(
        source_path=valid_file2,
        output_path=out2,
        output_format="PNG",
        dimension_mode=DimensionMode.PIXEL_DIMS,
        pixel_width=120,
        pixel_height=120
    ))

    # Process all synchronously in thread
    runner.start_processing()
    
    # Wait for completion
    timeout = 15.0
    start_t = time.time()
    while runner.is_running and (time.time() - start_t) < timeout:
        time.sleep(0.1)

    jobs = runner.get_jobs()
    assert len(jobs) == 3

    # Job 1 must be COMPLETED
    assert jobs[0].status == JobStatus.COMPLETED
    assert os.path.exists(out1)

    # Job Bad must be FAILED, with descriptive error
    assert jobs[1].status == JobStatus.FAILED
    assert "Cannot open image" in (jobs[1].error_message or "")
    assert not os.path.exists(out_corrupt)

    # Job 2 must be COMPLETED despite the failure of Job Bad!
    assert jobs[2].status == JobStatus.COMPLETED
    assert os.path.exists(out2)


def test_acceptance_11_cancellation_leaves_no_successful_file(tmp_path):
    """
    Check 11: Cancellation leaves no final file presented as successful and removes temporary files.
    """
    src_file = str(tmp_path / "big_canvas_src.png")
    out_file = str(tmp_path / "cancelled_export.png")

    im = Image.new("RGB", (100, 100), (200, 150, 100))
    im.save(src_file, format="PNG")

    cancelled_flag = [False]

    def cancel_trigger():
        return cancelled_flag[0]

    params = JobParameters(
        source_path=src_file,
        output_path=out_file,
        output_format="PNG",
        dimension_mode=DimensionMode.PIXEL_DIMS,
        pixel_width=500,
        pixel_height=500
    )

    # Cancel immediately
    cancelled_flag[0] = True
    res = execute_pipeline(params, is_cancelled_callback=cancel_trigger)

    assert res.success is False
    assert "Cancel" in (res.error_message or "")
    # Crucial check: destination file must NOT exist!
    assert not os.path.exists(out_file), "Cancelled file was written to destination!"
