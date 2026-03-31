# Grade conversion utilities
# Maps between letter grades (A+, B, F1, etc), quality points, and percentage scores

from dataclasses import dataclass
from typing import Optional, Tuple, List, Dict


@dataclass(frozen=True)
class GradeSpec:
    letter: str
    qp: float
    score_min: Optional[int]  # inclusive
    score_max: Optional[int]  # inclusive; None means no upper bound

# Canonical grade rows (synonyms handled below)
GRADE_TABLE: List[GradeSpec] = [
    GradeSpec("A+", 4.3, 90, 100),
    GradeSpec("A",  4.0, 80, 89),
    GradeSpec("A-", 3.7, 75, 79),
    GradeSpec("B+", 3.3, 70, 74),
    GradeSpec("B",  3.0, 65, 69),
    GradeSpec("B-", 2.7, 60, 64),
    GradeSpec("C+", 2.3, 55, 59),
    GradeSpec("C",  2.0, 50, 54),
    GradeSpec("F1", 1.7, 45, 49),
    GradeSpec("F2", 1.3, 40, 44),
    GradeSpec("F3", 0.0,  0, 39),
    # Special fails when total >= 50 but a key component was failed:
    GradeSpec("FCW", 1.7, 50, None),  # Coursework fail (>=50 overall)
    GradeSpec("FWE", 1.7, 50, None),  # Written exam fail (>=50 overall)
    # Administrative & Miscellaneous Non-GPA grades (0.0 QPs so reverse lookups don't violently crash)
    GradeSpec("EX", 0.0, None, None),
    GradeSpec("EC", 0.0, None, None),
    GradeSpec("FA", 0.0, None, None),
    GradeSpec("FMS", 0.0, None, None),
    GradeSpec("I", 0.0, None, None),
    GradeSpec("IP", 0.0, None, None),
    GradeSpec("LW", 0.0, None, None),
    GradeSpec("NR", 0.0, None, None),
    GradeSpec("P", 0.0, None, None),
    GradeSpec("NP", 0.0, None, None),
    GradeSpec("NV", 0.0, None, None),
    GradeSpec("EI", 0.0, None, None),
    GradeSpec("FMP", 0.0, None, None),
    GradeSpec("CO", 0.0, None, None),
    GradeSpec("AM", 0.0, None, None),
    GradeSpec("AB", 0.0, None, None),
    GradeSpec("DB", 0.0, None, None),
    GradeSpec("V", 0.0, None, None),
    GradeSpec("W", 0.0, None, None),
]

# Accept common synonyms mapped to canonical letters
GRADE_SYNONYMS: Dict[str, str] = {
    "F1CW": "F1", "F1WE": "F1",
    "F2CW": "F2", "F2WE": "F2",
    "F3CW": "F3", "F3WE": "F3",
    "FCW": "FCW", "FWE": "FWE",
    "FC": "FCW", "FE": "FWE",  # Handbook canonical
    # identity for all canonical letters:
    **{g.letter: g.letter for g in GRADE_TABLE}
}

# --- UNIFIED SYSTEM ENGINE CONSTANTS FOR PARSERS --- 
ALL_RECOGNIZED_GRADES = {
    "A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-",
    "F1", "F2", "F3", "FC", "FE", "FCW", "FWE", 
    "EX", "EC", "TC", "FA", "FMS", "I", "IP", "LW", 
    "NR", "P", "NP", "NV", "EI", "FMP", "CO", "AM", "AB", "DB", "V", "W", "FO"
}

KNOWN_GRADE_REGEX_CHUNK = r"([A-Z][+-]?|F[1-3]?|FCW|FWE|FC|FE|EX|EC|TC[+-]?|FMP|FMS|FA|LW|NR|NP|NV|EI|CO|AM|AB|DB|IP|FO)"


# ---- Reverse lookup structures ----
_QP_TO_CANONICALS: Dict[float, List[str]] = {}
for g in GRADE_TABLE:
    _QP_TO_CANONICALS.setdefault(g.qp, [])
    if g.letter not in _QP_TO_CANONICALS[g.qp]:
        _QP_TO_CANONICALS[g.qp].append(g.letter)

_CANONICAL_TO_QP: Dict[str, float] = {g.letter: g.qp for g in GRADE_TABLE}
_CANONICAL_TO_RANGE: Dict[str, Tuple[Optional[int], Optional[int]]] = {
    g.letter: (g.score_min, g.score_max) for g in GRADE_TABLE
}

def quality_points_to_grade(qp: float, prefer_1p7: str = "F1") -> str:
    """Convert quality points to letter grade. Uses nearest match for non-exact values."""
    # clamp to defined range
    qp = max(0.0, min(4.3, float(qp)))

    # exact match?
    if qp in _QP_TO_CANONICALS:
        letters = _QP_TO_CANONICALS[qp]
        if qp == 1.7:
            prefer_1p7 = prefer_1p7.upper()
            if prefer_1p7 in ("F1", "FCW", "FWE"):
                return prefer_1p7
        # default to the first canonical in the table
        return letters[0]

    # nearest neighbor among defined QPs
    defined_qps = sorted(_QP_TO_CANONICALS.keys())
    nearest = min(defined_qps, key=lambda v: abs(v - qp))
    if nearest == 1.7:
        # still honor the preference for the ambiguous bucket
        prefer_1p7 = prefer_1p7.upper()
        return prefer_1p7 if prefer_1p7 in ("F1", "FCW", "FWE") else "F1"
    return _QP_TO_CANONICALS[nearest][0]

def grade_to_quality_points(grade: str) -> float:
    """Convert letter grade to quality points (e.g., 'B+' -> 3.3)."""
    key = grade.strip().upper()
    if key not in GRADE_SYNONYMS:
        raise ValueError(f"Unknown grade: {grade}")
    canonical = GRADE_SYNONYMS[key]
    return _CANONICAL_TO_QP[canonical]

def score_to_grade(score: float, cw_failed: bool = False, we_failed: bool = False) -> Tuple[str, float]:
    """Convert percentage score to (grade, quality_points). Handles FCW/FWE special cases."""
    s = int(round(score))
    s = max(0, min(100, s))

    if s >= 50 and cw_failed:
        return "FCW", _CANONICAL_TO_QP["FCW"]
    if s >= 50 and we_failed:
        return "FWE", _CANONICAL_TO_QP["FWE"]

    for g in GRADE_TABLE:
        lo, hi = g.score_min, g.score_max
        if lo is None:
            continue
        if hi is None:
            if s >= lo:
                return g.letter, g.qp
        else:
            if lo <= s <= hi:
                # Collapse F1/F2/F3 specials to F1/F2/F3
                base = GRADE_SYNONYMS.get(g.letter, g.letter)
                return base, g.qp

    # Fallback (shouldn't hit with ranges above)
    return "F3", 0.0

def grade_to_score_range(grade: str) -> Tuple[Optional[int], Optional[int]]:
    """Get the (min, max) percentage score range for a grade."""
    key = grade.strip().upper()
    if key not in GRADE_SYNONYMS:
        raise ValueError(f"Unknown grade: {grade}")
    canonical = GRADE_SYNONYMS[key]
    return _CANONICAL_TO_RANGE[canonical]
