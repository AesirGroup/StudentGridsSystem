# Parser for degree audit grid documents
# Extracts student info, curriculum data, terms, and courses from grid PDF text

import re
from typing import Any, Dict, List, Optional, Tuple

from ..models import StudentData, ProgrammeData, TermData, StudentCourse, ProgrammeSummaryItem
from .splitter import split_grid_documents
from .grades import quality_points_to_grade


def _extract_student_numbers(text: str) -> List[str]:
    pattern = re.compile(r"Student Number:\s*(\d{9})")
    return pattern.findall(text)

# --- DEPRECATED ---
# def _extract_student_names(text: str) -> List[str]:

#     def _format_name_block(_block: str) -> str:
#         # split on line breaks, strip empties
#         lines = [ln.strip() for ln in _block.strip().splitlines() if ln.strip()]
#         if not lines:
#             return ""

#         if len(lines) == 1:
#             # already on one line; just normalize spacing + case
#             name = re.sub(r"\s+", " ", lines[0]).strip()
#             return name.title()

#         last_name = lines[0]
#         given_names = " ".join(lines[1:])

#         name = f"{given_names} {last_name}"
#         name = re.sub(r"\s+", " ", name).strip()
#         return name.title()

#     names = []
#     # look for text between "Dg GPA" and "CURRENT CURRICULUM"
#     pattern = re.compile(r"Dg GPA\s+([\s\S]*?)\s+CURRENT CURRICULUM", flags=re.IGNORECASE)
#     for match in pattern.finditer(text):
#         block = match.group(1)
#         formatted = _format_name_block(block)
#         if formatted:
#             names.append(formatted)
#     return names

def _extract_student_names(text: str) -> List[str]:
    names = []
    # Look for "Record of: FirstName LastName"
    # We use multiline mode so ^ matches start of line
    pattern = re.compile(r"Record of:\s*(.+)", re.IGNORECASE)
    for match in pattern.finditer(text):
        name = match.group(1).strip()
        names.append(name.title())
    return names


def _extract_student_campuses(text: str) -> List[str]:
    campuses = []
    for match in re.finditer(r"Campus:\s*([^\n\r]+)", text, flags=re.IGNORECASE):
        campuses.append(match.group(1).strip())
    return campuses


def _extract_student_admit_terms(text: str) -> List[str]:
    admit_terms = []
    for match in re.finditer(r"Admit Term:\s*([^\n\r]+)", text, flags=re.IGNORECASE):
        admit_terms.append(match.group(1).strip())
    return admit_terms


def _extract_programme_levels(text: str) -> List[str]:
    _known_levels = ["Undergraduate", "Postgraduate", "Graduate", "Certificate", "Diploma", "MPhil", "PhD"]
    _LEVEL_PATTERN = re.compile(
        r"\b(" + "|".join(map(re.escape, _known_levels)) + r")\b",
        re.IGNORECASE
    )

    def _looks_like_term(s: str) -> bool:
        return (
            bool(re.search(r"\b20\d{2}/20\d{2}\s+Semester\s+[IV]+\b", s, re.IGNORECASE)) or
            bool(re.search(r"\b20\d{2}/20\d{2}\s+Summer\b", s, re.IGNORECASE)) or
            bool(re.search(r"\b20\d{4}\b", s)) or     # occasional OCR artifacts like a long year chunk
            ("Semester" in s) or
            ("Summer" in s)
        )

    results: List[str] = []
    if not text or not text.strip():
        return results

    t = text.replace("\r\n", "\n").replace("\r", "\n")

    for cc_match in re.finditer(r"CURRENT\s+CURRICULUM", t, re.IGNORECASE):
        tail = t[cc_match.end():]
        lines = [ln.strip() for ln in tail.split("\n")[:10] if ln.strip()]
        if not lines:
            continue

        idx = 0
        if idx < len(lines) and _looks_like_term(lines[idx]):
            idx += 1

        scan = lines[idx:idx + 6]
        found_for_block = None
        for ln in scan:
            m = _LEVEL_PATTERN.search(ln)
            if m:
                found_for_block = m.group(1).title().strip()
                break

        if found_for_block:
            results.append(found_for_block)

    return results


