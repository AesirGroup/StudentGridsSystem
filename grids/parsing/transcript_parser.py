# Parser for transcript documents
# Extracts student info, terms, courses, and totals from transcript PDF text

from typing import Any, Dict, List, Optional
import re

from ..models import StudentData, ProgrammeData, TermData, StudentCourse, TranscriptTotals, TranscriptTotalRow
from .splitter import split_transcript_documents
from .grades import quality_points_to_grade


def sanitize_transcript_text(raw_text: str) -> str:
    """Strips watermarks, footers, and noise from the raw pdfplumber text."""
    if not isinstance(raw_text, str):
        return ""
        
    cleaned_lines = []
    for line in raw_text.split('\n'):
        stripped = line.strip()
        
        # 1. Kill standalone watermark letters (t, r, a, n, s, c, r, i, p, t, etc)
        if len(stripped) <= 1:
            continue
            
        # 2. Kill page footers
        if "This is not an official transcript" in stripped:
            continue
            
        cleaned_lines.append(line.rstrip())
        
    return "\n".join(cleaned_lines)


def _extract_student_names(text: str) -> List[str]:
    docs = split_transcript_documents(text)
    names = []
    for doc in docs:
        # Grabs the name but explicitly ignores a single lowercase letter at the absolute end (watermark bleed)
        match = re.search(r"Record of:\s*([A-Za-z\s]+?)(?:\s+[a-z])?$", doc, re.MULTILINE)
        names.append(match.group(1).strip() if match else "")
    return names


def _extract_student_numbers(text: str) -> List[str]:
    docs = split_transcript_documents(text)
    numbers = []
    for doc in docs:
        match = re.search(r"Student Number:\s*(\d+)", doc, re.IGNORECASE)
        numbers.append(match.group(1).strip() if match else "")
    return numbers


def _extract_dates_of_birth(text: str) -> List[str]:
    docs = split_transcript_documents(text)
    dobs = []
    for doc in docs:
        match = re.search(r"Date of Birth:\s*([0-9]{1,2}-[A-Za-z]{3}-[0-9]{4})", doc, re.IGNORECASE)
        dobs.append(match.group(1).strip() if match else "")
    return dobs


def _extract_campuses(text: str) -> List[str]:
    docs = split_transcript_documents(text)
    campuses = []
    for doc in docs:
        match = re.search(r"^Campus:\s*(.+)$", doc, re.MULTILINE | re.IGNORECASE)
        campuses.append(match.group(1).strip() if match else "")
    return campuses


def _extract_curriculum_blocks_data(text: str) -> List[Dict[str, str]]:
    docs = split_transcript_documents(text)
    blocks = []
    for doc in docs:
        block = {}
        
        # Stripped strict anchors to allow for slight pdfplumber space indentations
        fields = {
            "admit_term": r"Admit Term:\s*(.*)",
            "programme_level": r"Programme Level:\s*(.*)",
            "degree": r"Degree:\s*(.*)",
            "programme": r"Programme:\s*(.*)",
            "faculty": r"Faculty:\s*(.*)",
            "campus": r"Campus:\s*(.*)",
            "department": r"Department:\s*(.*)",
            "major": r"Major:\s*(.*)",
            "degree_gpa": r"Degree GPA:\s*([0-9.]+)", 
        }
        
        for key, pattern in fields.items():
            match = re.search(pattern, doc, re.IGNORECASE)
            block[key] = match.group(1).strip() if match else ""
            
        if not block["degree_gpa"]:
            block["degree_gpa"] = "0.0"
            
        blocks.append(block)
    return blocks


def _extract_term_blocks(text: str) -> List[Dict[str, str]]:
    if not text or not text.strip():
        return []

    # Normalize newlines
    t = text.replace("\r\n", "\n").replace("\r", "\n")

    term_header_re = re.compile(
        r"(?m)^[ \t]*(20\d{2}/20\d{2}\s+(?:Semester\s+[IVX]+|Summer))\b.*$"
    )

    headers = list(term_header_re.finditer(t))
    results = []

    for i, header in enumerate(headers):
        term_label = header.group(1).strip()
        start_pos = header.end()

        # Block extends until the start of the next term header
        if i + 1 < len(headers):
            end_pos = headers[i+1].start()
        else:
            end_pos = len(t)

        block = t[start_pos:end_pos]
        results.append({
            "term": term_label,
            "block": block.strip("\n")
        })

    return results


