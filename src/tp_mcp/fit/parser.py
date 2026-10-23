"""Load gzipped FIT files into typed per-sample records."""

import gzip
from datetime import datetime

from pydantic import BaseModel, computed_field


def decode_left_right_balance(value: int, power: float | None = None) -> dict[str, int | float]:
    """Decode FIT's encoded left/right balance and optionally split power."""
    pct = value & 0x7F
    # Bit 7 set means the percentage is the right-leg share.
    if value & 0x80:
        right, left = pct, 100 - pct
    else:
        left, right = pct, 100 - pct

    result: dict[str, int | float] = {"left_pct": left, "right_pct": right}
    if power is not None:
        result["left_watts"] = round(power * left / 100, 1)
        result["right_watts"] = round(power * right / 100, 1)
    return result


class WorkoutDataPoint(BaseModel):
    accumulated_power: int | None = None  # watts
    cadence: int | None = None  # rpm
    distance: float | None = None  # meters
    enhanced_altitude: float | None = None  # meters
    enhanced_speed: float | None = None  # m/s
    heart_rate: int | None = None  # bpm
    power: int | None = None  # watts
    left_power_phase: tuple[float | None, float | None] | None = None  # degrees
    left_power_phase_peak: tuple[float | None, float | None] | None = None  # degrees
    right_power_phase: tuple[float | None, float | None] | None = None  # degrees
    right_power_phase_peak: tuple[float | None, float | None] | None = None  # degrees
    timestamp: datetime | None = None
    left_right_balance: int | None = None  # raw encoded FIT value

    def _split(self) -> dict[str, int | float]:
        if self.left_right_balance is None or self.power is None:
            return {}
        return decode_left_right_balance(self.left_right_balance, self.power)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def left_power(self) -> float | None:
        value = self._split().get("left_watts")
        return float(value) if value is not None else None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def right_power(self) -> float | None:
        value = self._split().get("right_watts")
        return float(value) if value is not None else None


def flatten_workouts(workouts: list[list[WorkoutDataPoint]]) -> list[WorkoutDataPoint]:
    """Combine multiple workouts into one list of data points."""
    return [point for workout in workouts for point in workout]


def load_workout(filepath: str) -> list[WorkoutDataPoint]:
    """Read a gzipped FIT file and return its record data points."""
    import fitparse  # lazy: keeps server startup independent of the parser

    workout: list[WorkoutDataPoint] = []
    with gzip.open(filepath, "rb") as compressed_fit:
        fitfile = fitparse.FitFile(compressed_fit)
        for record in fitfile.get_messages("record"):
            workout.append(
                WorkoutDataPoint(
                    accumulated_power=record.get_value("accumulated_power"),
                    cadence=record.get_value("cadence"),
                    distance=record.get_value("distance"),
                    enhanced_altitude=record.get_value("enhanced_altitude"),
                    enhanced_speed=record.get_value("enhanced_speed"),
                    heart_rate=record.get_value("heart_rate"),
                    power=record.get_value("power"),
                    left_power_phase=record.get_value("left_power_phase"),
                    left_power_phase_peak=record.get_value("left_power_phase_peak"),
                    right_power_phase=record.get_value("right_power_phase"),
                    right_power_phase_peak=record.get_value("right_power_phase_peak"),
                    timestamp=record.get_value("timestamp"),
                    left_right_balance=record.get_raw_value("left_right_balance"),
                )
            )
    return workout