def _extract_programmes(text: str) -> List[str]:
    results: List[str] = []
    if not text or not text.strip():
        return results

    t = text.replace("\r\n", "\n").replace("\r", "\n")

    def _looks_like_term(s: str) -> bool:
        return (
            bool(re.search(r"\b20\d{2}/20\d{2}\s+Semester\s+[IV]+\b", s, re.IGNORECASE)) or
            bool(re.search(r"\b20\d{2}/20\d{2}\s+Summer\b", s, re.IGNORECASE)) or
            bool(re.search(r"\b20\d{4}\b", s)) or
            ("Semester" in s) or ("Summer" in s)
        )

    for cc_match in re.finditer(r"CURRENT\s+CURRICULUM", t, re.IGNORECASE):
        tail = t[cc_match.end():]
        lines = [ln.strip() for ln in tail.split("\n")[:12] if ln.strip()]
        if not lines:
            continue

        idx = 0
        if idx < len(lines) and _looks_like_term(lines[idx]):
            idx += 1
        if idx < len(lines) and re.search(r"(Undergraduate|Postgraduate|Graduate|Certificate|Diploma|MPhil|PhD)", lines[idx], re.IGNORECASE):
            idx += 1
        if idx < len(lines) and re.search(r"(Bachelor|Master|Doctor|Diploma|Certificate)", lines[idx], re.IGNORECASE):
            idx += 1

        if idx < len(lines):
            results.append(lines[idx].strip())

    return results


def _extract_faculties(text: str) -> List[str]:
    """Extract faculty names from CURRENT CURRICULUM blocks."""
    results: List[str] = []
    if not text or not text.strip():
        return results

    t = text.replace("\r\n", "\n").replace("\r", "\n")

    def _looks_like_term(s: str) -> bool:
        return (
            bool(re.search(r"\b20\d{2}/20\d{2}\s+Semester\s+[IV]+\b", s, re.IGNORECASE)) or
            bool(re.search(r"\b20\d{2}/20\d{2}\s+Summer\b", s, re.IGNORECASE)) or
            bool(re.search(r"\b20\d{4}\b", s)) or
            ("Semester" in s) or ("Summer" in s)
        )

    for cc_match in re.finditer(r"CURRENT\s+CURRICULUM", t, re.IGNORECASE):
        tail = t[cc_match.end():]
        lines = [ln.strip() for ln in tail.split("\n")[:15] if ln.strip()]
        if not lines:
            continue

        idx = 0
        # Skip term
        if idx < len(lines) and _looks_like_term(lines[idx]):
            idx += 1
        # Skip programme level
        if idx < len(lines) and re.search(r"(Undergraduate|Postgraduate|Graduate|Certificate|Diploma|MPhil|PhD)", lines[idx], re.IGNORECASE):
            idx += 1
        # Skip degree line
        if idx < len(lines) and re.search(r"(Bachelor|Master|Doctor|Diploma|Certificate)", lines[idx], re.IGNORECASE):
            idx += 1
        # Skip programme line (anything before faculty)
        if idx < len(lines):
            idx += 1
        # Faculty should now be here
        if idx < len(lines):
            results.append(lines[idx].strip())

    return results


def _extract_departments(text: str) -> List[str]:

    results: List[str] = []
    if not text or not text.strip():
        return results

    t = text.replace("\r\n", "\n").replace("\r", "\n")

    def _looks_like_term(s: str) -> bool:
        return (
            bool(re.search(r"\b20\d{2}/20\d{2}\s+Semester\s+[IV]+\b", s, re.IGNORECASE)) or
            bool(re.search(r"\b20\d{2}/20\d{2}\s+Summer\b", s, re.IGNORECASE)) or
            bool(re.search(r"\b20\d{4}\b", s)) or
            ("Semester" in s) or ("Summer" in s)
        )

    for cc_match in re.finditer(r"CURRENT\s+CURRICULUM", t, re.IGNORECASE):
        tail = t[cc_match.end():]
        lines = [ln.strip() for ln in tail.split("\n")[:20] if ln.strip()]
        if not lines:
            continue

        idx = 0
        # Skip term
        if idx < len(lines) and _looks_like_term(lines[idx]):
            idx += 1
        # Skip programme level
        if idx < len(lines) and re.search(r"(Undergraduate|Postgraduate|Graduate|Certificate|Diploma|MPhil|PhD)", lines[idx], re.IGNORECASE):
            idx += 1
        # Skip degree line
        if idx < len(lines) and re.search(r"(Bachelor|Master|Doctor|Diploma|Certificate)", lines[idx], re.IGNORECASE):
            idx += 1
        # Skip programme line
        if idx < len(lines):
            idx += 1
        # Skip faculty line
        if idx < len(lines):
            idx += 1
        # Skip campus line
        if idx < len(lines):
            idx += 1
        # Department should be here
        if idx < len(lines):
            results.append(lines[idx].strip())

    return results


