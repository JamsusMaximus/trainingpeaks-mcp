"""Tests for workout structure builder, validator, and IF/TSS computation."""

import json

import pytest

from tp_mcp.tools.structure import (
    SimpleRepetitionBlock,
    SimpleStep,
    SimpleWorkoutStructure,
    build_wire_structure,
    compute_if_tss,
    parse_structure_input,
    tp_validate_structure,
)


class TestBuildSimpleStep:
    """Test building single steps and verifying wire format."""

    def test_snake_case_intensity_class(self):
        step = SimpleStep(
            name="Warm Up", duration_seconds=600,
            intensity_min=40, intensity_max=55, intensity_class="warmUp",
        )
        wire = build_wire_structure(SimpleWorkoutStructure(steps=[step]))

        assert wire["structure"][0]["steps"][0]["intensityClass"] == "warmUp"

    def test_warmup_step(self):
        """The legacy camelCase alias remains accepted."""
        step = SimpleStep(
            name="Warm Up", duration_seconds=600,
            intensity_min=40, intensity_max=55, intensityClass="warmUp",
        )
        structure = SimpleWorkoutStructure(steps=[step])
        wire = build_wire_structure(structure)

        assert len(wire["structure"]) == 1
        block = wire["structure"][0]
        assert block["type"] == "step"
        assert block["begin"] == 0
        assert block["end"] == 600
        assert block["steps"][0]["name"] == "Warm Up"
        assert block["steps"][0]["intensityClass"] == "warmUp"
        assert block["steps"][0]["targets"][0] == {"minValue": 40, "maxValue": 55}

    def test_active_step(self):
        step = SimpleStep(
            name="Threshold", duration_seconds=1200,
            intensity_min=95, intensity_max=105, intensityClass="active",
        )
        structure = SimpleWorkoutStructure(steps=[step])
        wire = build_wire_structure(structure)

        assert wire["structure"][0]["steps"][0]["intensityClass"] == "active"

    def test_cooldown_step(self):
        step = SimpleStep(
            name="Cool Down", duration_seconds=300,
            intensity_min=30, intensity_max=45, intensityClass="coolDown",
        )
        structure = SimpleWorkoutStructure(steps=[step])
        wire = build_wire_structure(structure)

        assert wire["structure"][0]["steps"][0]["intensityClass"] == "coolDown"

    def test_step_with_cadence(self):
        step = SimpleStep(
            name="High Cadence", duration_seconds=300,
            intensity_min=70, intensity_max=80, intensityClass="active",
            cadence_min=95, cadence_max=105,
        )
        structure = SimpleWorkoutStructure(steps=[step])
        wire = build_wire_structure(structure)

        targets = wire["structure"][0]["steps"][0]["targets"]
        assert len(targets) == 2
        assert targets[1]["unit"] == "roundOrStridePerMinute"
        assert targets[1]["minValue"] == 95
        assert targets[1]["maxValue"] == 105


class TestBuildRepetitionBlock:
    """Test building repetition blocks."""

    def test_repetition_block(self):
        steps = [
            SimpleStep(name="Hard", duration_seconds=300, intensity_min=90, intensity_max=100, intensityClass="active"),
            SimpleStep(name="Easy", duration_seconds=120, intensity_min=50, intensity_max=60, intensityClass="rest"),
        ]
        rep = SimpleRepetitionBlock(reps=4, steps=steps)
        structure = SimpleWorkoutStructure(steps=[rep])
        wire = build_wire_structure(structure)

        block = wire["structure"][0]
        assert block["type"] == "repetition"
        assert block["length"] == {"value": 4, "unit": "repetition"}
        assert len(block["steps"]) == 2
        assert block["begin"] == 0
        assert block["end"] == (300 + 120) * 4  # 1680

    def test_repetition_inner_steps(self):
        steps = [
            SimpleStep(name="ON", duration_seconds=60, intensity_min=100, intensity_max=110, intensityClass="active"),
            SimpleStep(name="OFF", duration_seconds=60, intensity_min=40, intensity_max=50, intensityClass="rest"),
        ]
        rep = SimpleRepetitionBlock(reps=8, steps=steps)
        structure = SimpleWorkoutStructure(steps=[rep])
        wire = build_wire_structure(structure)

        inner = wire["structure"][0]["steps"]
        assert inner[0]["name"] == "ON"
        assert inner[1]["name"] == "OFF"


