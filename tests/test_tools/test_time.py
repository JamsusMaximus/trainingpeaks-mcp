"""Tests for the timezone helpers behind the `timezone` tool parameter."""

from zoneinfo import ZoneInfo

import pytest

from tp_mcp.tools._time import resolve_timezone, utc_to_local


class TestResolveTimezone:
    def test_valid_name(self):
        zone, err = resolve_timezone("Europe/Madrid")
        assert err is None
        assert isinstance(zone, ZoneInfo)
        assert zone.key == "Europe/Madrid"

    @pytest.mark.parametrize("empty", [None, "", "   "])
    def test_absent_means_no_zone_and_no_error(self, empty):
        assert resolve_timezone(empty) == (None, None)

    @pytest.mark.parametrize("bad", ["Europe/Nowhere", "BST", "GMT+1", "../etc/passwd"])
    def test_unknown_name_is_a_validation_error(self, bad):
        zone, err = resolve_timezone(bad)
        assert zone is None
        assert err["isError"] is True
        assert err["error_code"] == "VALIDATION_ERROR"
        assert bad in err["message"]
        assert "IANA" in err["message"]


class TestUtcToLocal:
    LONDON = ZoneInfo("Europe/London")

    def test_naive_is_treated_as_utc_summer(self):
        assert utc_to_local("2026-07-01T06:15:00", self.LONDON) == "2026-07-01T07:15:00+01:00"

    def test_naive_is_treated_as_utc_winter(self):
        assert utc_to_local("2026-11-01T06:15:00", self.LONDON) == "2026-11-01T06:15:00+00:00"

    def test_other_zone(self):
        assert utc_to_local("2026-10-27T06:15:00", ZoneInfo("Europe/Madrid")) == "2026-10-27T07:15:00+01:00"
        assert utc_to_local("2026-10-27T06:15:00", ZoneInfo("America/Denver")) == "2026-10-27T00:15:00-06:00"

    def test_zulu_suffix_and_explicit_offset_are_honoured(self):
        assert utc_to_local("2026-07-01T06:15:00Z", self.LONDON) == "2026-07-01T07:15:00+01:00"
        assert utc_to_local("2026-07-01T08:15:00+02:00", self.LONDON) == "2026-07-01T07:15:00+01:00"

    def test_dotnet_seven_digit_fraction_is_accepted(self):
        out = utc_to_local("2026-07-01T06:15:00.1234567", self.LONDON)
        assert out == "2026-07-01T07:15:00.123456+01:00"

    @pytest.mark.parametrize("bad", [None, "", "   ", "not a date", 42, "2026-13-45T00:00:00"])
    def test_unparseable_input_returns_none(self, bad):
        assert utc_to_local(bad, self.LONDON) is None
