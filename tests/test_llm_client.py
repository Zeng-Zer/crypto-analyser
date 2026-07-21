import pytest

from crypto_analyser.llm_client import ClassificationResult


def _result(**overrides):
    data = {
        "event_reference": "LUNAUSDT_123",
        "classification": "unexplained",
        "confidence": 0.8,
        "synthesis": {"reasons": ["No explanation."], "supporting_refs": []},
        "rationale": "Detailed rationale.",
    }
    data.update(overrides)
    return data


@pytest.mark.parametrize(
    "payload",
    [
        _result(unexpected=True),
        _result(
            synthesis={
                "reasons": ["No explanation."],
                "supporting_refs": [],
                "unexpected": True,
            }
        ),
    ],
)
def test_classification_result_rejects_unexpected_properties(payload):
    with pytest.raises(ValueError, match="unexpected fields"):
        ClassificationResult.from_dict(payload)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"event_reference": "LUNAUSDT_123"},
        _result(synthesis={"reasons": ["No explanation."]}),
    ],
)
def test_classification_result_rejects_invalid_object_shape(payload):
    with pytest.raises(ValueError, match="classification must be an object|missing fields"):
        ClassificationResult.from_dict(payload)


def test_classification_result_rejects_unknown_verdict():
    with pytest.raises(ValueError, match="classification must be one of"):
        ClassificationResult.from_dict(_result(classification="not_a_verdict"))


@pytest.mark.parametrize("confidence", [-0.1, 1.1, float("nan"), float("inf"), "0.8", True])
def test_classification_result_rejects_invalid_confidence(confidence):
    with pytest.raises(ValueError, match="confidence must"):
        ClassificationResult.from_dict(_result(confidence=confidence))


def test_classification_result_rejects_mismatched_event_reference():
    with pytest.raises(ValueError, match="event_reference does not match"):
        ClassificationResult.from_dict(_result(), "LUNAUSDT_456")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("event_reference", 123, "event_reference must"),
        ("classification", [], "classification must"),
        ("rationale", None, "rationale must"),
        ("synthesis", [], "synthesis must"),
    ],
)
def test_classification_result_rejects_wrong_scalar_types(field, value, message):
    with pytest.raises(ValueError, match=message):
        ClassificationResult.from_dict(_result(**{field: value}))