def _extract_majors(text: str) -> List[str]:
    """Extract major names from CURRENT CURRICULUM blocks."""
    if not text or not text.strip():
        return []

    t = text.replace("\r\n", "\n").replace("\r", "\n")

    def _looks_like_term(s: str) -> bool:
        return (
            bool(re.search(r"\b20\d{2}/20\d{2}\s+Semester\s+[IV]+\b", s, re.IGNORECASE))
            or bool(re.search(r"\b20\d{2}/20\d{2}\s+Summer\b", s, re.IGNORECASE))
            or ("Semester" in s)
            or ("Summer" in s)
        )

    # patterns for skipping
    _level_pat = re.compile(r"(Undergraduate|Postgraduate|Graduate|Certificate|Diploma|MPhil|PhD)", re.IGNORECASE)
    _degree_pat = re.compile(r"(Bachelor|Master|Doctor|Diploma|Certificate)", re.IGNORECASE)

    results: List[str] = []

    for cc_match in re.finditer(r"CURRENT\s+CURRICULUM", t, re.IGNORECASE):
        tail = t[cc_match.end():]
        lines = [ln.strip() for ln in tail.split("\n")[:25] if ln.strip()]
        if not lines:
            continue

        idx = 0
        # Skip term
        if idx < len(lines) and _looks_like_term(lines[idx]):
            idx += 1
        # Skip programme level
        if idx < len(lines) and _level_pat.search(lines[idx]):
            idx += 1
        # Skip degree line
        if idx < len(lines) and _degree_pat.search(lines[idx]):
            idx += 1
        # Skip programme
        if idx < len(lines): idx += 1
        # Skip faculty
        if idx < len(lines): idx += 1
        # Skip campus
        if idx < len(lines): idx += 1
        # Skip department
        if idx < len(lines): idx += 1

        # Major should now be here
        if idx < len(lines):
            results.append(lines[idx].strip())

    return results


def _extract_degree_gpas(text: str) -> List[float]:
    if not text or not text.strip():
        return []

    t = text.replace("\r\n", "\n").replace("\r", "\n")

    def _looks_like_term(s: str) -> bool:
        return (
            bool(re.search(r"\b20\d{2}/20\d{2}\s+Semester\s+[IV]+\b", s, re.IGNORECASE)) or
            bool(re.search(r"\b20\d{2}/20\d{2}\s+Summer\b", s, re.IGNORECASE)) or
            bool(re.search(r"\b20\d{4}\b", s)) or
            ("Semester" in s) or ("Summer" in s)
        )

    # Programme level keywords (to skip)
    _level_pat = re.compile(r"(Undergraduate|Postgraduate|Graduate|Certificate|Diploma|MPhil|PhD)", re.IGNORECASE)
    # Degree keywords (to skip)
    _degree_pat = re.compile(r"(Bachelor|Master|Doctor|Diploma|Certificate)", re.IGNORECASE)
    # A GPA-looking number (0.00 - 4.00-ish)
    _gpa_pat = re.compile(r"\b([0-4](?:\.\d{1,2})?)\b")

    results: List[float] = []

    for cc_match in re.finditer(r"CURRENT\s+CURRICULUM", t, re.IGNORECASE):
        tail = t[cc_match.end():]
        # Take a reasonable window after the header
        lines = [ln.strip() for ln in tail.split("\n")[:30] if ln.strip()]
        if not lines:
            continue

        idx = 0
        # 1) term
        if idx < len(lines) and _looks_like_term(lines[idx]):
            idx += 1
        # 2) programme level
        if idx < len(lines) and _level_pat.search(lines[idx]):
            idx += 1
        # 3) degree (e.g., Bachelor of Science)
        if idx < len(lines) and _degree_pat.search(lines[idx]):
            idx += 1
        # 4) programme
        if idx < len(lines): idx += 1
        # 5) faculty
        if idx < len(lines): idx += 1
        # 6) campus
        if idx < len(lines): idx += 1
        # 7) department
        if idx < len(lines): idx += 1
        # 8) major
        if idx < len(lines): idx += 1

        # 9) next numeric token should be the Degree GPA
        # scan a few lines in case of OCR line breaks
        for ln in lines[idx:idx + 3]:
            m = _gpa_pat.search(ln)
            if m:
                try:
                    results.append(float(m.group(1)))
                except ValueError:
                    pass
                break  # done for this CURRENT CURRICULUM block

    return results


