"""
Model deployment anchoring — hash model weights and record the deployment.

Proves *which model was running* at a given time. An investigator can later
re-hash the weights file(s) and verify against the on-chain record. Combined
with TEE attestation (tee.py), this bridges proof-of-storage (STABLE) toward
proof-of-processing: we prove what was stored AND what code ran.

Usage:
    from model_anchor import hash_model_weights, ModelDeploymentRecord, build_deployment_payload

    weights_hash = hash_model_weights("/models/llama-3-70b/")
    record = ModelDeploymentRecord(
        model_id="llama-3-70b",
        version="v1.2.3",
        weights_hash=weights_hash,
        framework="pytorch",
    )
    client.emit("model_deployment", build_deployment_payload(record))

Or via the recorder API:
    POST /model/register
    {"source_id": "deploy-system", "model_id": "llama-3-70b", "version": "v1.2.3",
     "weights_hash": "sha256:<hex>"}
"""

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

# Weight file extensions recognized by hash_model_weights when scanning a directory.
_WEIGHT_EXTS = (
    ".bin", ".safetensors", ".pt", ".pth", ".gguf", ".ggml", ".ckpt",
)

# Config/tokenizer extensions recognized by hash_config.
_CONFIG_EXTS = (".json", ".yaml", ".yml", ".txt", ".model", ".tiktoken")


@dataclass
class ModelDeploymentRecord:
    """
    A record of a model deployment, anchored in the ledger at deploy time.

    model_id:         Stable identifier (e.g. "llama-3-70b", "gpt-4o-mini").
    version:          Version, commit hash, or release tag.
    weights_hash:     "sha256:<hex>" fingerprint of the weight file(s).
    config_hash:      "sha256:<hex>" of config/tokenizer files (optional but recommended).
    framework:        pytorch | onnx | tflite | gguf | etc.
    parameter_count:  Human-readable size ("70B", "13B") — not verified, informational.
    provenance:       Upstream source URL or package name (Hugging Face ID, etc.).
    notes:            Freeform notes (deployment region, clearance level, etc.).
    """
    model_id: str
    version: str
    weights_hash: str                       # "sha256:<64-hex-chars>"
    config_hash: Optional[str] = None       # "sha256:<64-hex-chars>"
    framework: Optional[str] = None
    parameter_count: Optional[str] = None
    provenance: Optional[str] = None
    notes: Optional[str] = None
    _schema: str = "model_deployment_v1"


def hash_model_weights(
    path: "str | Path",
    *,
    include_extensions: tuple = (),
) -> str:
    """
    Compute a stable SHA-256 fingerprint of model weights at *path*.

    If path is a file:      hash that file directly.
    If path is a directory: hash all weight files (sorted by relative path for
                            reproducibility), producing a single aggregate hash
                            of "<filename>:<file_hash>\\n" lines.

    Returns "sha256:<64-hex-chars>".
    Raises FileNotFoundError if path does not exist.
    Raises ValueError if path is a directory with no recognized weight files.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Model path not found: {path}")

    if p.is_file():
        return "sha256:" + _hash_file(p)

    exts = include_extensions or _WEIGHT_EXTS
    files = sorted(f for f in p.rglob("*") if f.is_file() and f.suffix in exts)
    if not files:
        raise ValueError(
            f"No weight files found in {path}. "
            f"Recognized extensions: {exts}. "
            "Pass include_extensions=('.myext',) to override."
        )

    agg = hashlib.sha256()
    for f in files:
        entry = f"{f.relative_to(p)}:{_hash_file(f)}\n"
        agg.update(entry.encode())
    return "sha256:" + agg.hexdigest()


def hash_config(path: "str | Path") -> str:
    """
    Hash model config and tokenizer files alongside weights for a complete
    deployment fingerprint.

    If path is a file: hash it directly.
    If path is a directory: hash all config files (sorted) into one aggregate hash.
    Returns "sha256:<64-hex-chars>".
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config path not found: {path}")

    if p.is_file():
        return "sha256:" + _hash_file(p)

    files = sorted(f for f in p.rglob("*") if f.is_file() and f.suffix in _CONFIG_EXTS)
    if not files:
        raise ValueError(f"No config files found in {path}. Recognized extensions: {_CONFIG_EXTS}")

    agg = hashlib.sha256()
    for f in files:
        entry = f"{f.relative_to(p)}:{_hash_file(f)}\n"
        agg.update(entry.encode())
    return "sha256:" + agg.hexdigest()


def build_deployment_payload(record: ModelDeploymentRecord) -> dict:
    """Serialize a ModelDeploymentRecord to a ledger payload dict, dropping None fields."""
    return {k: v for k, v in asdict(record).items() if v is not None}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _hash_file(path: Path) -> str:
    """SHA-256 of a file, streaming in 1 MiB chunks to handle large weight files."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
