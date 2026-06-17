"""
Tests for InferenceLogger — deterministic inference recording (src/adapters/inference_logger.py).
"""

import sys
import os
from pathlib import Path

import pytest

# Ensure src/ is on the path so inference_logger can import from adapters/
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class _FakeClient:
    """Minimal LedgerClient stand-in that captures emitted payloads."""
    def __init__(self):
        self.emitted: list[tuple[str, dict]] = []

    def emit(self, event_type: str, payload: dict):
        self.emitted.append((event_type, payload))


@pytest.fixture
def client():
    return _FakeClient()


@pytest.fixture
def logger(client):
    from adapters.inference_logger import InferenceLogger
    return InferenceLogger(client, model_id="test-model", model_version="v1.0",
                           hash_inputs=True, hash_outputs=False)


def test_record_emits_event(logger, client):
    logger.record(inputs={"prompt": "hello"}, output="world")
    assert len(client.emitted) == 1
    event_type, payload = client.emitted[0]
    assert event_type == "inference_record"
    assert payload["_schema"] == "inference_record_v1"


def test_record_model_fields(logger, client):
    logger.record(inputs={"x": 1}, output="y")
    _, payload = client.emitted[0]
    assert payload["model_id"] == "test-model"
    assert payload["model_version"] == "v1.0"


def test_record_hash_inputs_true(logger, client):
    logger.record(inputs={"prompt": "hello"}, output="world")
    _, payload = client.emitted[0]
    assert "input_hash" in payload
    assert payload["input_hash"].startswith("sha256:")
    assert "inputs" not in payload


def test_record_hash_inputs_false(client):
    from adapters.inference_logger import InferenceLogger
    logger = InferenceLogger(client, model_id="m", hash_inputs=False)
    logger.record(inputs={"x": 1}, output="y")
    _, payload = client.emitted[0]
    assert "inputs" in payload
    assert "input_hash" not in payload


def test_record_output_raw_by_default(logger, client):
    logger.record(inputs={"x": 1}, output={"label": "cat", "score": 0.9})
    _, payload = client.emitted[0]
    assert "output" in payload
    assert "output_hash" not in payload


def test_record_hash_outputs(client):
    from adapters.inference_logger import InferenceLogger
    logger = InferenceLogger(client, model_id="m", hash_outputs=True)
    logger.record(inputs=None, output="secret result")
    _, payload = client.emitted[0]
    assert "output_hash" in payload
    assert payload["output_hash"].startswith("sha256:")


def test_record_latency_ms(logger, client):
    logger.record(inputs=None, output=None, latency_ms=42.5)
    _, payload = client.emitted[0]
    assert payload["latency_ms"] == 42.5


def test_record_metadata(logger, client):
    logger.record(inputs=None, output=None, metadata={"roe_seq": 7})
    _, payload = client.emitted[0]
    assert payload["metadata"] == {"roe_seq": 7}


def test_inference_seq_increments(logger, client):
    logger.record(inputs=None, output=None)
    logger.record(inputs=None, output=None)
    logger.record(inputs=None, output=None)
    seqs = [p["inference_seq"] for _, p in client.emitted]
    assert seqs == [1, 2, 3]


def test_record_no_inputs_no_output_minimal_payload(logger, client):
    logger.record()
    _, payload = client.emitted[0]
    assert "input_hash" not in payload
    assert "inputs" not in payload
    assert "output" not in payload


def test_decorator_logs_on_success(client):
    from adapters.inference_logger import InferenceLogger
    logger = InferenceLogger(client, model_id="m", hash_inputs=False, hash_outputs=False)

    @logger.log
    def classify(x):
        return x * 2

    result = classify(5)
    assert result == 10
    assert len(client.emitted) == 1
    event_type, payload = client.emitted[0]
    assert event_type == "inference_record"
    assert payload["status"] == "ok"
    assert payload["_schema"] == "inference_record_v1"


def test_decorator_records_function_name(client):
    from adapters.inference_logger import InferenceLogger
    logger = InferenceLogger(client, model_id="m")

    @logger.log
    def my_inference_fn(x):
        return x

    my_inference_fn(1)
    _, payload = client.emitted[0]
    assert "my_inference_fn" in payload["function"]


def test_decorator_records_latency(client):
    from adapters.inference_logger import InferenceLogger
    logger = InferenceLogger(client, model_id="m")

    @logger.log
    def fast_fn():
        return "ok"

    fast_fn()
    _, payload = client.emitted[0]
    assert "latency_ms" in payload
    assert payload["latency_ms"] >= 0


def test_decorator_logs_on_exception(client):
    from adapters.inference_logger import InferenceLogger
    logger = InferenceLogger(client, model_id="m")

    @logger.log
    def bad_fn():
        raise ValueError("inference exploded")

    with pytest.raises(ValueError, match="inference exploded"):
        bad_fn()

    assert len(client.emitted) == 1
    _, payload = client.emitted[0]
    assert payload["status"] == "error"
    assert payload["exception_type"] == "ValueError"
    assert "inference exploded" in payload["exception_msg"]


def test_decorator_reraises_exception(client):
    from adapters.inference_logger import InferenceLogger
    logger = InferenceLogger(client, model_id="m")

    @logger.log
    def exploding():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        exploding()


def test_decorator_include_inputs_false(client):
    from adapters.inference_logger import InferenceLogger
    logger = InferenceLogger(client, model_id="m", hash_inputs=False)

    @logger.log(include_inputs=False)
    def sensitive(secret_data):
        return "classified"

    sensitive("top-secret")
    _, payload = client.emitted[0]
    assert "inputs" not in payload
    assert "input_hash" not in payload


def test_hash_value_stable():
    from adapters.inference_logger import _hash_value
    h1 = _hash_value({"prompt": "hello", "temp": 0.7})
    h2 = _hash_value({"temp": 0.7, "prompt": "hello"})  # different key order
    assert h1 == h2   # sort_keys=True ensures stability


def test_hash_value_changes_with_content():
    from adapters.inference_logger import _hash_value
    assert _hash_value("input a") != _hash_value("input b")
