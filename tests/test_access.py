"""Tests for the least-privilege access policy."""

import pytest

from tp_mcp import access
from tp_mcp.access import AccessLevel, classify, is_tool_allowed


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(access.MODE_ENV_VAR, raising=False)
    monkeypatch.delenv(access.DISABLED_ENV_VAR, raising=False)


def test_default_mode_is_full_backwards_compatible():
    assert access.current_mode() == "full"
    assert is_tool_allowed("tp_delete_workout")
    assert is_tool_allowed("tp_create_workout")
    assert is_tool_allowed("tp_get_workouts")


def test_read_mode_blocks_all_writes_and_deletes(monkeypatch):
    monkeypatch.setenv(access.MODE_ENV_VAR, "read")
    assert is_tool_allowed("tp_get_workouts")            # read ok
    assert is_tool_allowed("tp_refresh_auth")            # auth ok
    assert not is_tool_allowed("tp_create_workout")      # write blocked
    assert not is_tool_allowed("tp_update_ftp")          # write blocked
    assert not is_tool_allowed("tp_delete_workout")      # delete blocked
    assert not is_tool_allowed("tp_upload_workout_file")  # write blocked


def test_write_mode_allows_writes_but_not_deletes(monkeypatch):
    monkeypatch.setenv(access.MODE_ENV_VAR, "write")
    assert is_tool_allowed("tp_create_workout")
    assert is_tool_allowed("tp_update_ftp")
    assert not is_tool_allowed("tp_delete_workout")
    assert not is_tool_allowed("tp_delete_group")


def test_disabled_list_overrides_mode(monkeypatch):
    monkeypatch.setenv(access.MODE_ENV_VAR, "full")
    monkeypatch.setenv(access.DISABLED_ENV_VAR, "tp_upload_workout_file, tp_delete_workout")
    assert not is_tool_allowed("tp_upload_workout_file")
    assert not is_tool_allowed("tp_delete_workout")
    assert is_tool_allowed("tp_create_workout")  # not in the disabled list


def test_unknown_tool_fails_safe(monkeypatch):
    # Unknown non-destructive name -> WRITE (hidden in read mode)
    monkeypatch.setenv(access.MODE_ENV_VAR, "read")
    assert classify("tp_frobnicate_thing") == AccessLevel.WRITE
    assert not is_tool_allowed("tp_frobnicate_thing")
    # Unknown removal-shaped name -> DELETE (hidden unless full)
    assert classify("tp_purge_everything") == AccessLevel.DELETE
    monkeypatch.setenv(access.MODE_ENV_VAR, "write")
    assert not is_tool_allowed("tp_purge_everything")


def test_invalid_mode_falls_back_to_default(monkeypatch):
    monkeypatch.setenv(access.MODE_ENV_VAR, "banana")
    assert access.current_mode() == "full"


def test_classification_partitions_all_known_tools():
    # Every delete tool classifies as DELETE; sanity on the read set too.
    for name in access._DELETE_TOOLS:
        assert classify(name) == AccessLevel.DELETE
    for name in access._READ_TOOLS:
        assert classify(name) == AccessLevel.READ
    assert classify("tp_refresh_auth") == AccessLevel.AUTH
