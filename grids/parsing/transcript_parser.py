# Parser for transcript documents
# Extracts student info, terms, courses, and totals from transcript PDF text

from typing import Any, Dict, List, Optional
import re

from ..models import StudentData, ProgrammeData, TermData, StudentCourse, TranscriptTotals, TranscriptTotalRow
from .splitter import split_transcript_documents
from .grades import quality_points_to_grade


def _extract_student_names(text: str) -> List[str]:
    if not isinstance(text, str) or not text.strip():
        return []

    lines = text.splitlines()
    names: List[str] = []
    i = 0
    while i < len(lines):
        if re.search(r"\bSTUDENT\s+INFORMATION\b", lines[i], re.IGNORECASE):
            # grab the next non-empty line
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                names.append(lines[j].strip())
            i = j  # continue from where we looked
        else:
            i += 1
    return names


def _extract_student_numbers(text: str) -> List[str]:
    matches = re.findall(r"Record of:\s*(\d+)\s*Student Number:", text, re.DOTALL)
    return matches


def _extract_dates_of_birth(text: str) -> List[str]:
    if not isinstance(text, str) or not text.strip():
        return []

    dob_pattern = re.compile(r"Date of Birth:\s*([0-9]{1,2}-[A-Za-z]{3}-[0-9]{4})", re.IGNORECASE)
    return dob_pattern.findall(text)


def _extract_campuses(text: str) -> List[str]:
    if not isinstance(text, str) or not text.strip():
        return []

    campus_pattern = re.compile(r"Campus:\s*(.+)", re.IGNORECASE)
    campuses = []

    for line in text.splitlines():
        match = campus_pattern.search(line)
        if match:
            campuses.append(match.group(1).strip())

    return campuses


def _extract_curriculum_blocks_data(text: str) -> List[Dict[str, str]]:
    fields = [
        "Admit Term",
        "Programme Level",
        "Degree",
        "Programme",
        "Faculty",
        "Campus",
        "Department",
        "Major",
        "Degree GPA",
    ]

    def _to_snake_case(label: str) -> str:
        """Convert label to snake_case lowercase."""
        return re.sub(r"\s+", "_", label.strip()).lower()

    def _next_nonempty(lines: List[str], start: int) -> Optional[int]:
        """Return index of the next non-empty line at/after start, or None if not found."""
        i = start
        while i < len(lines):
            if lines[i].strip():
                return i
            i += 1
        return None

    if not isinstance(text, str) or not text.strip():
        return []

    # Keep original line positions; don't drop empty lines globally
    lines = [ln.rstrip() for ln in text.splitlines()]
    out: List[Dict[str, str]] = []

    i = 0
    while i < len(lines):
        # Find "CURRICULUM INFORMATION"
        if re.fullmatch(r"(?i)\s*CURRICULUM INFORMATION\s*", lines[i] or ""):
            # Expect next non-empty to be "CURRENT PROGRAMME"
            j = _next_nonempty(lines, i + 1)
            if j is None or not re.fullmatch(r"(?i)\s*CURRENT PROGRAMME\s*", lines[j] or ""):
                i += 1
                continue

            # Expect the 9 label lines (in order)
            k = j + 1
            label_indices = []
            ok_labels = True
            for field in fields:
                k = _next_nonempty(lines, k)
                if k is None:
                    ok_labels = False
                    break
                if not re.fullmatch(rf"(?i)\s*{re.escape(field)}\s*:\s*", lines[k] or ""):
                    ok_labels = False
                    break
                label_indices.append(k)
                k += 1

            if not ok_labels:
                i += 1
                continue

            # Read the 9 value lines (next 9 non-empty lines)
            values: List[str] = []
            for _ in fields:
                k = _next_nonempty(lines, k)
                if k is None:
                    values = []
                    break
                values.append(lines[k].strip())
                k += 1

            if len(values) != len(fields):
                i += 1
                continue

            # Use snake_case keys
            block = {_to_snake_case(field): value for field, value in zip(fields, values)}
            out.append(block)

            # Jump cursor past this block to avoid re-matching inside
            i = k
        else:
            i += 1

    return out


