import json
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError

from apps.access.normalization import NormalizationError, apply_normalization, validate_steps

CASES = (
    Path(__file__).resolve().parents[4] / "docs" / "reader-profiles" / "normalization-cases.json"
)


def test_shared_normalization_cases():
    cases = json.loads(CASES.read_text())
    assert cases
    for case in cases:
        steps = case["steps"]
        validate_steps(steps)
        if case.get("error"):
            with pytest.raises(NormalizationError):
                apply_normalization(
                    case["sample"],
                    steps,
                    min_length=case.get("min_length"),
                    max_length=case.get("max_length"),
                )
            continue
        assert (
            apply_normalization(
                case["sample"],
                steps,
                min_length=case.get("min_length"),
                max_length=case.get("max_length"),
            )
            == case["expected"]
        )


def test_unknown_operation_is_rejected():
    with pytest.raises(ValidationError):
        validate_steps([{"op": "reverse"}])


def test_invalid_regex_is_rejected():
    with pytest.raises(ValidationError):
        validate_steps([{"op": "regex_extract", "pattern": "[unterminated"}])