def _extract_overall_gpas(text: str) -> List[float]:
    """Extract cumulative GPA values (looks for 'Cumm. GPA' or 'Cumulative GPA')."""
    if not text or not text.strip():
        return []

    t = text.replace("\r\n", "\n").replace("\r", "\n")

    # Match variants like: "Cumm. GPA 3.01" or "Cumulative GPA: 3.01"
    pattern = re.compile(
        r"(?:Cumm\.?|Cumulative)\s*GPA\s*[:\-]?\s*([0-4](?:\.\d{1,2})?)",
        re.IGNORECASE
    )

    results: List[float] = []
    for m in pattern.finditer(t):
        try:
            results.append(float(m.group(1)))
        except ValueError:
            pass
    return results

# --- DEPRECATED ---
# def _extract_curriculum_blocks_data(text: str) -> List[Dict[str, Any]]:

#     if not text or not text.strip():
#         return []

#     t = text.replace("\r\n", "\n").replace("\r", "\n")

#     # Helpers
#     def _looks_like_term(s: str) -> bool:
#         return (
#             bool(re.search(r"\b20\d{2}/20\d{2}\s+Semester\s+[IV]+\b", s, re.IGNORECASE))
#             or bool(re.search(r"\b20\d{2}/20\d{2}\s+Summer\b", s, re.IGNORECASE))
#             or ("Semester" in s)
#             or ("Summer" in s)
#         )

#     _level_pat = re.compile(r"(Undergraduate|Postgraduate|Graduate|Certificate|Diploma|MPhil|PhD)", re.IGNORECASE)
#     _degree_pat = re.compile(r"(Bachelor|Master|Doctor|Diploma|Certificate)", re.IGNORECASE)
#     _gpa_pat = re.compile(r"\b([0-5](?:\.\d{1,2})?)\b")   # supports GPA up to 5.00

#     results: List[Dict[str, str]] = []

#     for cc_match in re.finditer(r"CURRENT\s+CURRICULUM", t, re.IGNORECASE):
#         tail = t[cc_match.end():]
#         lines = [ln.strip() for ln in tail.split("\n")[:40] if ln.strip()]
#         if not lines:
#             continue

#         block: Dict[str, Any] = {
#             "admit_term": None,
#             "programme_level": None,
#             "degree": None,
#             "programme": None,
#             "faculty": None,
#             "campus": None,
#             "department": None,
#             "major": None,
#             "degree_gpa": None,
#         }

#         idx = 0
#         # 1) term
#         if idx < len(lines) and _looks_like_term(lines[idx]):
#             block["admit_term"] = lines[idx]
#             idx += 1
#         # 2) programme level
#         if idx < len(lines) and _level_pat.search(lines[idx]):
#             block["programme_level"] = lines[idx]
#             idx += 1
#         # 3) degree
#         if idx < len(lines) and _degree_pat.search(lines[idx]):
#             block["degree"] = lines[idx]
#             idx += 1
#         # 4) programme
#         if idx < len(lines):
#             block["programme"] = lines[idx]
#             idx += 1
#         # 5) faculty
#         if idx < len(lines):
#             block["faculty"] = lines[idx]
#             idx += 1
#         # 6) campus
#         if idx < len(lines):
#             block["campus"] = lines[idx]
#             idx += 1
#         # 7) department
#         if idx < len(lines):
#             block["department"] = lines[idx]
#             idx += 1
#         # 8) major
#         if idx < len(lines):
#             block["major"] = lines[idx]
#             idx += 1
#         # 9) degree GPA (scan nearby lines for a numeric GPA)
#         for ln in lines[idx:idx + 3]:
#             m = _gpa_pat.search(ln)
#             if m:
#                 block["degree_gpa"] = float(m.group(1))
#                 break

