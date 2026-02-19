from typing import Set, Dict, List

# Each set represents a group of courses that are considered identical for degree rules.
_EQUIVALENCY_GROUPS: List[Set[str]] = [
    # Level 1 Shared / Consolidated Transitions
    {"COMP 1601", "COMP 1400", "INFO 1504"},
    {"COMP 1600", "COMP 1401", "INFO 1505"},
    {"COMP 1604", "COMP 1402", "INFO 1503"},
    {"INFO 1601", "COMP 1403", "INFO 1501"},
    {"COMP 1602", "COMP 1404", "INFO 1502"},
    {"COMP 1603", "COMP 1405"},
    {"MATH 1115", "COMP 1406"},
    {"INFO 1600", "COMP 1407", "INFO 1500"},
    {"ESST 2003", "INFO 1506"},
    {"MGMT 1001", "INFO 1507"},

    # Level 2 Shared / Consolidated Transitions
    {"COMP 2611", "COMP 2000", "INFO 2410"},
    {"COMP 2601", "COMP 2200", "INFO 2425"},
    {"INFO 3600", "COMP 2300"},
    {"COMP 2605", "COMP 2700", "INFO 2415"},
    {"INFO 2600", "INFO 2400"},
    {"INFO 2601", "INFO 2500"},
    {"COMP 2603", "COMP 2500", "INFO 2420"}, # Added from the hidden text paragraphs

    # Level 3 Shared / Consolidated Transitions
    {"COMP 2604", "COMP 3100"},
    {"COMP 2606", "COMP 3250", "INFO 3440"}, # Fixed typo: COMPT 2606 -> COMP 2606
    {"INFO 2602", "COMP 3550"},
    {"INFO 2604", "INFO 3415"},
    {"INFO 2605", "INFO 3425"}
]

# Build a fast O(1) lookup dictionary safely
_EQUIV_MAP: Dict[str, Set[str]] = {}
for group in _EQUIVALENCY_GROUPS:
    for course in group:
        if course not in _EQUIV_MAP:
            _EQUIV_MAP[course] = set()
        # Union the sets to safely handle courses mapped multiple times
        _EQUIV_MAP[course].update(group)

def get_equivalent_codes(course_code: str) -> Set[str]:
    """
    Returns a set of all equivalent course codes, including the original code.
    If no equivalencies exist, returns a set containing just the original code.
    """
    return _EQUIV_MAP.get(course_code, {course_code})