def _extract_term_block_data(term_entry: Dict[str, str]) -> Dict[str, Any]:
    block = term_entry.get("block", "")
    term_label = term_entry.get("term", "").strip()

    academic_standing = None
    standing_match = re.search(r"^Academic Standing:\s*(.*)$", block, re.MULTILINE | re.IGNORECASE)
    if standing_match:
        academic_standing = standing_match.group(1).strip()

    student_session = None
    session_match = re.search(r"^Student Session:\s*(.*)$", block, re.MULTILINE | re.IGNORECASE)
    if session_match:
        student_session = session_match.group(1).strip()

    course_attempts = []
    
    # Bulletproof regex for capturing the UWI inline course sandwich
    # Allows for missing grades specifically to support "In Progress" courses
    course_pattern = re.compile(
        r"^([A-Z]{4})\s+(\d{4})\s+[A-Z]\s+[A-Z]{2}\s+(.*?)\s+(?:([A-Z][+-]?|F\d?|EX|EC|TC[+-]?)\s+)?(\d+\.\d{2})\s+(\d+\.\d{2})",
        re.MULTILINE
    )
    
    for match in course_pattern.finditer(block):
        subj, num, title, grade, credits, q_points = match.groups()
        course_attempts.append({
            "subject": subj,
            "number": int(num),
            "title": title.strip(),
            "grade": grade,  # May be None if In Progress
            "credits": float(credits),
            "quality_points": float(q_points)
        })

    term_gpa = None
    cumulative_gpa = None
    attempt_hours = None
    passed_hours = None
    earned_hours = None
    quality_points = None

    current_term_match = re.search(r"^Current Term:\s*(.*)$", block, re.MULTILINE | re.IGNORECASE)
    if current_term_match:
        floats = [float(x) for x in re.findall(r"\b\d+\.\d+\b", current_term_match.group(1))]
        if len(floats) >= 6:
            attempt_hours = floats[0]
            passed_hours = floats[1]
            earned_hours = floats[2]
            quality_points = floats[4]
            term_gpa = floats[5]

    cumulative_match = re.search(r"^Cumulative:\s*(.*)$", block, re.MULTILINE | re.IGNORECASE)
    if cumulative_match:
        floats = [float(x) for x in re.findall(r"\b\d+\.\d+\b", cumulative_match.group(1))]
        if len(floats) >= 6:
            cumulative_gpa = floats[5]

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

    totals_line_idx = None
    for idx, line in enumerate(lines):
        if re.search(r"TRANSCRIPT\s+TOTALS", line, re.IGNORECASE):
            totals_line_idx = idx
            break

    if totals_line_idx is None:
        return None

    start_idx = max(0, totals_line_idx - 30)
    end_idx = min(len(lines), totals_line_idx + 10)

    block_lines = lines[start_idx:end_idx]
    return "\n".join(block_lines)


