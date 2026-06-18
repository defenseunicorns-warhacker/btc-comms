"""
EXAMPLE DOMAIN SCHEMA — Rules of Engagement (ROE) structured event payload.

This is NOT a core system requirement. It is one example of how teams can
define structured, typed payloads on top of STABLE's domain-agnostic ledger.
The core system accepts any JSON payload; this schema adds field enforcement
for a specific defense use case.

----

For high-stakes AI decisions — particularly in defense contexts — free-form log
lines are insufficient. This schema shows how to structure event payloads so
that a domain expert (e.g. a JAG officer or investigator) can interpret a record
without engineering support.

Adapt this pattern for your own domain:
  - Swap "decision_type/roe_reference/weapon_system_id" for your domain's fields
  - Keep "human_authorized, operator_id, ai_confidence, information_state" — they
    are domain-agnostic accountability fields that apply to any supervised AI
  - The _schema tag (e.g. "roe_decision_v1") is what validate_roe_payload() uses
    to identify records that should be checked; plain payloads pass through untouched

The schema captures:
  - WHAT was decided (decision_type, recommended_action)
  - WHO authorized it (human_authorized, operator_id)
  - WHY (information_state — what the AI saw at decision time)
  - WHEN (latency from detection to authorization)
  - WHERE (geo_location)
  - WHICH rule applied (roe_reference)
  - CONFIDENCE (ai_confidence — the AI's own certainty, on record)

Usage:
    from roe_schema import RoEDecision, build_roe_payload

    event = RoEDecision(
        decision_type="ENGAGE_READY",
        human_authorized=True,
        operator_id="OP-441",
        target_id="T-0091",
        ai_confidence=0.94,
        roe_reference="ROE-ALPHA-7",
        information_state={"threat_class": "UAS", "bearing": 142, "range_m": 800},
        time_to_authorization_ms=4200,
        geo_location={"lat": 34.05, "lon": -118.24, "alt_m": 120},
        weapon_system_id="WPN-03",
        recommended_action="HOLD_FIRE",
        final_action="HOLD_FIRE",
    )
    payload = build_roe_payload(event)
    client.emit("roe_decision", payload)
"""

from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class RoEDecision:
    """
    Example structured payload for a defense ROE decision event.

    This is an example domain schema — replace these fields with whatever
    your domain requires. The fields that transfer to any supervised AI use case:
      human_authorized, operator_id, ai_confidence, information_state,
      time_to_authorization_ms, recommended_action, final_action.

    Defense-specific fields (substitute your own):
      decision_type, roe_reference, target_id, geo_location, weapon_system_id.
    """
    decision_type: str             # ENGAGE_READY | HOLD_FIRE | ABORT | DESIGNATE_TARGET | TRACK_ONLY
    human_authorized: bool
    operator_id: str               # "UNATTENDED" if fully autonomous
    target_id: str
    ai_confidence: float           # 0.0–1.0
    roe_reference: str             # e.g. "ROE-ALPHA-7"
    information_state: dict        # sensor snapshot at decision time
    time_to_authorization_ms: int
    geo_location: dict             # {lat, lon, alt_m}
    weapon_system_id: str
    recommended_action: str
    final_action: str
    # Optional enrichment
    sensor_ids: list[str] = field(default_factory=list)
    collateral_damage_estimate: Optional[str] = None   # LOW | MEDIUM | HIGH | UNKNOWN
    legal_review_id: Optional[str] = None              # JAG pre-authorization reference
    notes: Optional[str] = None


@dataclass
class RoEEngagementResult:
    """
    Example follow-up record after an engagement completes.
    Closes the accountability loop back to the originating RoEDecision.
    """
    decision_seq: int       # seq of the originating RoEDecision entry
    target_id: str
    outcome: str            # NEUTRALIZED | MISSED | ABORTED | DAMAGE_ASSESSMENT_PENDING
    bda_confidence: float   # Battle Damage Assessment confidence
    collateral_confirmed: bool
    duration_ms: int
    operator_id: str
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_roe_payload(decision: RoEDecision) -> dict:
    """
    Serialize a RoEDecision to the payload dict expected by the ledger API.
    Adds a schema version tag for forward compatibility.
    """
    d = asdict(decision)
    d["_schema"] = "roe_decision_v1"
    d["_required_fields_present"] = _validate(decision)
    return d


def build_result_payload(result: RoEEngagementResult) -> dict:
    d = asdict(result)
    d["_schema"] = "roe_result_v1"
    return d


def validate_roe_payload(payload: dict) -> tuple[bool, list[str]]:
    """
    Check a raw payload dict for ROE compliance.
    Returns (is_valid, list_of_missing_fields).
    """
    if payload.get("_schema") not in ("roe_decision_v1", "roe_result_v1"):
        return True, []   # not an ROE event — no schema required

    required = [
        "decision_type", "human_authorized", "operator_id", "target_id",
        "ai_confidence", "roe_reference", "information_state",
        "time_to_authorization_ms", "geo_location", "weapon_system_id",
        "recommended_action", "final_action",
    ]
    missing = [f for f in required if f not in payload or payload[f] is None]
    return len(missing) == 0, missing


def _validate(decision: RoEDecision) -> bool:
    ok, _ = validate_roe_payload(asdict(decision))
    return ok