class TestMultiBlockStructure:
    """Test multi-block structure with cumulative begin/end times."""

    def test_three_block_structure(self):
        warmup = SimpleStep(name="WU", duration_seconds=600, intensity_min=40, intensity_max=55, intensityClass="warmUp")
        intervals = SimpleRepetitionBlock(
            reps=4, steps=[
                SimpleStep(name="Hard", duration_seconds=300, intensity_min=90, intensity_max=100, intensityClass="active"),
                SimpleStep(name="Easy", duration_seconds=120, intensity_min=50, intensity_max=60, intensityClass="rest"),
            ],
        )
        cooldown = SimpleStep(name="CD", duration_seconds=600, intensity_min=40, intensity_max=55, intensityClass="coolDown")

        structure = SimpleWorkoutStructure(steps=[warmup, intervals, cooldown])
        wire = build_wire_structure(structure)

        assert len(wire["structure"]) == 3

        # Block 1: warmup 0-600
        assert wire["structure"][0]["begin"] == 0
        assert wire["structure"][0]["end"] == 600

        # Block 2: intervals 600-2280 (4 * (300+120) = 1680)
        assert wire["structure"][1]["begin"] == 600
        assert wire["structure"][1]["end"] == 2280

        # Block 3: cooldown 2280-2880
        assert wire["structure"][2]["begin"] == 2280
        assert wire["structure"][2]["end"] == 2880


class TestComputeIFTSS:
    """Test IF/TSS computation from structure."""

    def test_steady_state_workout(self):
        """60 min at 75% FTP -> IF ~0.75, TSS ~56."""
        step = SimpleStep(
            name="Endurance", duration_seconds=3600,
            intensity_min=75, intensity_max=75, intensityClass="active",
        )
        structure = SimpleWorkoutStructure(steps=[step])
        intensity_factor, tss, total = compute_if_tss(structure)

        assert total == 3600
        assert abs(intensity_factor - 0.75) < 0.01
        assert abs(tss - 56.2) < 1.0

    def test_structured_workout(self):
        """Mixed intensity workout should compute correctly."""
        warmup = SimpleStep(name="WU", duration_seconds=600, intensity_min=50, intensity_max=60, intensityClass="warmUp")
        intervals = SimpleRepetitionBlock(
            reps=4, steps=[
                SimpleStep(name="Hard", duration_seconds=300, intensity_min=95, intensity_max=105, intensityClass="active"),
                SimpleStep(name="Easy", duration_seconds=120, intensity_min=50, intensity_max=60, intensityClass="rest"),
            ],
        )
        cooldown = SimpleStep(name="CD", duration_seconds=600, intensity_min=40, intensity_max=50, intensityClass="coolDown")

        structure = SimpleWorkoutStructure(steps=[warmup, intervals, cooldown])
        intensity_factor, tss, total = compute_if_tss(structure)

        assert total == 600 + (300 + 120) * 4 + 600  # 2880
        assert intensity_factor > 0.6
        assert tss > 0

    def test_non_power_metric_is_not_estimated_with_power_model(self):
        step = SimpleStep(
            name="Tempo",
            duration_seconds=1800,
            intensity_min=85,
            intensity_max=90,
        )
        structure = SimpleWorkoutStructure(
            primary_intensity_metric="percentOfThresholdPace",
            steps=[step],
        )

        with pytest.raises(ValueError, match="only percentOfFtp"):
            compute_if_tss(structure)

    def test_empty_steps_returns_zero(self):
        """Edge case: if somehow total_seconds is 0."""
        # Cannot create empty structure due to min_length=1, so test directly
        from tp_mcp.tools.structure import SimpleWorkoutStructure

        step = SimpleStep(name="x", duration_seconds=1, intensity_min=0, intensity_max=0, intensityClass="active")
        structure = SimpleWorkoutStructure(steps=[step])
        _, _, total = compute_if_tss(structure)
        assert total == 1


class TestValidation:
    """Test structure validation."""

    def test_missing_duration_raises(self):
        with pytest.raises(Exception):
            SimpleStep(name="Bad", duration_seconds=0, intensity_min=50, intensity_max=60, intensityClass="active")

    def test_empty_steps_raises(self):
        with pytest.raises(Exception):
            SimpleWorkoutStructure(steps=[])

    def test_invalid_intensity_class(self):
        with pytest.raises(Exception):
            SimpleStep(name="Bad", duration_seconds=300, intensity_min=50, intensity_max=60, intensityClass="invalid")

    def test_intensity_min_gt_max(self):
        with pytest.raises(Exception):
            SimpleStep(name="Bad", duration_seconds=300, intensity_min=100, intensity_max=50, intensityClass="active")

    def test_invalid_primary_metric(self):
        step = SimpleStep(name="OK", duration_seconds=300, intensity_min=50, intensity_max=60, intensityClass="active")
        with pytest.raises(Exception):
            SimpleWorkoutStructure(primaryIntensityMetric="invalidMetric", steps=[step])

    @pytest.mark.parametrize(
        ("payload", "unknown_field"),
        [
            (
                {
                    "steps": [
                        {
                            "name": "Main",
                            "duration_seconds": 300,
                            "intensity_min": 50,
                            "intensity_max": 60,
                        },
                    ],
                    "primary_intensity_metic": "percentOfFtp",
                },
                "primary_intensity_metic",
            ),
            (
                {
                    "steps": [
                        {
                            "name": "Main",
                            "duration_seconds": 300,
                            "intensity_min": 50,
                            "intensity_max": 60,
                            "intensity_clas": "warmUp",
                        },
                    ],
                },
                "intensity_clas",
            ),
            (
                {
                    "steps": [
                        {
                            "type": "repetition",
                            "reps": 2,
                            "stepz": [],
                            "steps": [
                                {
                                    "name": "Main",
                                    "duration_seconds": 300,
                                    "intensity_min": 50,
                                    "intensity_max": 60,
                                },
                            ],
                        },
                    ],
                },
                "stepz",
            ),
        ],
    )
    def test_unknown_fields_are_rejected(self, payload, unknown_field):
        with pytest.raises(Exception, match=unknown_field):
            parse_structure_input(payload)


