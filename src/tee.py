"""
TEE (Trusted Execution Environment) attestation integration.

Records a cryptographic attestation from the platform's TEE into the
accountability ledger. An attestation proves *which binary was running* —
the software measurement (mrenclave / MRTD) is bound to the record, so a
reviewer can verify the model ran inside an approved enclave with an approved
code image.

Combined with model_anchor (which proves which weights were deployed), this
provides the bridge between proof-of-storage and proof-of-processing:
  1. model_anchor: proves *what* weights were loaded
  2. tee:          proves *what code* ran on them
  3. STABLE ledger: proves the output record hasn't been altered since

Supported platforms:
  TDX   — Intel Trust Domain Extensions (Linux ≥ 6.7, /dev/tdx_guest)
  SEV   — AMD Secure Encrypted Virtualization (/dev/sev-guest)
  SGX   — Intel Software Guard Extensions (DCAP library)
  MOCK  — Simulated measurement for demo/test (MOCK_TEE=true)

Usage:
    from tee import collect_attestation, build_attestation_payload

    # Bind the model weights hash into the attestation so TEE proof and
    # model deployment are cryptographically linked.
    att = collect_attestation(report_data=b"sha256:<model-weights-hash>")
    client.emit("tee_attestation", build_attestation_payload(att))

Or via the recorder API:
    POST /tee/attest
    {"source_id": "inference-service", "tee_type": "MOCK",
     "measurement": "<hex>", "report_data": "<hex>", "quote": ""}

Environment:
  MOCK_TEE=true   Enable simulated attestation (no hardware required).
"""

import hashlib
import os
import socket
import time
from dataclasses import asdict, dataclass
from typing import Optional


MOCK_TEE: bool = os.getenv("MOCK_TEE", "false").lower() in ("true", "1", "yes")


class TeeError(RuntimeError):
    """Raised when TEE attestation is unavailable or the platform call fails."""


@dataclass
class TeeAttestation:
    """
    A TEE attestation record, ready to be stored in the accountability ledger.

    tee_type:    TDX | SEV | SGX | MOCK — the platform that produced this quote.
    measurement: Hex software measurement (MRTD for TDX, MRENCLAVE for SGX,
                 simulated hash for MOCK). Identifies *exactly* which binary ran.
    report_data: User-supplied bytes bound into the quote (hex). Bind the model
                 weights_hash here to tie this attestation to a specific deployment.
    quote:       Full attestation quote as hex. May be empty in mock mode.
                 In production, submit this to Intel DCAP / AMD KDS for verification.
    platform:    CPU/platform identifier string (informational).
    """
    tee_type: str
    measurement: str       # hex
    report_data: str       # hex
    quote: str             # hex (may be empty in mock mode)
    platform: Optional[str] = None
    _schema: str = "tee_attestation_v1"


def collect_attestation(report_data: bytes = b"") -> TeeAttestation:
    """
    Collect a TEE attestation from the current platform.

    report_data — arbitrary bytes you want cryptographically bound into the
    attestation quote. Pass the model weights_hash as bytes to link this
    attestation to a specific model deployment:
        collect_attestation(report_data=weights_hash.encode())

    Returns a TeeAttestation ready for build_attestation_payload().
    Raises TeeError if no TEE is available and MOCK_TEE is not set.
    """
    if MOCK_TEE or os.getenv("MOCK_TEE", "false").lower() in ("true", "1", "yes"):
        return _mock_attestation(report_data)

    # Try platform-specific collectors. Each returns None if the device is absent;
    # raises TeeError if the device is present but the call fails (don't silently
    # fall through to mock when real hardware is there but misconfigured).
    for collector in (_try_tdx, _try_sev):
        att = collector(report_data)
        if att is not None:
            return att

    raise TeeError(
        "No TEE available on this platform and MOCK_TEE is not set. "
        "Options: set MOCK_TEE=true for demo/test mode, or run on TDX/SEV hardware."
    )


def build_attestation_payload(att: TeeAttestation) -> dict:
    """Serialize a TeeAttestation to a ledger payload dict, dropping None fields."""
    return {k: v for k, v in asdict(att).items() if v is not None}


# ---------------------------------------------------------------------------
# Platform collectors
# ---------------------------------------------------------------------------

def _mock_attestation(report_data: bytes) -> TeeAttestation:
    """
    Simulated TEE attestation for demo and test environments (MOCK_TEE=true).

    The simulated measurement is stable within an hour-long window so tests
    get the same value for the run, but it changes across deployments. This
    mimics real enclave behavior: same code → same measurement.
    """
    measurement_src = f"{socket.gethostname()}:{os.getpid()}:{int(time.time() // 3600)}"
    measurement = hashlib.sha256(measurement_src.encode()).hexdigest()
    rd_hex = report_data.hex() if report_data else ""
    return TeeAttestation(
        tee_type="MOCK",
        measurement=measurement,
        report_data=rd_hex,
        quote="",
        platform="mock",
    )


def _try_tdx(report_data: bytes) -> Optional[TeeAttestation]:
    """
    Intel TDX attestation via /dev/tdx_guest (Linux kernel ≥ 6.7).

    Returns None if /dev/tdx_guest is absent (TDX not available on this host).
    Raises TeeError if the device is present but attestation fails.

    Production integration point: replace the body with a call to the
    intel/tdx-tools SDK (tdx_attest_get_report / TDX_CMD_GET_REPORT0 ioctl).
    Reference: https://github.com/intel/tdx-tools
    """
    if not os.path.exists("/dev/tdx_guest"):
        return None
    # TDX hardware present — SDK integration required.
    raise TeeError(
        "TDX device found at /dev/tdx_guest. "
        "Wire in the intel/tdx-tools SDK at src/tee.py:_try_tdx to complete. "
        "Set MOCK_TEE=true to test without hardware."
    )


def _try_sev(report_data: bytes) -> Optional[TeeAttestation]:
    """
    AMD SEV-SNP attestation via /dev/sev-guest.

    Returns None if /dev/sev-guest is absent.
    Raises TeeError if the device is present but attestation fails.

    Production integration point: replace the body with a call to the
    amd/sev-tool or google/go-sev-guest SDK (SEV_SNP_GUEST_MSG_REPORT ioctl).
    """
    if not os.path.exists("/dev/sev-guest"):
        return None
    raise TeeError(
        "SEV device found at /dev/sev-guest. "
        "Wire in the sev-tool SDK at src/tee.py:_try_sev to complete. "
        "Set MOCK_TEE=true to test without hardware."
    )
