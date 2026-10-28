"""Tests for the timezone helpers behind the `timezone` tool parameter."""

from zoneinfo import ZoneInfo

import pytest

from tp_mcp.tools._time import TP_SERVER_TIMEZONE, naive_to_local, resolve_timezone, server_time_to_local, utc_to_local


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


class TestServerTimeToLocal:
    """dateUploaded is TrainingPeaks server time (America/Denver), not UTC."""

    MADRID = ZoneInfo("Europe/Madrid")

    def test_source_zone_is_denver(self):
        assert TP_SERVER_TIMEZONE == "America/Denver"

    def test_live_example_2026_10_27(self):
        # File ...2026-10-27-10-57-53-135Z... (10:57:53 UTC) carried dateUploaded 04:57:53 (MDT, UTC-6).
        assert server_time_to_local("2026-10-27T04:57:53", ZoneInfo("UTC")) == "2026-10-27T10:57:53+00:00"
        assert server_time_to_local("2026-10-27T04:57:53", self.MADRID) == "2026-10-27T11:57:53+01:00"

    def test_other_live_examples(self):
        assert server_time_to_local("2026-10-28T03:43:28", ZoneInfo("UTC")) == "2026-10-28T09:43:28+00:00"
        assert server_time_to_local("2026-10-26T02:22:47", ZoneInfo("UTC")) == "2026-10-26T08:22:47+00:00"

    def test_winter_upload_is_utc_minus_7(self):
        # January: Denver is on MST (UTC-7), so the same wall-clock value is an hour later in UTC.
        assert server_time_to_local("2026-01-15T04:57:53", ZoneInfo("UTC")) == "2026-01-15T11:57:53+00:00"
        assert server_time_to_local("2026-01-15T04:57:53", self.MADRID) == "2026-01-15T12:57:53+01:00"
        assert server_time_to_local("2026-01-15T04:57:53", ZoneInfo("Europe/London")) == "2026-01-15T11:57:53+00:00"

    def test_dst_boundary_is_resolved_on_the_timestamp_itself(self):
        # US DST ends 2026-11-01 02:00 local. 2026-10-31 is still MDT (-6); 2026-11-02 is MST (-7).
        assert server_time_to_local("2026-10-31T12:00:00", ZoneInfo("UTC")) == "2026-10-31T18:00:00+00:00"
        assert server_time_to_local("2026-11-02T12:00:00", ZoneInfo("UTC")) == "2026-11-02T19:00:00+00:00"
        # Europe changed a week earlier, so the Madrid offset flips independently.
        assert server_time_to_local("2026-10-31T12:00:00", self.MADRID) == "2026-10-31T19:00:00+01:00"
        assert server_time_to_local("2026-10-24T12:00:00", self.MADRID) == "2026-10-24T20:00:00+02:00"

    def test_explicit_offset_in_input_wins_over_source_zone(self):
        assert server_time_to_local("2026-10-27T10:57:53Z", self.MADRID) == "2026-10-27T11:57:53+01:00"

    def test_utc_to_local_is_unchanged_for_analysis_timestamps(self):
        # Analysis startTimestamp stays UTC: run started 10:37 CET -> startTimestamp 09:37:03.
        assert utc_to_local("2026-10-27T09:37:03", self.MADRID) == "2026-10-27T10:37:03+01:00"
        assert naive_to_local("2026-10-27T09:37:03", self.MADRID, ZoneInfo("UTC")) == "2026-10-27T10:37:03+01:00"

    @pytest.mark.parametrize("bad", [None, "", "garbage", 7])
    def test_unparseable_returns_none(self, bad):
        assert server_time_to_local(bad, self.MADRID) is None