#         results.append(block)

#     return results

def _extract_curriculum_blocks_data(text: str) -> List[Dict[str, Any]]:
    if not text or not text.strip():
        return []

    t = text.replace("\r\n", "\n").replace("\r", "\n")

    def _clean_val(line: str) -> str:
        if ":" in line:
            return line.split(":", 1)[1].strip()
        return line.strip()

    def _looks_like_term(s: str) -> bool:
        return (
            bool(re.search(r"\b20\d{2}/20\d{2}\s+Semester\s+[IV]+\b", s, re.IGNORECASE))
            or bool(re.search(r"\b20\d{2}/20\d{2}\s+Summer\b", s, re.IGNORECASE))
            or ("Semester" in s)
            or ("Summer" in s)
        )

    _level_pat = re.compile(r"(Undergraduate|Postgraduate|Graduate|Certificate|Diploma|MPhil|PhD)", re.IGNORECASE)
    _degree_pat = re.compile(r"(Bachelor|Master|Doctor|Diploma|Certificate)", re.IGNORECASE)
    _gpa_pat = re.compile(r"\b([0-5](?:\.\d{1,2})?)\b")

    results: List[Dict[str, str]] = []

    for cc_match in re.finditer(r"CURRENT\s+CURRICULUM", t, re.IGNORECASE):
        tail = t[cc_match.end():]
        lines = [ln.strip() for ln in tail.split("\n")[:40] if ln.strip()]
        
        block: Dict[str, Any] = {
            "admit_term": None, "programme_level": None, "degree": None,
            "programme": None, "faculty": None, "campus": None,
            "department": None, "major": None, "degree_gpa": None,
        }

        idx = 0
        
        # --- NEW FIX: Skip "CURRENT PROGRAMME" header if present ---
        if idx < len(lines) and "CURRENT PROGRAMME" in lines[idx].upper():
            idx += 1
        # -----------------------------------------------------------

        # 1) term
        if idx < len(lines) and _looks_like_term(lines[idx]):
            block["admit_term"] = _clean_val(lines[idx])
            idx += 1
        # 2) programme level
        if idx < len(lines) and _level_pat.search(lines[idx]):
            block["programme_level"] = _clean_val(lines[idx])
            idx += 1
        # 3) degree
        if idx < len(lines) and _degree_pat.search(lines[idx]):
            block["degree"] = _clean_val(lines[idx])
            idx += 1
        # 4) programme
        if idx < len(lines):
            block["programme"] = _clean_val(lines[idx])
            idx += 1
        # 5) faculty
        if idx < len(lines):
            block["faculty"] = _clean_val(lines[idx])
            idx += 1
        # 6) campus
        if idx < len(lines):
            block["campus"] = _clean_val(lines[idx])
            idx += 1
        # 7) department
        if idx < len(lines):
            block["department"] = _clean_val(lines[idx])
            idx += 1
        # 8) major
        if idx < len(lines):
            block["major"] = _clean_val(lines[idx])
            idx += 1
        # 9) degree GPA
        for ln in lines[idx:idx + 3]:
            m = _gpa_pat.search(ln)
            if m:
                block["degree_gpa"] = float(m.group(1))
                break

        results.append(block)

    return results


def _extract_term_blocks(text: str) -> List[Dict[str, str]]:
    """Extract raw term blocks (from term header to 'Term GPA' line)."""
    if not text or not text.strip():
        return []

    # Normalize newlines
    t = text.replace("\r\n", "\n").replace("\r", "\n")

    # Regexes
    term_header_re = re.compile(
        r"(?mi)^[ \t]*(?P<term>20\d{2}/20\d{2}\s+(?:Semester\s+[IVX]+|Summer))\b.*$"
    )
    term_gpa_re = re.compile(r"(?mi)^[ \t]*Term[ \t]+GPA\b.*$")

    results: List[Dict[str, str]] = []

    # Find all term headers
    headers = list(term_header_re.finditer(t))
    # Find all "Term GPA" markers
    gpa_markers = list(term_gpa_re.finditer(t))

    gpa_positions = [m.start() for m in gpa_markers]

    def _next_gpa_after(pos: int):
        import bisect
        idx = bisect.bisect_left(gpa_positions, pos)
        if 0 <= idx < len(gpa_markers):
            return gpa_markers[idx]
        return None

    for i, header in enumerate(headers):
        term_label = header.group("term").strip()
        start_pos = header.start()
        next_gpa = _next_gpa_after(header.end())
        if not next_gpa:
            continue

        # skip malformed: if another term header appears before this GPA
        if i + 1 < len(headers) and next_gpa.start() > headers[i + 1].start():
            continue

        block = t[start_pos:next_gpa.end()]
        results.append({
            "term": term_label,
            "block": block.strip("\n")
        })

    return results


