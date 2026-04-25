"""Weekly summary tool - combines workouts and fitness data."""

import asyncio
import logging
from datetime import date, timedelta
from typing import Any

from pydantic import ValidationError

from tp_mcp.tools._validation import SingleDateInput, format_validation_error
from tp_mcp.tools.fitness import tp_get_fitness
from tp_mcp.tools.workouts import tp_get_workouts

logger = logging.getLogger("tp-mcp")


def _get_week_bounds(ref_date: date) -> tuple[date, date]:
    """Get Monday-Sunday bounds for the week containing ref_date."""
    monday = ref_date - timedelta(days=ref_date.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


async def tp_get_weekly_summary(week_of: str | None = None) -> dict[str, Any]:
    """Get combined view of workouts + fitness metrics for a week.

    Args:
        week_of: Optional date within the week (YYYY-MM-DD). Defaults to current week.

    Returns:
        Dict with workout list, totals, and fitness metrics.
    """
    if week_of:
        try:
            validated = SingleDateInput(date=week_of)
            ref_date = validated.date
        except (ValidationError, ValueError) as e:
            msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
            return {
                "isError": True,
                "error_code": "VALIDATION_ERROR",
                "message": msg,
            }
    else:
        ref_date = date.today()

    monday, sunday = _get_week_bounds(ref_date)

    # Parallel fetch of workouts and fitness data
    workouts_task = tp_get_workouts(monday.isoformat(), sunday.isoformat())
    fitness_task = tp_get_fitness(
        days=7,
        start_date=monday.isoformat(),
        end_date=sunday.isoformat(),
    )

    workouts_result, fitness_result = await asyncio.gather(workouts_task, fitness_task)

    # Compute totals from workouts
    total_tss = 0.0
    total_duration_hours = 0.0
    workout_count = 0

    if not workouts_result.get("isError"):
        for w in workouts_result.get("workouts", []):
            workout_count += 1
            tss = w.get("tss")
            if tss is not None:
                total_tss += tss
            dur = w.get("duration_actual") or w.get("duration_planned")
            if dur is not None:
                total_duration_hours += dur

    # Extract end-of-week fitness metrics
    end_of_week_fitness = None
    if not fitness_result.get("isError"):
        daily_data = fitness_result.get("daily_data", [])
        if daily_data:
            end_of_week_fitness = daily_data[-1]

    return {
        "week": {"start": monday.isoformat(), "end": sunday.isoformat()},
        "workouts": workouts_result.get("workouts", []) if not workouts_result.get("isError") else [],
        "workout_count": workout_count,
        "total_tss": round(total_tss, 1),
        "total_duration_hours": round(total_duration_hours, 2),
        "fitness": end_of_week_fitness,
    }
