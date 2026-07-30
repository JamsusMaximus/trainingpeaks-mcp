"""Guard tests: every tool must declare a title and behaviour annotations.

If your new tool fails here: give it a name matching the conventions
(tp_get_*/tp_list_* for reads, tp_delete_* for destructive removals,
tp_create_*/tp_add_* for creates) or add it to the exception sets next to the
metadata block in server.py (_DESTRUCTIVE_TOOLS / _NON_IDEMPOTENT_WRITES /
_READ_ONLY_EXTRA / _TITLE_OVERRIDES). See "Adding a tool" in the README.
"""

from tp_mcp.server import _DESTRUCTIVE_TOOLS, _NON_IDEMPOTENT_WRITES, TOOLS

_HELP = "See tests/test_tool_metadata.py docstring for how to fix this."


class TestEveryToolHasMetadata:
    def test_every_tool_has_title(self):
        missing = [t.name for t in TOOLS if not t.title]
        assert not missing, f"Tools without a title: {missing}. {_HELP}"

    def test_every_tool_has_annotations(self):
        missing = [t.name for t in TOOLS if t.annotations is None]
        assert not missing, f"Tools without annotations: {missing}. {_HELP}"

    def test_every_tool_declares_open_world(self):
        bad = [t.name for t in TOOLS if not t.annotations.open_world_hint]
        assert not bad, f"All tools call the external TrainingPeaks API: {bad}. {_HELP}"


class TestReadWriteClassification:
    def test_read_prefixed_tools_are_read_only(self):
        bad = [
            t.name
            for t in TOOLS
            if t.name.startswith(("tp_get_", "tp_list_", "tp_download_", "tp_search_", "tp_validate_", "tp_analyze_"))
            and not t.annotations.read_only_hint
        ]
        assert not bad, f"Read-prefixed tools missing readOnlyHint: {bad}. {_HELP}"

    def test_delete_tools_are_destructive(self):
        bad = [t.name for t in TOOLS if t.name.startswith("tp_delete_") and not t.annotations.destructive_hint]
        assert not bad, f"tp_delete_* tools missing destructiveHint: {bad}. {_HELP}"

    def test_no_read_only_tool_is_destructive(self):
        bad = [t.name for t in TOOLS if t.annotations.read_only_hint and t.annotations.destructive_hint]
        assert not bad, f"Contradictory metadata (read-only AND destructive): {bad}"

    def test_exception_sets_only_name_real_tools(self):
        names = {t.name for t in TOOLS}
        stale = (_DESTRUCTIVE_TOOLS | _NON_IDEMPOTENT_WRITES) - names
        assert not stale, f"Exception sets name tools that no longer exist: {stale}"


class TestSpotChecks:
    """Hand-written expectations, independent of the derivation rules."""

    def _tool(self, name):
        return next(t for t in TOOLS if t.name == name)

    def test_get_workouts(self):
        t = self._tool("tp_get_workouts")
        assert t.title == "Get workouts"
        assert t.annotations.read_only_hint is True
        assert t.annotations.destructive_hint is False

    def test_delete_workout(self):
        t = self._tool("tp_delete_workout")
        assert t.title == "Delete workout"
        assert t.annotations.read_only_hint is False
        assert t.annotations.destructive_hint is True
        assert t.annotations.idempotent_hint is True  # deleting twice: same state

    def test_create_workout_is_non_idempotent_create(self):
        t = self._tool("tp_create_workout")
        assert t.annotations.read_only_hint is False
        assert t.annotations.destructive_hint is False
        assert t.annotations.idempotent_hint is False  # retry duplicates

    def test_update_ftp_is_idempotent_write(self):
        t = self._tool("tp_update_ftp")
        assert t.title == "Update FTP"
        assert t.annotations.read_only_hint is False
        assert t.annotations.idempotent_hint is True

    def test_remove_athletes_is_destructive_non_delete_name(self):
        t = self._tool("tp_remove_athletes_from_group")
        assert t.annotations.destructive_hint is True

    def test_acronym_titles(self):
        assert self._tool("tp_update_hr_zones").title == "Update HR zones"
        assert self._tool("tp_get_workout_prs").title == "Get workout PRs"
        assert self._tool("tp_get_atp").title == "Get ATP (annual training plan)"

    def test_auth_status_override(self):
        t = self._tool("tp_auth_status")
        assert t.title == "Check auth status"
        assert t.annotations.read_only_hint is True