def _extract_term_block_data(term_entry: Dict[str, str]) -> Dict[str, Any]:
    """Parse a term block into structured data (courses, GPA, standing, etc)."""
#grabs whatever looks like this, expand whenever you see a new subject code
    _SUBJ_RE = r"(COMP|INFO|MATH|FOUN|MGMT|ECON|ACCT|FSTF|BIOL|CHEM|PHYS|PSYC|SOCI|STAT|LAW|HIST|LING|ENGL|ESST|HOTL|AGEX|COCR|ENTR|FILM|GEND|HUEC|BIOC|FREN|SPAN|GERM|JAPA)"
    
    # OLD BROKEN REGEX: r"^{_SUBJ_RE}\s*(\d{{3,4}})$"
    # NEW WORKING REGEX: Allows trailing text (e.g. grades)
    _COURSE_SAME_LINE = re.compile(rf"^{_SUBJ_RE}\s*(\d{{3,4}})\b") 
    _SUBJECT_ONLY = re.compile(rf"^{_SUBJ_RE}$")
    _NUMBER_ONLY = re.compile(r"^\d{3,4}$")
    _GPA_NUM_RE = re.compile(r"\b([0-5](?:\.\d{1,2})?)\b")
    
    # Helper to check if a token looks like a float
    def _is_float_token(s: str) -> bool:
        try:
            float(s)
            return True
        except ValueError:
            return False

    # Helper to check if a token looks like a grade
    def _looks_like_grade_token(tok: str) -> bool:
        _NON_GRADE_FLAGS = {"Y", "PO", "CW", "CWK", "EXAM", "OR?", "REP", "R1", "R2", "R3", "R4", "R5", "LW", "EC", "EX", "AM", "FMP"}
        if not tok or len(tok) > 4: return False
        if "/" in tok: return False
        if tok.upper() in _NON_GRADE_FLAGS: return False
        if _is_float_token(tok): return False
        return re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9+\-]{0,3}", tok) is not None

    block = term_entry.get("block", "") or ""
    term_label = term_entry.get("term", "").strip()
    lines = [ln.strip() for ln in block.split("\n") if ln.strip()]

    # --- Academic Standing & Session ---
    academic_standing: Optional[str] = None
    student_session: Optional[str] = None
    for i, ln in enumerate(lines):
        if re.match(r"(?i)^Academic\s+Standing", ln) and i > 0:
            academic_standing = lines[i - 1]
        if re.match(r"(?i)^Student\s+Session", ln) and i + 1 < len(lines):
            student_session = lines[i + 1]

    # --- Courses ---
    course_attempts: List[Dict[str, Any]] = []

    def _find_course_at(idx: int):
        m_same = _COURSE_SAME_LINE.match(lines[idx])
        if m_same:
            return m_same.group(1), int(m_same.group(2)), 1 # 1 means we found it on this line
        m_subj = _SUBJECT_ONLY.match(lines[idx])
        if m_subj and idx + 1 < len(lines) and _NUMBER_ONLY.match(lines[idx + 1]):
            return m_subj.group(1), int(lines[idx + 1]), 2
        return None, None, 0

    def _next_course_or_footer(start: int) -> int:
        j = start
        while j < len(lines):
            if _COURSE_SAME_LINE.match(lines[j]) or _SUBJECT_ONLY.match(lines[j]):
                return j
            if re.match(r"(?i)^Term\s+Credits", lines[j]) or re.match(r"(?i)^Term\s+GPA", lines[j]):
                return j
            j += 1
        return j

    i = 0
    while i < len(lines):
        subj, num, consumed = _find_course_at(i)
        if not subj:
            i += 1
            continue

        # CRITICAL FIX: The window MUST start at 'i' if the course info is on the same line.
        # If consumed=1 (same line), we include line 'i'. 
        # If consumed=2 (split line), we start after the number.
        start_scan = i if consumed == 1 else i + consumed
        
        end_scan = _next_course_or_footer(i + consumed) # Look ahead for next course
        window = lines[start_scan:end_scan]

        # Extract Credits and QP (Floats)
        credits: Optional[float] = None
        quality_points: Optional[float] = None
        
        # Collect all floats in the window
        all_floats = []
        for ln in window:
            # Simple tokenize by space
            for tok in ln.split():
                if _is_float_token(tok):
                    all_floats.append(float(tok))
        
        # Logic: Credits is usually the 2nd to last float, QP is last float
        # In the format: "ACCT 1002 34.00 /40 23.00 /60 57 C+ 3.00 6.90"
        # Floats: 34.00, 23.00, 57.0 (maybe), 3.00, 6.90.
        # Credits = 3.00 (2nd to last), QP = 6.90 (last).
        if len(all_floats) >= 2:
            credits = all_floats[-2]
            quality_points = all_floats[-1]

        # Extract Grade (Last non-float, non-garbage token)
        grade: Optional[str] = None
        # Reverse scan tokens
        found = False
        for ln in reversed(window):
            if found: break
            tokens = ln.split()
            for tok in reversed(tokens):
                if _looks_like_grade_token(tok):
                    grade = tok
                    found = True
                    break

        course_attempts.append({
            "subject": subj, "number": num,
            "credits": credits, "quality_points": quality_points, "grade": grade,
        })

        i = end_scan

    # --- Term GPA ---
    term_gpa: Optional[float] = None
    for idx, ln in enumerate(lines):
        if re.match(r"(?i)^Term\s+GPA", ln):
            m = _GPA_NUM_RE.search(ln)
            if m: term_gpa = float(m.group(1))

    return {
        "term": term_label, "academic_standing": academic_standing,
        "student_session": student_session, "course_attempts": course_attempts,
        "term_gpa": term_gpa,
    }


