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

160+ tests across 8 files:

- **Hash chain** — tamper detection at every entry, sequence gaps, broken links
- **MMR** — append, inclusion proofs for all sizes/positions, root recompute, tamper
- **Signing** — sign/verify roundtrip, payload tamper, unknown key, and
  **impersonation rejection** (a key enrolled to one identity cannot sign as another)
- **Ledger store** — genesis, chain links, MMR persistence across reopen, logarithmic node growth
- **API (end-to-end)** — seed→verify, tamper→verify-fails, MMR proof endpoint,
  strict-signing enforcement, token auth, impersonation rejection at ingest
- **DDIL** — local buffering during outage, ordered flush on reconnect, signatures survive buffering
- **ROE schema** — required-field validation, autonomous (`human_authorized=false`) records

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

The recorder runs in its own trust domain; any app on the cluster opts in with
two lines of adapter code pointed at the in-cluster Service
(`stable.stable.svc.cluster.local:8000`). That makes STABLE less an application
and more a **platform capability** — a tamper-evident ledger every UDS package
can write to, the way they'd attach a logging sidecar. One recorder, many audited
apps, one immutable record.

A ready-to-apply consumer example is in
[k8s/example-consumer.yaml](../k8s/example-consumer.yaml). The full vision,
architecture, adoption pattern, and enrollment model are in
**[UDS_CAPABILITY.md](UDS_CAPABILITY.md)**.
