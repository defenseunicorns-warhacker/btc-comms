# STABLE as a UDS Capability

STABLE is not just an application — it's a **shared accountability capability**
any app on a UDS cluster can opt into, the way a workload attaches a logging
sidecar or reaches a secrets service. Deploy one recorder; every AI-enabled app
on the cluster gets an immutable, signed, Bitcoin-anchorable record for free.

> The vision: an app developer adds two lines, points at the cluster's STABLE
> service, and every decision their agent makes is now tamper-evident and
> attributable — without them implementing any crypto.

---

## The model: one recorder, many audited apps

```
   ┌──────────────┐
   │   app A pod  │──┐
   └──────────────┘  │      ┌──────────────────────────────────────┐
   ┌──────────────┐  │      │  STABLE recorder  (namespace: stable) │
   │   app B pod  │──┼─────▶│  • separate trust domain              │──▶ Bitcoin
   └──────────────┘  │      │  • write-only ingest API              │   (OpenTimestamps,
   ┌──────────────┐  │      │  • one immutable, signed, anchored    │    public + free)
   │   app C pod  │──┘      │    ledger for the whole cluster       │
   └──────────────┘         └──────────────────────────────────────┘
```

Three properties make this a *capability*, not a library:

1. **Separate trust domain.** The recorder runs in its own namespace
   (`stable`), with its own storage (PVC) the audited apps cannot reach. Apps get
   a write-only HTTP API — no modify or delete path. An app (or a compromised
   agent inside it) cannot rewrite what it already recorded. This is the whole
   point, and it only holds because the recorder is *not* in the app's trust
   domain. See [ARCHITECTURE.md → Trust model](ARCHITECTURE.md#trust-model-read-this-first).
2. **One ledger, cluster-wide.** Every app writes to the same hash-chained,
   Bitcoin-anchored record. Cross-app provenance ("agent A's decision fed agent
   B's action") lives in one verifiable timeline, not scattered per-service logs.
3. **Zero crypto for the consumer.** The hash chain, MMR proofs, Ed25519 signing,
   DDIL buffering, and Bitcoin anchoring all live in the recorder and the thin
   adapter. The app developer never touches any of it.

---

## How an app adopts it

The recorder is a `ClusterIP` Service ([k8s/service.yaml](../k8s/service.yaml)),
reachable from any pod at:

```
http://stable.stable.svc.cluster.local:8000
```

Then use one of the three integration patterns
([ARCHITECTURE.md → Integration](ARCHITECTURE.md#integration--wiring-into-an-existing-system)):

**Python service — two lines:**
```python
import logging
from adapters import LedgerLogHandler
logging.getLogger().addHandler(
    LedgerLogHandler("app-a", "http://stable.stable.svc.cluster.local:8000"))
```

**Any agent — explicit client (DDIL-buffered, signed):**
```python
from adapters import LedgerClient
client = LedgerClient("http://stable.stable.svc.cluster.local:8000", source_id="app-a")
client.emit("decision", {"action": "HOLD", "confidence": 0.71})
```

**Anything else — one curl:**
```bash
curl -X POST http://stable.stable.svc.cluster.local:8000/events \
     -H 'Content-Type: application/json' \
     -d '{"source_id":"app-a","payload":{"action":"HOLD"}}'
```

Most apps just set `LEDGER_URL` to the service address as an env var — every
example agent in [examples/](../examples/) already honors it. A ready-to-apply
illustration is in [k8s/example-consumer.yaml](../k8s/example-consumer.yaml).

---

## Enrollment is the trust anchor

The hardened recorder runs with `STRICT_SIGNING=true`
([k8s/deployment.yaml](../k8s/deployment.yaml)): it rejects any event whose
signature isn't from a key whose **registered `source_id` matches the claimed
sender**. So adopting the shared recorder has exactly one prerequisite beyond
pointing at the URL: the app's signing key must be **enrolled** with the recorder.

- **Demo / trusted cluster:** keys self-enroll on first use (TOFU). Point at the
  URL and go.
- **Production:** enrollment is gated by a provisioning authority (CAC/PIV, an
  enrollment CA, or HSM attestation) so an attacker can't pre-register a victim's
  `source_id`. The signing/verification path is identical — only key issuance
  hardens. See [ARCHITECTURE.md → Residual trust assumption](ARCHITECTURE.md#trust-model-read-this-first).

This is the right place for the trust boundary: *who is allowed to write as
identity X* is a provisioning decision, decoupled from the tamper-evidence
machinery.

---

## Packaging: ship it as a bundle, depend on it as a service

STABLE already ships as a UDS bundle / Zarf package
([uds-bundle.yaml](../uds-bundle.yaml), [zarf.yaml](../zarf.yaml)) that deploys
the recorder, its Service, storage, and a random `API_TOKEN` Secret into an
air-gapped cluster — hardened by default. See
[DEPLOYMENT.md](DEPLOYMENT.md#air-gapped-deployment-uds--zarf).

Because the recorder is a standalone, namespaced service with a stable in-cluster
address, **other UDS packages compose with it** rather than embedding it:

- Deploy the STABLE bundle once per cluster (or per enclave).
- Each consuming package sets `LEDGER_URL` to `stable.stable.svc.cluster.local:8000`
  and adds the adapter — no STABLE code is vendored into the app.
- Upgrade, replicate, or harden the recorder independently of the apps it audits.

The result: **tamper-evidence becomes ambient cluster infrastructure.** Any
AI-enabled mission app gets a defensible, DoDD-3000.09-aligned audit trail by
adoption, not by reimplementation.

---

## The pitch framing (one line for the deck)

> "STABLE isn't another app to maintain — it's a platform capability for the
> whole UDS ecosystem. Deploy one recorder; every AI app on the cluster gets an
> immutable, signed, Bitcoin-anchored record in two lines. Accountability becomes
> something the platform provides, not something each program has to rebuild."