def _parse_transcript_totals(block: str) -> Optional[TranscriptTotals]:
    """Parse transcript totals into Institution/Transfer/Overall/Degree rows."""
    if not block or not block.strip():
        return None

    def extract_floats(text: str) -> List[float]:
        float_pattern = re.compile(r'\b\d+\.\d+\b')
        matches = float_pattern.findall(text)
        return [float(m) for m in matches]

    totals_marker = re.search(r"TRANSCRIPT\s+TOTALS", block, re.IGNORECASE)
    if not totals_marker:
        return None

    pre_totals_text = block[:totals_marker.start()]
    post_totals_text = block[totals_marker.end():]

    table_start = re.search(r"(?:Attempt|GPA\s+Hrs)", pre_totals_text, re.IGNORECASE)
    if table_start:
        table_text = pre_totals_text[table_start.end():]
        floats_before = extract_floats(table_text)
    else:
        floats_before = extract_floats(pre_totals_text)

    floats_after = extract_floats(post_totals_text)

    degree_gpa = None
    lines = pre_totals_text.split('\n')
    for i, line in enumerate(lines):
        if re.search(r"Total\s+Transfer", line, re.IGNORECASE):
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
        attempt_col = floats_before[0:3] if len(floats_before) >= 3 else []
        gpa_hrs_col = floats_before[3:6] if len(floats_before) >= 6 else []
        quality_pts_col = floats_before[6:9] if len(floats_before) >= 9 else []
        gpa_col = floats_before[9:12] if len(floats_before) >= 12 else []

        degree_floats = floats_before[12:15] if len(floats_before) >= 15 else []
        passed_col = floats_after[0:3] if len(floats_after) >= 3 else []

        rows = []
        for i in range(3):
            rows.append({
                'attempt_hours': attempt_col[i] if i < len(attempt_col) else 0.0,
                'passed_hours': passed_col[i] if i < len(passed_col) else 0.0,
                'gpa_hrs_hours': gpa_hrs_col[i] if i < len(gpa_hrs_col) else 0.0,
                'quality_points': quality_pts_col[i] if i < len(quality_pts_col) else 0.0,
                'gpa': gpa_col[i] if i < len(gpa_col) else 0.0
            })

        degree_row = {
            'attempt_hours': degree_floats[0] if len(degree_floats) >= 1 else 0.0,
            'passed_hours': degree_floats[1] if len(degree_floats) >= 2 else degree_floats[0] if len(degree_floats) >= 1 else 0.0,
            'gpa_hrs_hours': degree_floats[0] if len(degree_floats) >= 1 else 0.0,
            'quality_points': degree_floats[2] if len(degree_floats) >= 3 else 0.0,
            'gpa': degree_gpa if degree_gpa else 0.0
        }

        transfer_row_idx = None
        for i, row in enumerate(rows):
            if all(v == 0.0 for v in row.values()):
                transfer_row_idx = i
                break

        if transfer_row_idx is not None:
            other_indices = [i for i in range(3) if i != transfer_row_idx]
            overall_row = rows[other_indices[0]] if len(other_indices) >= 1 else rows[1]
            institution_row = rows[other_indices[1]] if len(other_indices) >= 2 else rows[2]
            transfer_row = rows[transfer_row_idx]
        else:
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
    # Phase 1: Wash out the watermarks and page footers globally
    safe_text = sanitize_transcript_text(raw)
    
    # Phase 2: Standardize array extractions so data cleanly matches per student doc
    student_names = _extract_student_names(safe_text)
    student_numbers = _extract_student_numbers(safe_text)
    date_of_births = _extract_dates_of_birth(safe_text)
    campuses = _extract_campuses(safe_text)
    curriculum_blocks_data = _extract_curriculum_blocks_data(safe_text)

    students = []
    for i in range(len(student_numbers)):
        name = student_names[i] if i < len(student_names) else ""
        num = student_numbers[i] if i < len(student_numbers) else ""
        dob = date_of_births[i] if i < len(date_of_births) else ""
        campus = campuses[i] if i < len(campuses) else ""
        curr = curriculum_blocks_data[i] if i < len(curriculum_blocks_data) else {
            "admit_term": "", "programme_level": "", "degree": "", 
            "programme": "", "faculty": "", "department": "", 
            "major": "", "degree_gpa": "0.0"
        }
        
        # Safely extract the float value once
        degree_gpa_val = float(curr.get("degree_gpa") or 0.0)
        
        students.append(
            StudentData(
                name=name,
                student_number=num,
                date_of_birth=dob,
                campus=campus,
                programme=ProgrammeData(
                    admit_term=curr.get("admit_term", ""),
                    programme_level=curr.get("programme_level", ""),
                    degree=curr.get("degree", ""),
                    programme=curr.get("programme", ""),
                    faculty=curr.get("faculty", ""),
                    department=curr.get("department", ""),
                    major=curr.get("major", ""),
                    degree_gpa=degree_gpa_val,
                ),
                terms=[],
                # Explicitly pass the GPA here so the UI doesn't render 'null'
                overall_gpa=degree_gpa_val, 
                programme_summary=[]
            ))

    # Phase 3: Term and Course Extractions
    docs = split_transcript_documents(safe_text)
    for i in range(min(len(students), len(docs))):
        terms = _extract_term_blocks(docs[i])
        term_data = [_extract_term_block_data(t) for t in terms]
        
        students[i].terms = [TermData(
            term_name=td["term"],
            courses=[StudentCourse(
                subject=sc["subject"],
                number=sc["number"],
                title=sc.get("title", ""),
                credits=sc["credits"],
                grade=sc.get("grade") or quality_points_to_grade(sc["quality_points"]),
                points=sc["quality_points"],
            ) for sc in td["course_attempts"]],
            gpa=td.get("term_gpa"),
            cumulative_gpa=td.get("cumulative_gpa"),
            attempt_hours=td.get("attempt_hours"),
            passed_hours=td.get("passed_hours"),
            earned_hours=td.get("earned_hours"),
            quality_points=td.get("quality_points")
        ) for td in term_data]

        totals_block = _extract_transcript_totals_block(docs[i])
        if totals_block:
            transcript_totals = _parse_transcript_totals(totals_block)
            if transcript_totals:
                students[i].transcript_totals = transcript_totals

    return students