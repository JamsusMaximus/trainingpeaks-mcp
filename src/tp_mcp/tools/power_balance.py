"""Left/right power balance analysis over downloaded workout files."""

from pathlib import Path
from typing import Any

from tp_mcp.fit import (
    bucket_left_right_power,
    flatten_workouts,
    format_power_buckets,
    load_workout,
    summarize_power_buckets,
)


def _error(code: str, message: str) -> dict[str, Any]:
    return {"isError": True, "error_code": code, "message": message}


async def tp_analyze_power_balance(
    file_paths: list[str],
    bucket_size: int = 50,
    sample_seconds: int | None = None,
) -> dict[str, Any]:
    """Analyze left/right power balance by power bucket from downloaded .fit.gz files.

    Args:
        file_paths: Paths returned as saved_to by tp_download_workout_file. Multiple files are combined.
        bucket_size: Width of each total-power bucket in watts.
        sample_seconds: Seconds per data point, used to report durations.

    Returns:
        Dict with per-bucket balance rows, a text table, and any skipped files.
    """
    if not file_paths:
        return _error("VALIDATION_ERROR", "file_paths must contain at least one path.")
    if not isinstance(bucket_size, int) or bucket_size <= 0:
        return _error("VALIDATION_ERROR", "bucket_size must be a positive integer.")
    if sample_seconds is not None and (not isinstance(sample_seconds, int) or sample_seconds <= 0):
        return _error("VALIDATION_ERROR", "sample_seconds must be a positive integer.")

    workouts = []
    failed: list[dict[str, str]] = []
    for path in file_paths:
        if not Path(path).is_file():
            failed.append({"file": path, "error": "File not found."})
            continue
        try:
            workouts.append(load_workout(path))
        except ImportError:
            return _error("DEPENDENCY_MISSING", "The 'fitparse' package is required to analyze FIT files.")
        except Exception as e:  # corrupt gzip/FIT content
            failed.append({"file": path, "error": f"Could not parse file: {e}"})

    if not workouts:
        return _error("VALIDATION_ERROR", f"No files could be loaded: {failed}")

    points = flatten_workouts(workouts)
    buckets = bucket_left_right_power(points, bucket_size)
    result = summarize_power_buckets(buckets, sample_seconds)
    result.update(
        {
            "files_analyzed": len(workouts),
            "records_total": len(points),
            "bucket_size": bucket_size,
            "text": format_power_buckets(buckets, sample_seconds),
        }
    )
    if failed:
        result["skipped_files"] = failed
    if not buckets:
        result["message"] = "No records contained both power and left/right balance (needs a dual-sided power meter)."
    return result