class TestParseStructureInput:
    """Test parsing structure from dict and JSON string."""

    def test_parse_from_dict(self):
        data = {
            "primary_intensity_metric": "percentOfFtp",
            "steps": [
                {"name": "WU", "duration_seconds": 600, "intensity_min": 40, "intensity_max": 55, "intensity_class": "warmUp"},
            ],
        }
        parsed = parse_structure_input(data)
        assert len(parsed.steps) == 1
        assert parsed.primary_intensity_metric == "percentOfFtp"
        assert parsed.steps[0].intensity_class == "warmUp"


    def test_parse_legacy_camel_case_aliases(self):
        data = {
            "primaryIntensityMetric": "percentOfThresholdHr",
            "steps": [
                {
                    "name": "WU",
                    "duration_seconds": 600,
                    "intensity_min": 60,
                    "intensity_max": 70,
                    "intensityClass": "warmUp",
                },
            ],
        }

        parsed = parse_structure_input(data)

        assert parsed.primary_intensity_metric == "percentOfThresholdHr"
        assert parsed.steps[0].intensity_class == "warmUp"

    def test_parse_from_json_string(self):
        data = {
            "steps": [
                {"name": "Main", "duration_seconds": 1200, "intensity_min": 80, "intensity_max": 90, "intensityClass": "active"},
            ],
        }
        parsed = parse_structure_input(json.dumps(data))
        assert len(parsed.steps) == 1

    def test_parse_repetition_block(self):
        data = {
            "steps": [
                {
                    "type": "repetition", "reps": 3,
                    "steps": [
                        {"name": "ON", "duration_seconds": 60, "intensity_min": 95, "intensity_max": 105, "intensityClass": "active"},
                        {"name": "OFF", "duration_seconds": 60, "intensity_min": 50, "intensity_max": 60, "intensityClass": "rest"},
                    ],
                },
            ],
        }
        parsed = parse_structure_input(data)
        assert isinstance(parsed.steps[0], SimpleRepetitionBlock)
        assert parsed.steps[0].reps == 3

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError, match="Invalid JSON"):
            parse_structure_input("{bad json")


class TestTpValidateStructure:
    """Tests for tp_validate_structure tool."""

    @pytest.mark.asyncio
    async def test_valid_structure_returns_summary(self):
        data = json.dumps({
            "primaryIntensityMetric": "percentOfFtp",
            "steps": [
                {"name": "WU", "duration_seconds": 600, "intensity_min": 40, "intensity_max": 55, "intensityClass": "warmUp"},
                {"name": "Main", "duration_seconds": 1200, "intensity_min": 85, "intensity_max": 95, "intensityClass": "active"},
                {"name": "CD", "duration_seconds": 600, "intensity_min": 40, "intensity_max": 55, "intensityClass": "coolDown"},
            ],
        })
        result = await tp_validate_structure(data)

        assert result["valid"] is True
        assert result["block_count"] == 3
        assert result["total_steps"] == 3
        assert result["total_duration_seconds"] == 2400
        assert result["total_duration_minutes"] == 40.0
        assert result["estimated_if"] > 0
        assert result["estimated_tss"] > 0
        assert result["intensity_metric"] == "percentOfFtp"

    @pytest.mark.asyncio
    async def test_invalid_structure_returns_error(self):
        result = await tp_validate_structure("{bad json")

        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_empty_steps_returns_error(self):
        result = await tp_validate_structure(json.dumps({"steps": []}))

        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_misspelled_intensity_class_returns_error(self):
        result = await tp_validate_structure(json.dumps({
            "steps": [
                {
                    "name": "WU",
                    "duration_seconds": 600,
                    "intensity_min": 40,
                    "intensity_max": 55,
                    "intensity_clas": "warmUp",
                },
            ],
        }))

        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"
        assert "intensity_clas" in result["message"]

    @pytest.mark.asyncio
    async def test_non_power_metric_has_no_load_estimate(self):
        result = await tp_validate_structure(json.dumps({
            "primary_intensity_metric": "percentOfThresholdHr",
            "steps": [
                {
                    "name": "Tempo",
                    "duration_seconds": 1800,
                    "intensity_min": 85,
                    "intensity_max": 90,
                },
            ],
        }))

        assert result["valid"] is True
        assert result["total_duration_seconds"] == 1800
        assert result["estimated_if"] is None
        assert result["estimated_tss"] is None
        assert "provide tss_planned explicitly" in result["estimation_warning"]