def _extract_term_blocks(text: str) -> List[Dict[str, str]]:
    if not text or not text.strip():
        return []

    # Normalize newlines
    t = text.replace("\r\n", "\n").replace("\r", "\n")

    # Regexes
    term_header_re = re.compile(
        r"(?mi)^[ \t]*(?P<term>20\d{2}/20\d{2}\s+(?:Semester\s+[IVX]+|Summer))\b.*$"
    )
    term_totals_re = re.compile(r"(?mi)^[ \t]*Term[ \t]+Totals\b.*$")

    results: List[Dict[str, str]] = []

    # Find all term headers and all 'Term Totals' markers
    headers = list(term_header_re.finditer(t))
    totals_markers = list(term_totals_re.finditer(t))

    if not headers or not totals_markers:
        return []

    totals_positions = [m.start() for m in totals_markers]

    def _next_totals_after(pos: int):
        import bisect
        idx = bisect.bisect_left(totals_positions, pos)
        if 0 <= idx < len(totals_markers):
            return totals_markers[idx]
        return None

    for i, header in enumerate(headers):
        term_label = header.group("term").strip()
        start_pos = header.start()

        next_totals = _next_totals_after(header.end())
        if not next_totals:
            # No 'Term Totals' after this header -> skip malformed block
            continue

        # If another term header appears before this 'Term Totals', skip this header as malformed
        if i + 1 < len(headers) and next_totals.start() > headers[i + 1].start():
            continue

        block = t[start_pos:next_totals.end()]
        results.append({
            "term": term_label,
            "block": block.strip("\n")
        })

    return results


