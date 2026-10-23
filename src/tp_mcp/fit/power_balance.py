"""Left/right power balance bucketed by total power."""

from typing import Any

from tp_mcp.fit.parser import WorkoutDataPoint

PowerBuckets = dict[tuple[int, int], dict[str, float | int]]


def bucket_left_right_power(workout: list[WorkoutDataPoint], bucket_size: int) -> PowerBuckets:
    """Sum left/right power samples into total-power buckets.

    Buckets are lower-inclusive, upper-exclusive (size 50 -> (0, 50), (50, 100), ...).
    Samples missing power or balance are skipped.
    """
    if bucket_size <= 0:
        raise ValueError("bucket_size must be a positive integer")

    usable = [
        (p.power, p.left_power, p.right_power)
        for p in workout
        if p.power is not None and p.power >= 0 and p.left_power is not None and p.right_power is not None
    ]
    if not usable:
        return {}

    highest = max(power // bucket_size for power, _, _ in usable)
    buckets: PowerBuckets = {
        (lower, lower + bucket_size): {"left_power": 0.0, "right_power": 0.0, "datapoints": 0}
        for lower in range(0, (highest + 1) * bucket_size, bucket_size)
    }
    for power, left, right in usable:
        lower = (power // bucket_size) * bucket_size
        bucket = buckets[(lower, lower + bucket_size)]
        bucket["left_power"] += left
        bucket["right_power"] += right
        bucket["datapoints"] += 1
    return buckets


def _format_duration(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{secs:02}"


def summarize_power_buckets(buckets: PowerBuckets, datapoint_length: int | None = None) -> dict[str, Any]:
    """Convert buckets to JSON-friendly rows with balance percentages.

    ``datapoint_length`` is the duration of each sample in seconds.
    """
    if datapoint_length is not None and datapoint_length <= 0:
        raise ValueError("datapoint_length must be a positive number of seconds")

    rows: list[dict[str, Any]] = []
    for (lower, upper), values in sorted(buckets.items()):
        left = float(values["left_power"])
        right = float(values["right_power"])
        total = left + right
        count = int(values["datapoints"])
        row: dict[str, Any] = {
            "range_watts": [lower, upper],
            "left_watts_total": round(left, 1),
            "right_watts_total": round(right, 1),
            "left_pct": round(left / total * 100, 2) if total else None,
            "right_pct": round(right / total * 100, 2) if total else None,
            "datapoints": count,
        }
        if datapoint_length is not None:
            row["duration"] = _format_duration(count * datapoint_length)
        rows.append(row)

    total_points = sum(r["datapoints"] for r in rows)
    summary: dict[str, Any] = {"total_datapoints": total_points, "buckets": rows}
    if datapoint_length is not None:
        summary["total_duration"] = _format_duration(total_points * datapoint_length)
    return summary


def format_power_buckets(buckets: PowerBuckets, datapoint_length: int | None = None) -> str:
    """Render buckets as human-readable text (one line per bucket)."""
    summary = summarize_power_buckets(buckets, datapoint_length)
    header = f"Data points included in buckets: {summary['total_datapoints']}"
    if datapoint_length is not None:
        header += f" | Duration: {summary['total_duration']}"
    if not summary["buckets"]:
        return header + "\nNo power buckets to display."

    lines = [header]
    for row in summary["buckets"]:
        lower, upper = row["range_watts"]
        if row["left_pct"] is None:
            balance = "Left — / Right — (no power)"
        else:
            balance = f"Left {row['left_pct']:.2f}% / Right {row['right_pct']:.2f}%"
        total = row["left_watts_total"] + row["right_watts_total"]
        count = row["datapoints"]
        line = (
            f"{lower}–{upper} W: Left {int(row['left_watts_total'])} W, Right {int(row['right_watts_total'])} W, "
            f"Total {int(total)} W | {balance} | {count} data point{'s' if count != 1 else ''}"
        )
        if "duration" in row:
            line += f" | Duration: {row['duration']}"
        lines.append(line)
    return "\n".join(lines)
