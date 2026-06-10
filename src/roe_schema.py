"""
Rules of Engagement (ROE) structured event schema.

Defines the mandatory fields for AI decision events that must be
legally interpretable by JAG officers and DCSA investigators.
Plain JSON payloads are still accepted for non-ROE events.

The schema captures:
  - WHAT was decided (decision_type, recommended_action)
  - WHO authorized it (human_authorized, operator_id)
  - WHY (information_state — what the AI saw at decision time)
  - WHEN (latency from detection to authorization)
  - WHERE (geo_location)
  - WHICH rule applied (roe_reference)
  - CONFIDENCE (ai_confidence — for accountability of autonomous assessments)

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
    A structured record of an AI-assisted or autonomous decision at a
    Rules of Engagement gate. All fields are mandatory for JAG compliance.

    decision_type:           What kind of gate this is.
    human_authorized:        Was a human in the decision loop?
    operator_id:             Identifier of the authorizing human (CAC in production).
    target_id:               Identifier of the object/entity being acted upon.
    ai_confidence:           AI's reported confidence (0–1) at decision time.
    roe_reference:           The specific ROE rule invoked.
    information_state:       Snapshot of sensor/intelligence data available to the AI.
    time_to_authorization_ms: Latency from first detection to authorization decision.
    geo_location:            {lat, lon, alt_m} of the event.
    weapon_system_id:        Which system would execute the action.
    recommended_action:      What the AI recommended.
    final_action:            What was actually authorized/executed.
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
    Follow-up record after an engagement completes — closes the accountability loop.
    Link back to the RoEDecision via decision_seq.
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