def _extract_term_block_data(term_entry: Dict[str, str]) -> Dict[str, Any]:
    """Parse a term block into courses, GPA, and academic standing."""

    # Subjects seen in your samples; extend as needed.
    _SUBJ_RE = r"(COMP|INFO|MATH|FOUN|MGMT|ECON|ACCT|FSTF|BIOL|CHEM|PHYS|PSYC|SOCI|STAT|LAW|HIST|LING|ENGL)"
    _COURSE_SAME_LINE = re.compile(rf"^{_SUBJ_RE}\s*(\d{{3,4}})$")
    _SUBJECT_ONLY = re.compile(rf"^{_SUBJ_RE}$")
    _NUMBER_ONLY = re.compile(r"^\d{3,4}$")

    # GPA-looking number (0.00-5.00)
    _GPA_NUM_RE = re.compile(r"\b([0-5](?:\.\d{1,2})?)\b")

    # Non-grade flags we should ignore when picking the last token
    _NON_GRADE_FLAGS = {"Y", "PO", "CW", "CWK", "EXAM", "OR?", "REP", "R1", "R2", "R3", "R4", "R5", "UG", "S", "."}

    def _is_float_token(s: str) -> bool:
        try:
            float(s)
            return True
        except ValueError:
            return False

    def _looks_like_grade_token(tok: str) -> bool:
        # Grade tokens: short (A, B+, C-), not numbers, not flags like 'CW'
        if not tok or len(tok) > 4:
            return False
        if "/" in tok:
            return False
        if tok.upper() in _NON_GRADE_FLAGS:
            return False
        if _is_float_token(tok):
            return False
        return re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9+\-]{0,3}", tok) is not None

    block = term_entry.get("block", "") or ""
    term_label = term_entry.get("term", "").strip()

    # normalize and split
    lines = [ln.strip() for ln in block.split("\n") if ln.strip()]

    # --- Academic Standing (line before 'Academic Standing:') ---
    academic_standing: Optional[str] = None
    for i, ln in enumerate(lines):
        if re.match(r"(?i)^Academic\s+Standing", ln):
            if i > 0:
                academic_standing = lines[i - 1]
            break

    # --- Student Session (line after 'Student Session:') ---
    student_session: Optional[str] = None
    for i, ln in enumerate(lines):
        if re.match(r"(?i)^Student\s+Session", ln):
            if i + 1 < len(lines):
                student_session = lines[i + 1]
            break

    # --- Courses ---
    course_attempts: List[Dict[str, Any]] = []

    def _is_footer_marker(s: str) -> bool:
        return bool(
            re.match(r"(?i)^Attempt$", s)
            or re.match(r"(?i)^Current\s+Term:", s)
            or re.match(r"(?i)^Term\s+Totals$", s)
        )

    def _find_course_at(idx: int):
        """
        Detect course start at lines[idx].
        Returns (subject, number, consumed_lines) or (None, None, 0)
        """
        m_same = _COURSE_SAME_LINE.match(lines[idx])
        if m_same:
            return m_same.group(1), int(m_same.group(2)), 1
        m_subj = _SUBJECT_ONLY.match(lines[idx])
        if m_subj and idx + 1 < len(lines) and _NUMBER_ONLY.match(lines[idx + 1]):
            return m_subj.group(1), int(lines[idx + 1]), 2
        return None, None, 0

    def _next_course_or_footer(start: int) -> int:
        """
        Find the index where this course's window should end:
        - next course header
        - or footer markers ('Attempt'/'Current Term:'/'Term Totals')
        - or end of lines
        Returns index (exclusive).
        """
        j = start
        while j < len(lines):
            if _COURSE_SAME_LINE.match(lines[j]) or _SUBJECT_ONLY.match(lines[j]) or _is_footer_marker(lines[j]):
                return j
            j += 1
        return j

    i = 0
    while i < len(lines):
        subj, num, consumed = _find_course_at(i)
        if not subj:
            i += 1
            continue

        # window: after course code up to next course/footer
        start_scan = i + consumed
        end_scan = _next_course_or_footer(start_scan)
        window = [w for w in lines[start_scan:end_scan] if w not in {".", "R"}]  # drop separators

        # grade = last candidate token in window (position-based)
        grade: Optional[str] = None
        for tok in reversed(window):
            if _looks_like_grade_token(tok):
                grade = tok
                break

        # credits & quality_points:
        # In this new format, per-course numeric trio is: Mark(0.00), Hours(credits), Points(quality_points),
        # and they appear *before* the grade. So take the last two floats *before* the grade token.
        credits: Optional[float] = None
        quality_points: Optional[float] = None
        if grade is not None:
            # gather floats up to (but not including) the grade
            pre_grade: List[str] = []
            for tok in window:
                if tok == grade:
                    break
                pre_grade.append(tok)
            float_tokens = [float(t) for t in pre_grade if _is_float_token(t)]
            if len(float_tokens) >= 2:
                credits = float_tokens[-2]
                quality_points = float_tokens[-1]
        else:
            # Fallback: take last two floats in the window
            float_tokens = [float(t) for t in window if _is_float_token(t)]
            if len(float_tokens) >= 2:
                credits = float_tokens[-2]
                quality_points = float_tokens[-1]

        course_attempts.append({
            "subject": subj,
            "number": num,
            "credits": credits,
            "quality_points": quality_points,
            "grade": grade,
        })

        i = end_scan  # jump to end of this course window

    # --- Term Statistics (from the 'Current Term:/Cumulative:' table before 'Term Totals') ---
    # The section contains 12 values in 6 pairs (Current/Cumulative):
    # 0-1: Attempt Hours, 2-3: Passed Hours, 4-5: Earned Hours,
    # 6-7: GPA Hours, 8-9: Quality Points, 10-11: GPA
    term_gpa: Optional[float] = None
    cumulative_gpa: Optional[float] = None
    attempt_hours: Optional[float] = None
    passed_hours: Optional[float] = None
    earned_hours: Optional[float] = None
    quality_points: Optional[float] = None

    try:
        # find bounds of the numeric summary section
        idx_current = next(i for i, ln in enumerate(lines) if re.match(r"(?i)^Current\s+Term:", ln))
        idx_end = next(i for i, ln in enumerate(lines[idx_current:], start=idx_current) if re.match(r"(?i)^Term\s+Totals$", ln))
        # collect all floats in that region (using a general float pattern, not just GPA values)
        # Pattern matches any float like 15.00, 56.10, 3.74, etc.
        float_pattern = re.compile(r'\b\d+\.\d+\b')
        nums: List[float] = []
        for ln in lines[idx_current:idx_end]:
            for m in float_pattern.finditer(ln):
                nums.append(float(m.group()))

        # Extract all statistics if we have the full set of 12 values
        if len(nums) >= 12:
            attempt_hours = nums[0]      # Current term attempt hours
            passed_hours = nums[2]       # Current term passed hours
            earned_hours = nums[4]       # Current term earned hours
            quality_points = nums[8]     # Current term quality points
            term_gpa = nums[10]          # Current term GPA
            cumulative_gpa = nums[11]    # Cumulative GPA
        elif len(nums) >= 2:
            # Fallback: if we don't have all 12, at least try to get the GPAs
            term_gpa = nums[-2]
            cumulative_gpa = nums[-1] if len(nums) > 1 else None
    except StopIteration:
        # section not present -> leave as None
        pass

    return {
        "term": term_label,
        "academic_standing": academic_standing,
        "student_session": student_session,
        "course_attempts": course_attempts,
        "term_gpa": term_gpa,
        "cumulative_gpa": cumulative_gpa,
        "attempt_hours": attempt_hours,
        "passed_hours": passed_hours,
        "earned_hours": earned_hours,
        "quality_points": quality_points,
    }


