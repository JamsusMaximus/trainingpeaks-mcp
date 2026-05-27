"""Tests for athlete settings tools."""

from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.client.http import APIResponse
from tp_mcp.tools.settings import (
    _parse_pace_to_ms,
    _summarize_settings,
    tp_get_athlete_settings,
    tp_get_athlete_settings_summary,
    tp_update_ftp,
    tp_update_hr_zones,
    tp_update_nutrition,
    tp_update_speed_zones,
)


class TestGetAthleteSettings:
    @pytest.mark.asyncio
    async def test_success(self):
        response = APIResponse(success=True, data={"threshold": 280, "zones": []})
        with patch("tp_mcp.tools.settings.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_athlete_settings()
        assert "settings" in result


class TestGetAthleteSettingsSummary:
    def test_summary_includes_thresholds_and_zones(self):
        settings = {
            "athleteId": 123,
            "email": "athlete@example.com",
            "name": "Example Athlete",
            "powerZones": [
                {
                    "threshold": 250,
                    "workoutTypeId": 2,
                    "zones": [
                        {"label": "Easy", "minimum": 0, "maximum": 140},
                        {"label": "Endurance", "minimum": 141, "maximum": 190},
                    ],
                }
            ],
            "heartRateZones": [
                {
                    "threshold": 165,
                    "workoutTypeId": 2,
                    "zones": [{"label": "Z1", "minimum": 90, "maximum": 130}],
                }
            ],
            "speedZones": [
                {"threshold": 3.704, "workoutTypeId": 3},
                {"threshold": 0.952, "workoutTypeId": 1},
            ],
        }

        summary = _summarize_settings(settings)

        assert summary == {
            "lthr_bpm_bike": 165,
            "hr_zones_bike": [{"label": "Z1", "min": 90.0, "max": 130.0}],
            "lt_pace_run": {"threshold_m_per_s": 3.704, "pace_min_per_km": "4:30/km"},
            "lt_pace_swim": {"threshold_m_per_s": 0.952, "pace_min_per_100m": "1:45/100m"},
            "ftp_watts_bike": 250,
            "power_zones_bike": [
                {"label": "Easy", "min": 0.0, "max": 140.0},
                {"label": "Endurance", "min": 141.0, "max": 190.0},
            ],
        }
        assert "athleteId" not in summary
        assert "email" not in summary
        assert "name" not in summary

    @pytest.mark.asyncio
    async def test_summary_tool_returns_only_summary(self):
        settings = {
            "athleteId": 123,
            "email": "athlete@example.com",
            "powerZones": [{"threshold": 250, "workoutTypeId": 2}],
        }
        response = APIResponse(success=True, data=settings)
        with patch("tp_mcp.tools.settings.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_athlete_settings_summary()

        assert result == {"summary": {"ftp_watts_bike": 250}}


class TestUpdateFTP:
    @pytest.mark.asyncio
    async def test_coggan_zones_320w(self):
        """FTP 320W should scale the existing default power zone model."""
        response = APIResponse(success=True, data=None)
        settings = {
            "powerZones": [
                {
                    "zoneCalculatorId": None,
                    "threshold": 280,
                    "calculationMethod": 5,
                    "workoutTypeId": 0,
                    "zones": [
                        {"label": "Recovery", "minimum": 0, "maximum": 156},
                        {"label": "Endurance", "minimum": 157, "maximum": 212},
                        {"label": "Tempo", "minimum": 213, "maximum": 254},
                        {"label": "Threshold", "minimum": 255, "maximum": 296},
                        {"label": "VO2 Max", "minimum": 297, "maximum": 338},
                        {"label": "Anaerobic Capacity", "minimum": 339, "maximum": 2000},
                    ],
                },
                {
                    "zoneCalculatorId": None,
                    "threshold": 300,
                    "calculationMethod": 4,
                    "workoutTypeId": 3,
                    "zones": [{"label": str(i), "minimum": i, "maximum": i} for i in range(1, 7)],
                },
            ],
        }
        with patch("tp_mcp.tools.settings.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=APIResponse(success=True, data=settings))
            mock_instance.put = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_update_ftp(ftp=320)

        assert result["success"] is True
        assert result["ftp"] == 320
        zones = result["zones"]
        assert len(zones) == 6
        # Existing maxima [156, 212, 254, 296, 338] are scaled from 280W to 320W
        assert zones[0]["minimum"] == 0
        assert zones[0]["maximum"] == 178
        assert zones[1]["minimum"] == 179
        assert zones[1]["maximum"] == 242
        assert zones[3]["minimum"] == 291
        assert zones[3]["maximum"] == 338
        assert zones[5]["minimum"] == 387
        assert zones[5]["maximum"] == 2000

        payload = mock_instance.put.call_args[1]["json"]
        assert len(payload) == 2
        assert payload[0]["threshold"] == 320
        assert payload[0]["workoutTypeId"] == 0
        assert payload[0]["zones"] == zones
        assert payload[1] == settings["powerZones"][1]

    @pytest.mark.asyncio
    async def test_ftp_fallback_when_threshold_is_zero(self):
        """FTP update uses hardcoded ratios when current_threshold is 0."""
        response = APIResponse(success=True, data=None)
        settings = {
            "powerZones": [
                {
                    "threshold": 0,
                    "calculationMethod": 5,
                    "workoutTypeId": 0,
                    "zones": [
                        {"label": "Recovery", "minimum": 0, "maximum": 156},
                        {"label": "Endurance", "minimum": 157, "maximum": 212},
                        {"label": "Tempo", "minimum": 213, "maximum": 254},
                        {"label": "Threshold", "minimum": 255, "maximum": 296},
                        {"label": "VO2 Max", "minimum": 297, "maximum": 338},
                        {"label": "Anaerobic Capacity", "minimum": 339, "maximum": 2000},
                    ],
                }
            ],
        }
        with patch("tp_mcp.tools.settings.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=APIResponse(success=True, data=settings))
            mock_instance.put = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_update_ftp(ftp=200)

        assert result["success"] is True
        assert result["ftp"] == 200
        zones = result["zones"]
        assert len(zones) == 6
        # Hardcoded ratios: 0.56, 0.76, 0.91, 1.06, 1.21
        assert zones[0]["maximum"] == round(200 * 0.56)
        assert zones[1]["maximum"] == round(200 * 0.76)
        assert zones[2]["maximum"] == round(200 * 0.91)
        assert zones[3]["maximum"] == round(200 * 1.06)
        assert zones[4]["maximum"] == round(200 * 1.21)
        assert zones[5]["maximum"] == 2000

    @pytest.mark.asyncio
    async def test_ftp_fallback_when_zones_malformed(self):
        """FTP update uses hardcoded ratios when existing zones have non-numeric maxima."""
        response = APIResponse(success=True, data=None)
        settings = {
            "powerZones": [
                {
                    "threshold": 280,
                    "calculationMethod": 5,
                    "workoutTypeId": 0,
                    "zones": [
                        {"label": "Recovery", "minimum": 0, "maximum": "bad"},
                        {"label": "Endurance", "minimum": 157, "maximum": 212},
                        {"label": "Tempo", "minimum": 213, "maximum": 254},
                        {"label": "Threshold", "minimum": 255, "maximum": 296},
                        {"label": "VO2 Max", "minimum": 297, "maximum": 338},
                        {"label": "Anaerobic Capacity", "minimum": 339, "maximum": 2000},
                    ],
                }
            ],
        }
        with patch("tp_mcp.tools.settings.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=APIResponse(success=True, data=settings))
            mock_instance.put = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_update_ftp(ftp=300)

        assert result["success"] is True
        zones = result["zones"]
        assert len(zones) == 6
        # Falls back to hardcoded ratios: 0.56, 0.76, 0.91, 1.06, 1.21
        assert zones[0]["maximum"] == round(300 * 0.56)
        assert zones[1]["maximum"] == round(300 * 0.76)
        assert zones[2]["maximum"] == round(300 * 0.91)
        assert zones[3]["maximum"] == round(300 * 1.06)
        assert zones[4]["maximum"] == round(300 * 1.21)
        assert zones[5]["maximum"] == 2000

    @pytest.mark.asyncio
    async def test_ftp_validation(self):
        result = await tp_update_ftp(ftp=0)
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"


class TestUpdateHRZones:
    @pytest.mark.asyncio
    async def test_threshold_update(self):
        response = APIResponse(success=True, data=None)
        with patch("tp_mcp.tools.settings.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.put = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_update_hr_zones(threshold_hr=165)

        assert result["success"] is True
        payload = mock_instance.put.call_args[1]["json"]
        assert payload["threshold"] == 165

    @pytest.mark.asyncio
    async def test_max_hr_only(self):
        response = APIResponse(success=True, data=None)
        with patch("tp_mcp.tools.settings.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.put = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_update_hr_zones(max_hr=195)

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_no_params_rejected(self):
        result = await tp_update_hr_zones()
        assert result["isError"] is True


class TestUpdateSpeedZones:
    def test_parse_run_pace(self):
        """4:30/km = 1000m / 270s = 3.704 m/s."""
        speed = _parse_pace_to_ms("4:30/km")
        assert abs(speed - 3.704) < 0.01

    def test_parse_swim_pace(self):
        """1:45/100m = 100m / 105s = 0.952 m/s."""
        speed = _parse_pace_to_ms("1:45/100m", is_swim=True)
        assert abs(speed - 0.952) < 0.01

    @pytest.mark.asyncio
    async def test_run_pace_update(self):
        response = APIResponse(success=True, data=None)
        with patch("tp_mcp.tools.settings.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.put = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_update_speed_zones(run_threshold_pace="4:30/km")

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_invalid_pace_format(self):
        result = await tp_update_speed_zones(run_threshold_pace="invalid")
        assert result["isError"] is True

    @pytest.mark.asyncio
    async def test_no_params_rejected(self):
        result = await tp_update_speed_zones()
        assert result["isError"] is True


class TestUpdateNutrition:
    @pytest.mark.asyncio
    async def test_success(self):
        response = APIResponse(success=True, data=None)
        with patch("tp_mcp.tools.settings.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_update_nutrition(planned_calories=2500)

        assert result["success"] is True
        assert result["planned_calories"] == 2500
