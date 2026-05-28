"""Phase 5b — priority scoring.

    priority = condition × criticality      (each in [0,1])

Every factor is exposed in the breakdown with its inputs, so an auditor can see
*why* a bridge ranks where it does. Weights/rates live in domain/mappings.py.

Operates on a BridgeExtraction (pruefungen + schaeden + structure/traffic fields).
The denormalized 'aktuelle' fields don't exist yet at this stage, so we derive
the current condition from the latest pruefung and worst damage directly.
"""
import numpy as np

from backend.domain import mappings as M
from backend.extraction.schemas import BridgeExtraction

# Small floor so a single zero factor doesn't annihilate the whole score —
# the product still reflects relative differences across bridges.
_FLOOR = 0.05


def _latest_grade(bridge: BridgeExtraction) -> float | None:
    """Zustandsnote of the most recent inspection that has one."""
    dated = [(p.datum, p.zustandsnote) for p in bridge.pruefungen
             if p.zustandsnote is not None and p.datum]
    if not dated:
        notes = [p.zustandsnote for p in bridge.pruefungen if p.zustandsnote is not None]
        return notes[-1] if notes else None
    return max(dated, key=lambda dn: dn[0])[1]


def _condition_factor(bridge: BridgeExtraction) -> tuple[float, dict]:
    grade = _latest_grade(bridge)
    max_s = max((s.s for s in bridge.schaeden if s.s is not None), default=0)
    max_v = max((s.v for s in bridge.schaeden if s.v is not None), default=0)
    if grade is None:
        base = _FLOOR
    else:
        base = (grade - 1.0) / 3.0          # 1.0→0, 4.0→1
    boost = 0.15 if (max_s >= 3 or max_v >= 3) else 0.0   # severe S or V
    value = max(_FLOOR, min(1.0, base + boost))
    return value, {"zustandsnote": grade, "max_s": max_s, "max_v": max_v,
                   "boost": boost, "value": round(value, 3)}


def _criticality_factor(bridge: BridgeExtraction) -> tuple[float, dict]:
    # Normalize the LLM's free-text values ('Bundesautobahn', 'Leicht möglich…')
    # to canonical codes so the weights actually apply.
    rc_code = M.normalize_strassenklasse(bridge.strassenklasse)
    rc = M.ROADCLASS_WEIGHT.get(rc_code, M.ROADCLASS_DEFAULT)
    dtv = bridge.dtv_gesamt or 0
    dtv_scaled = min(1.0, np.log1p(dtv) / np.log1p(M.DTV_REFERENCE)) if dtv > 0 else 0.0
    umf_code = M.normalize_umfahrt(bridge.umfahrt_schwer)
    umf = M.UMFAHRT_WEIGHT.get(umf_code, M.UMFAHRT_DEFAULT)
    value = max(_FLOOR, 0.40 * rc + 0.30 * dtv_scaled + 0.30 * umf)
    return value, {"roadclass": rc_code, "roadclass_w": rc,
                   "dtv": dtv, "dtv_scaled": round(dtv_scaled, 3),
                   "umfahrt_schwer": umf_code, "umfahrt_w": umf,
                   "value": round(value, 3)}


def _cost_estimate(bridge: BridgeExtraction) -> dict:
    """Rough intervention cost — informational only, NOT part of the priority.

    Priority measures urgency; cost is a separate budget-planning dimension
    (stored as geschaetzte_kosten_eur). Folding cost into priority would demote
    exactly the large, critical bridges that most need attention.
    """
    flaeche = bridge.brueckenflaeche_m2 or 0
    rate = M.COST_RATE_EUR_PER_M2["default"]
    return {"brueckenflaeche_m2": flaeche, "rate_eur_m2": rate,
            "est_cost_eur": round(flaeche * rate)}


def score(bridge: BridgeExtraction) -> tuple[float, dict]:
    """Return (priority_score in [0,1], breakdown dict for priority_breakdown).

    priority = condition × (0.5 + 0.5·criticality)

    Condition is the base need (a pristine bridge scores ~0 regardless of how
    important it is). Criticality amplifies urgency for high-class/high-traffic
    roads (0.5×–1.0×, never crushing a genuinely damaged bridge).
    Cost is deliberately excluded (see _cost_estimate).
    """
    condition, c_why = _condition_factor(bridge)
    criticality, k_why = _criticality_factor(bridge)

    importance_mult = 0.5 + 0.5 * criticality
    priority = condition * importance_mult

    breakdown = {
        "priority_score": round(priority, 4),
        "condition": c_why,
        "criticality": k_why,
        "multipliers": {"importance": round(importance_mult, 3)},
        "cost_estimate": _cost_estimate(bridge),
        "formula": "condition * (0.5 + 0.5*criticality)",
    }
    return round(priority, 4), breakdown
