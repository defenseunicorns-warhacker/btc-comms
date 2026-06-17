# Deployment & Operations

How to run STABLE locally, in a container, and into a disconnected
Kubernetes cluster — plus tests and hardening. For configuration variables see
[ARCHITECTURE.md → Configuration](ARCHITECTURE.md#configuration).

---

## Run locally

```bash
pip install -r requirements.txt

# Local demo (mock Bitcoin confirmation, tamper/seed endpoints enabled).
# Use `python3 -m uvicorn` so it works even when the uvicorn script isn't on PATH.
DEMO_MODE=true MOCK_ANCHOR=true python3 -m uvicorn src.api:app --reload

open http://localhost:8000
```

Hardened (production-shaped) run:

```bash
STRICT_SIGNING=true API_TOKEN=$(openssl rand -hex 32) \
  python3 -m uvicorn src.api:app
```

With `STRICT_SIGNING=true`, every event must carry a signature from a key whose
registered `source_id` matches the claimed sender. With `API_TOKEN` set, mutating
endpoints require `Authorization: Bearer <token>` or `X-API-Key: <token>`.

---

## Docker

```bash
docker compose up --build   # --build avoids running a stale cached image
```

---

## Running tests

```bash
python3 -m pytest tests/ -v
```

228+ tests across 11 files:

- **Hash chain** — tamper detection at every entry, sequence gaps, broken links
- **MMR** — append, inclusion proofs for all sizes/positions, root recompute, tamper
- **Signing** — sign/verify roundtrip, payload tamper, unknown key, and
  **impersonation rejection** (a key enrolled to one identity cannot sign as another)
- **Ledger store** — genesis, chain links, MMR persistence across reopen, logarithmic node growth
- **API (end-to-end)** — seed→verify, tamper→verify-fails, MMR proof endpoint,
  strict-signing enforcement, token auth, impersonation rejection at ingest
- **DDIL** — local buffering during outage, ordered flush on reconnect, signatures survive buffering
- **Domain schema (ROE example)** — structured-payload field validation, `human_authorized=false` autonomous records

---

## Air-gapped deployment (UDS / Zarf)

STABLE ships as a [UDS](https://github.com/defenseunicorns/uds-cli) bundle /
[Zarf](https://zarf.dev) package — the image and a software bill of materials
(SBOM) are bundled into a single tarball that deploys into a **fully
disconnected Kubernetes cluster** with no internet access.

```bash
# 1. Build the container image
docker build -t stable:latest .

# 2. Build the air-gap package (image + manifests + SBOM, one tarball)
uds zarf package create . --confirm
#   → zarf-package-stable-<arch>-0.1.0.tar.zst

# 3. On the air-gapped cluster: initialize Zarf, then deploy
uds zarf init --confirm
uds zarf package deploy zarf-package-stable-*.tar.zst --confirm
```

The deploy runs **hardened by default** (`STRICT_SIGNING=true`, a random
`API_TOKEN` Secret, non-root read-only container, health probes). Manifests live
in [k8s/](../k8s/); package definitions are [zarf.yaml](../zarf.yaml) and
[uds-bundle.yaml](../uds-bundle.yaml).

> **Why this matters:** local tamper-evidence needs no network at all, so STABLE
> is fully functional air-gapped. When a link is available — even intermittently —
> anchors batch-submit to Bitcoin and confirm. Nothing about the guarantee
> depends on continuous connectivity.

---

## STABLE as a shared UDS capability

STABLE is not just an application — it's a **shared accountability capability**
any app on a UDS cluster can opt into, the way a workload attaches a logging
sidecar or reaches a secrets service. Deploy one recorder; every AI-enabled app
on the cluster gets an immutable, signed, Bitcoin-anchorable record in two lines.

```
   ┌──────────────┐
   │   app A pod  │──┐
   └──────────────┘  │      ┌───────────────────────────────────────┐
   ┌──────────────┐  │      │  STABLE recorder  (namespace: stable) │
   │   app B pod  │──┼─────▶│  • separate trust domain              │──▶ Bitcoin
   └──────────────┘  │      │  • write-only ingest API              │
   ┌──────────────┐  │      │  • one immutable ledger for the whole │
   │   app C pod  │──┘      │    cluster                            │
   └──────────────┘         └───────────────────────────────────────┘
```

Three properties make this a *capability*, not a library:

1. **Separate trust domain.** The recorder runs in its own namespace (`stable`)
   with its own storage the audited apps cannot reach. Apps get a write-only HTTP
   API — no modify or delete path. An app (or a compromised agent inside it)
   cannot rewrite what it already recorded.
2. **One ledger, cluster-wide.** Every app writes to the same hash-chained,
   Bitcoin-anchored record. Cross-app provenance lives in one verifiable timeline,
   not scattered per-service logs.
3. **Zero crypto for the consumer.** The hash chain, MMR proofs, Ed25519 signing,
   DDIL buffering, and Bitcoin anchoring all live in the recorder and the thin
   adapter. The app developer never touches any of it.

The recorder is a `ClusterIP` Service reachable from any pod at
`http://stable.stable.svc.cluster.local:8000`. Adopt it with one of three patterns
([ARCHITECTURE.md → Integration](ARCHITECTURE.md#integration--wiring-into-an-existing-system)):

```python
# Two lines for any Python service using standard logging:
from adapters import LedgerLogHandler
logging.getLogger().addHandler(
    LedgerLogHandler("app-a", "http://stable.stable.svc.cluster.local:8000"))
```

```python
# Or explicit client (DDIL-buffered, signed):
from adapters import LedgerClient
client = LedgerClient("http://stable.stable.svc.cluster.local:8000", source_id="app-a")
client.emit("decision", {"action": "HOLD", "confidence": 0.71})
```

A ready-to-apply consumer example is in
[k8s/example-consumer.yaml](../k8s/example-consumer.yaml).

**Enrollment.** The hardened recorder runs with `STRICT_SIGNING=true`: it rejects
any event whose signature isn't from a key whose registered `source_id` matches
the claimed sender. In demo mode keys self-enroll on first use. In production,
enrollment is gated by a provisioning authority (CAC/PIV, enrollment CA, or HSM)
— the signing path is identical, only key issuance hardens. See
[ARCHITECTURE.md → Trust model](ARCHITECTURE.md#trust-model-read-this-first).