def _extract_programme_summary_data(text: str) -> List[Dict[str, str]]:
    """Extract programme summary progress (requirement name -> fraction like '9/9')."""

    _STUDENT_SPLIT_RE = re.compile(r"(?mi)^ *Student +Number *:")
    _SUMMARY_START_RE = re.compile(r"(?mi)^\s*Programme +Summary\s*:\s*$")
    _SUMMARY_HEADER_RE = re.compile(r"(?mi)^\s*Summary\b")  # e.g., "Summary 2025-08-05 ..."
    _PROGRAMME_OVERALL_RE = re.compile(r"(?mi)^\s*Programme +Overall\s*$")
    _FRACTION_RE = re.compile(r"(\d+(?:\.\d+)?)\s*/\s*(\d*(?:\.\d+)?)")  # supports '0/', '30/30', '12.0/15'

    # A requirement line typically looks like:
    #   "10 Biology Major Electives          30/30"
    #   "1 FOUN Courses-FSA                  9/9"
    #   "60 Non-Major Electives               0/"
    # The numeric id at the start is optional to match robustly.
    _REQ_LINE_RE = re.compile(
        r"""(?mx) ^
            \s*(?:\d+)\s+                # leading numeric id (e.g., '10') - required in samples, but we'll be lenient
            (?P<name>.*?)                # requirement name (non-greedy)
            \s+(?P<frac>\d+(?:\.\d+)?\s*/\s*\d*(?:\.\d+)?)\s*$
        """
    )

    def _normalize_fraction(frac: str) -> str:
        # remove internal spaces around '/', keep as string
        return frac.replace(" ", "")

    if not text or not text.strip():
        return []

    t = text.replace("\r\n", "\n").replace("\r", "\n")

    # --- Split into student chunks ---
    markers = list(_STUDENT_SPLIT_RE.finditer(t))
    student_chunks: List[str] = []
    if not markers:
        student_chunks = [t]
    else:
        for i, m in enumerate(markers):
            start = m.start()
            end = markers[i + 1].start() if i + 1 < len(markers) else len(t)
            student_chunks.append(t[start:end])

    results: List[Dict[str, str]] = []

    for chunk in student_chunks:
        lines = [ln.rstrip() for ln in chunk.split("\n")]

        # Find the Programme Summary block
        start_idx = None
        for idx, ln in enumerate(lines):
            if _SUMMARY_START_RE.match(ln):
                start_idx = idx
                break

        req_map: Dict[str, str] = {}

        if start_idx is not None:
            # Skip the 'Programme Summary:' line itself
            i = start_idx + 1

            # Optionally skip the "Summary 2025-..." header line
            if i < len(lines) and _SUMMARY_HEADER_RE.match(lines[i]):
                i += 1

            # Collect requirement rows until we hit "Programme Overall" or end
            while i < len(lines):
                if _PROGRAMME_OVERALL_RE.match(lines[i]):
                    break
                m = _REQ_LINE_RE.match(lines[i])
                if m:
                    name = " ".join(m.group("name").split())  # collapse extra spaces within the name
                    frac = _normalize_fraction(m.group("frac"))
                    req_map[name] = frac
                i += 1

            # Handle "Programme Overall"
            if i < len(lines) and _PROGRAMME_OVERALL_RE.match(lines[i]):
                # The fraction is usually on the NEXT non-empty line, after a programme code
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines):
                    # Find the last fraction on that line (e.g., "GESC-BSC-S_F   87/93")
                    fracs = list(_FRACTION_RE.finditer(lines[j]))
                    if fracs:
                        last = fracs[-1].group(0)
                        req_map["Programme Overall"] = _normalize_fraction(last)

        results.append(req_map)

    return results