def _extract_programme_summary(text: str) -> Dict[str, str]:
    # TODO: implement programme summary extraction for transcripts
    pass


def _extract_transcript_totals_block(text: str) -> Optional[str]:
    """Extract the raw TRANSCRIPT TOTALS section (30 lines before, 10 after marker)."""
    if not text or not text.strip():
        return None

    # Find the TRANSCRIPT TOTALS marker
    totals_match = re.search(r"TRANSCRIPT\s+TOTALS", text, re.IGNORECASE)
    if not totals_match:
        return None

    # Extract a generous window around the marker (approximately 30 lines before and 10 after)
    lines = text.splitlines()

    # Find the line index where TRANSCRIPT TOTALS appears
    totals_line_idx = None
    for idx, line in enumerate(lines):
        if re.search(r"TRANSCRIPT\s+TOTALS", line, re.IGNORECASE):
            totals_line_idx = idx
            break

    if totals_line_idx is None:
        return None

    # Extract window: 30 lines before to 10 lines after
    start_idx = max(0, totals_line_idx - 30)
    end_idx = min(len(lines), totals_line_idx + 10)

    block_lines = lines[start_idx:end_idx]
    return "\n".join(block_lines)


def _parse_transcript_totals(block: str) -> Optional[TranscriptTotals]:
    """Parse transcript totals into Institution/Transfer/Overall/Degree rows."""
    if not block or not block.strip():
        return None

    def extract_floats(text: str) -> List[float]:
        """Extract all float values from text"""
        float_pattern = re.compile(r'\b\d+\.\d+\b')
        matches = float_pattern.findall(text)
        return [float(m) for m in matches]

    # Split the block at TRANSCRIPT TOTALS marker
    totals_marker = re.search(r"TRANSCRIPT\s+TOTALS", block, re.IGNORECASE)
    if not totals_marker:
        return None

    pre_totals_text = block[:totals_marker.start()]
    post_totals_text = block[totals_marker.end():]

    # Find where the table actually starts (after the row labels)
    # Look for "Attempt" or "GPA Hrs" column headers
    table_start = re.search(r"(?:Attempt|GPA\s+Hrs)", pre_totals_text, re.IGNORECASE)
    if table_start:
        # Extract floats only from the table section
        table_text = pre_totals_text[table_start.end():]
        floats_before = extract_floats(table_text)
    else:
        floats_before = extract_floats(pre_totals_text)

    # Extract floats from after TRANSCRIPT TOTALS
    floats_after = extract_floats(post_totals_text)

    # Also extract the Degree GPA which appears before the table (usually a value < 5.0 before "Total Transfer")
    degree_gpa = None
    lines = pre_totals_text.split('\n')
    for i, line in enumerate(lines):
        if re.search(r"Total\s+Transfer", line, re.IGNORECASE):
            # Check the 2-3 lines before for a small float (GPA < 5.0)
            for j in range(max(0, i-3), i):
                line_floats = extract_floats(lines[j])
                for val in line_floats:
                    if 0.0 < val <= 5.0:
                        degree_gpa = val
                        break
                if degree_gpa:
                    break
            break

    if len(floats_before) >= 12 and len(floats_after) >= 3:
        # Extract columns from before section
        # Assume first 3 floats = Attempt column
        attempt_col = floats_before[0:3] if len(floats_before) >= 3 else []
        # Next 3 floats = GPA Hrs column
        gpa_hrs_col = floats_before[3:6] if len(floats_before) >= 6 else []
        # Next 3 floats = Quality Points column
        quality_pts_col = floats_before[6:9] if len(floats_before) >= 9 else []
        # Next 3 floats = GPA column for first 3 rows
        gpa_col = floats_before[9:12] if len(floats_before) >= 12 else []

        # Degree row values (typically last 3-4 floats before TRANSCRIPT TOTALS)
        # These represent: Attempt, GPA Hrs, Quality Points for Degree row
        degree_floats = floats_before[12:15] if len(floats_before) >= 15 else []

        # Extract Passed column from after section (first 3 floats)
        passed_col = floats_after[0:3] if len(floats_after) >= 3 else []

        # Assemble rows (order is typically: Total Transfer, Overall, Total Institution)
        rows = []
        for i in range(3):  # First 3 rows
            rows.append({
                'attempt_hours': attempt_col[i] if i < len(attempt_col) else 0.0,
                'passed_hours': passed_col[i] if i < len(passed_col) else 0.0,
                'gpa_hrs_hours': gpa_hrs_col[i] if i < len(gpa_hrs_col) else 0.0,
                'quality_points': quality_pts_col[i] if i < len(quality_pts_col) else 0.0,
                'gpa': gpa_col[i] if i < len(gpa_col) else 0.0
            })

        # Degree row
        degree_row = {
            'attempt_hours': degree_floats[0] if len(degree_floats) >= 1 else 0.0,
            'passed_hours': degree_floats[1] if len(degree_floats) >= 2 else degree_floats[0] if len(degree_floats) >= 1 else 0.0,
            'gpa_hrs_hours': degree_floats[0] if len(degree_floats) >= 1 else 0.0,  # Same as attempt
            'quality_points': degree_floats[2] if len(degree_floats) >= 3 else 0.0,
            'gpa': degree_gpa if degree_gpa else 0.0
        }

        # Identify which row is all zeros (Total Transfer)
        transfer_row_idx = None
        for i, row in enumerate(rows):
            if all(v == 0.0 for v in row.values()):
                transfer_row_idx = i
                break

        if transfer_row_idx is not None:
            # The other two rows are Overall and Total Institution (usually identical)
            other_indices = [i for i in range(3) if i != transfer_row_idx]
            overall_row = rows[other_indices[0]] if len(other_indices) >= 1 else rows[1]
            institution_row = rows[other_indices[1]] if len(other_indices) >= 2 else rows[2]
            transfer_row = rows[transfer_row_idx]
        else:
            # Fallback: assume order is Total Transfer, Overall, Total Institution
            transfer_row = rows[0]
            overall_row = rows[1]
            institution_row = rows[2]

        return TranscriptTotals(
            total_institution=TranscriptTotalRow(**institution_row),
            total_transfer=TranscriptTotalRow(**transfer_row),
            overall=TranscriptTotalRow(**overall_row),
            degree=TranscriptTotalRow(**degree_row)
        )

    return None


