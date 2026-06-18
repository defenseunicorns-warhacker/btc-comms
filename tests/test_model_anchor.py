"""
Tests for model weight hashing and deployment anchoring (src/model_anchor.py).
"""

import pytest
from pathlib import Path


@pytest.fixture
def anchor():
    import model_anchor
    return model_anchor


def test_hash_single_file(tmp_path, anchor):
    f = tmp_path / "model.bin"
    f.write_bytes(b"fake weights data")
    result = anchor.hash_model_weights(f)
    assert result.startswith("sha256:")
    assert len(result) == len("sha256:") + 64


def test_hash_file_stable(tmp_path, anchor):
    f = tmp_path / "model.bin"
    f.write_bytes(b"stable weights")
    assert anchor.hash_model_weights(f) == anchor.hash_model_weights(f)


def test_hash_file_changes_with_content(tmp_path, anchor):
    f = tmp_path / "model.bin"
    f.write_bytes(b"version 1")
    h1 = anchor.hash_model_weights(f)
    f.write_bytes(b"version 2")
    h2 = anchor.hash_model_weights(f)
    assert h1 != h2


def test_hash_directory(tmp_path, anchor):
    (tmp_path / "layer0.bin").write_bytes(b"layer 0 weights")
    (tmp_path / "layer1.bin").write_bytes(b"layer 1 weights")
    result = anchor.hash_model_weights(tmp_path)
    assert result.startswith("sha256:")
    assert len(result) == len("sha256:") + 64


def test_hash_directory_stable(tmp_path, anchor):
    (tmp_path / "a.bin").write_bytes(b"weights a")
    (tmp_path / "b.safetensors").write_bytes(b"weights b")
    h1 = anchor.hash_model_weights(tmp_path)
    h2 = anchor.hash_model_weights(tmp_path)
    assert h1 == h2


def test_hash_directory_changes_when_file_changes(tmp_path, anchor):
    f = tmp_path / "model.bin"
    f.write_bytes(b"original")
    h1 = anchor.hash_model_weights(tmp_path)
    f.write_bytes(b"tampered")
    h2 = anchor.hash_model_weights(tmp_path)
    assert h1 != h2


def test_hash_directory_no_weight_files_raises(tmp_path, anchor):
    (tmp_path / "readme.txt").write_text("no weights here")
    with pytest.raises(ValueError, match="No weight files"):
        anchor.hash_model_weights(tmp_path)


def test_hash_missing_path_raises(tmp_path, anchor):
    with pytest.raises(FileNotFoundError):
        anchor.hash_model_weights(tmp_path / "nonexistent.bin")


def test_hash_config_file(tmp_path, anchor):
    cfg = tmp_path / "config.json"
    cfg.write_text('{"model_type": "llama"}')
    result = anchor.hash_config(cfg)
    assert result.startswith("sha256:")


def test_hash_config_directory(tmp_path, anchor):
    (tmp_path / "config.json").write_text('{"vocab_size": 32000}')
    (tmp_path / "tokenizer.json").write_text('{"version": "1.0"}')
    result = anchor.hash_config(tmp_path)
    assert result.startswith("sha256:")


def test_hash_custom_extensions(tmp_path, anchor):
    (tmp_path / "model.myext").write_bytes(b"custom format")
    with pytest.raises(ValueError, match="No weight files"):
        anchor.hash_model_weights(tmp_path)
    # Succeeds with override
    result = anchor.hash_model_weights(tmp_path, include_extensions=(".myext",))
    assert result.startswith("sha256:")


def test_build_deployment_payload_drops_nones(anchor):
    from model_anchor import ModelDeploymentRecord, build_deployment_payload
    record = ModelDeploymentRecord(
        model_id="test-model",
        version="v1.0",
        weights_hash="sha256:" + "a" * 64,
    )
    payload = build_deployment_payload(record)
    assert payload["model_id"] == "test-model"
    assert payload["_schema"] == "model_deployment_v1"
    assert "config_hash" not in payload
    assert "framework" not in payload
    assert "notes" not in payload


def test_build_deployment_payload_includes_optional_fields(anchor):
    from model_anchor import ModelDeploymentRecord, build_deployment_payload
    record = ModelDeploymentRecord(
        model_id="llama-3",
        version="v2.0",
        weights_hash="sha256:" + "b" * 64,
        framework="pytorch",
        parameter_count="70B",
        provenance="meta-llama/Llama-3-70B",
        notes="Production deployment",
    )
    payload = build_deployment_payload(record)
    assert payload["framework"] == "pytorch"
    assert payload["parameter_count"] == "70B"
    assert payload["provenance"] == "meta-llama/Llama-3-70B"