def _extract_num_denom(frac: Optional[str]) -> Tuple[int, int]:
    def _to_int(s: str) -> int:
        s = s.strip()
        if not s:
            return -1
        try:
            return int(s)
        except ValueError:
            try:
                return int(float(s))
            except ValueError:
                m = re.search(r"\d+(?:\.\d+)?", s)
                return int(float(m.group(0))) if m else 0

    if not frac:
        return 0, 0

    if '/' in frac:
        left, right = frac.split('/', 1)
    else:
        left, right = "", ""

    return _to_int(left), _to_int(right)


def parse_grids(raw: str) -> List[StudentData]:
    student_numbers = _extract_student_numbers(raw)
    names = _extract_student_names(raw)
    curr_blocks = _extract_curriculum_blocks_data(raw)
    overall_gpas = _extract_overall_gpas(raw)
    programme_summary_data = _extract_programme_summary_data(raw)

    students = []
    for i in range(len(student_numbers)):
        students.append(
            StudentData(
                name=names[i],
                student_number=student_numbers[i],
                date_of_birth=None,
                campus=curr_blocks[i]["campus"],
                programme=ProgrammeData(
                    admit_term=curr_blocks[i]["admit_term"],
                    programme_level=curr_blocks[i]["programme_level"],
                    degree=curr_blocks[i]["degree"],
                    programme=curr_blocks[i]["programme"],
                    faculty=curr_blocks[i]["faculty"],
                    department=curr_blocks[i]["department"],
                    major=curr_blocks[i]["major"],
                    degree_gpa=curr_blocks[i]["degree_gpa"],
                ),
                terms=[],
                overall_gpa=overall_gpas[i],
                programme_summary=[
                    ProgrammeSummaryItem(
                        name=pr[0],
                        progress_numerator=_extract_num_denom(pr[1])[0],
                        progress_denominator=_extract_num_denom(pr[1])[1],
                    ) for pr in programme_summary_data[i].items()]
            )
        )

    docs = split_grid_documents(raw)
    for i in range(len(students)):
        terms = _extract_term_blocks(docs[i])
        term_data = [_extract_term_block_data(t) for t in terms]
        students[i].terms = [TermData(
            term_name=td["term"],
            courses = [StudentCourse(
                subject=sc["subject"],
                number=sc["number"],
                title=sc.get("title", ""),
                credits=sc["credits"],
                grade=sc.get("grade", quality_points_to_grade(sc["quality_points"])), # fall in case we can't pull grade
                points=sc["quality_points"],
            ) for sc in td["course_attempts"]],
            gpa = td["term_gpa"],
            cumulative_gpa=None,
            attempt_hours=None,
            earned_hours=None,
            quality_points=None
        ) for td in term_data]
    return students