def parse_transcripts(raw: str) -> List[StudentData]:
    student_names = _extract_student_names(raw)
    student_numbers = _extract_student_numbers(raw)
    date_of_births = _extract_dates_of_birth(raw)
    campuses = _extract_campuses(raw)
    curriculum_blocks_data = _extract_curriculum_blocks_data(raw)

    students = []
    for i in range(len(student_numbers)):
        students.append(
            StudentData(
                name=student_names[i],
                student_number=student_numbers[i],
                date_of_birth=date_of_births[i],
                campus=campuses[i],
                programme=ProgrammeData(
                    admit_term=curriculum_blocks_data[i]["admit_term"],
                    programme_level=curriculum_blocks_data[i]["programme_level"],
                    degree=curriculum_blocks_data[i]["degree"],
                    programme=curriculum_blocks_data[i]["programme"],
                    faculty=curriculum_blocks_data[i]["faculty"],
                    department=curriculum_blocks_data[i]["department"],
                    major=curriculum_blocks_data[i]["major"],
                    degree_gpa=float(curriculum_blocks_data[i]["degree_gpa"]),
                ),
                terms=[],
                overall_gpa=None,
                programme_summary=[]
            ))

    docs = split_transcript_documents(raw)
    for i in range(len(students)):
        terms = _extract_term_blocks(docs[i])
        term_data = [_extract_term_block_data(t) for t in terms]
        students[i].terms = [TermData(
            term_name=td["term"],
            courses=[StudentCourse(
                subject=sc["subject"],
                number=sc["number"],
                title=sc.get("title", ""),
                credits=sc["credits"],
                grade=sc.get("grade", quality_points_to_grade(sc["quality_points"])), # fall in case we can't pull grade
                points=sc["quality_points"],
            ) for sc in td["course_attempts"]],
            gpa=td.get("term_gpa"),
            cumulative_gpa=td.get("cumulative_gpa"),
            attempt_hours=td.get("attempt_hours"),
            passed_hours=td.get("passed_hours"),
            earned_hours=td.get("earned_hours"),
            quality_points=td.get("quality_points")
        ) for td in term_data]

        # Extract transcript totals
        totals_block = _extract_transcript_totals_block(docs[i])
        if totals_block:
            transcript_totals = _parse_transcript_totals(totals_block)
            if transcript_totals:
                students[i].transcript_totals = transcript_totals

    return students
