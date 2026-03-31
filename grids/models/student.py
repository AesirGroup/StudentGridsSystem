# Student data models
# StudentCourse, TermData, and StudentData for representing student records

from typing import Dict, List, Optional, Any, Generator, Tuple
from pydantic import BaseModel, Field, model_validator
import re

from .programme import ProgrammeData, ProgrammeSummaryItem
from .transcript import TranscriptTotals

# Passing grades: A, B, C (with +/-) and EC (Exemption with Credit)
# Excludes: D, E, P (not passing), EX (exemption without credit), CO (co-curricular)
_PASSING_GRADE_RE = re.compile(r"^[ABC][+-]?$|^EC$", re.IGNORECASE)
_ALL_PASSING_GRADE_RE = re.compile(r"^[ABC][+-]?$|^EC$", re.IGNORECASE)
_GRADE_ORDER = [
    "A+",
    "A",
    "A-",
    "B+",
    "B",
    "B-",
    "C+",
    "C",
    "C-",
    "D+",
    "D",
    "D-",
    "E+",
    "E",
    "E-",
    "P",
]
_GRADE_SCORE = {g: len(_GRADE_ORDER) - i for i, g in enumerate(_GRADE_ORDER)}


def _normalize_grade(g: str) -> str:
    """Uppercase, strip spaces, keep +/- if present (e.g., 'b +' -> 'B+')."""
    return (g or "").upper().replace(" ", "")


class StudentCourse(BaseModel):
    subject: Optional[str] = None
    number: Optional[int] = None
    title: Optional[str] = None
    grade: str = ""
    credits: float = 0.0
    points: Optional[float] = None
    level: int = 0
    # Alternative field names from frontend
    code: Optional[str] = None
    name: Optional[str] = None  # Alias for title

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, values):
        # Handle aliases: 'name' -> 'title', 'code' -> 'subject' + 'number'
        if isinstance(values, dict):
            # Handle title vs name
            if "name" in values and "title" not in values:
                values["title"] = values["name"]

            # Handle code -> subject + number
            if "code" in values and values["code"]:
                code = values["code"]
                # Parse "COMP 1600" -> subject="COMP", number=1600
                parts = code.strip().split()
                if len(parts) >= 2:
                    if "subject" not in values or not values.get("subject"):
                        values["subject"] = parts[0]
                    if "number" not in values or not values.get("number"):
                        try:
                            values["number"] = int(parts[1])
                        except ValueError:
                            pass

            # LEVEL INFERENCE
            if values.get("number") and not values.get("level"):
                try:
                    values["level"] = int(values["number"]) // 1000
                except (ValueError, TypeError):
                    pass

        return values

    @property
    def course_code(self) -> str:
        """Get course code (e.g., 'COMP 1600')."""
        if self.subject and self.number:
            return f"{self.subject} {self.number}"
        return self.code or ""

    def __str__(self) -> str:
        return f"{self.course_code} ({self.grade})"


class TermData(BaseModel):
    term_name: Optional[str] = None
    courses: List[StudentCourse] = Field(default_factory=list)
    gpa: Optional[float] = None
    cumulative_gpa: Optional[float] = None
    attempt_hours: Optional[float] = None
    passed_hours: Optional[float] = None
    earned_hours: Optional[float] = None
    quality_points: Optional[float] = None
    # Alternative field names from frontend
    semester: Optional[str] = None  # Alias for term_name
    status: Optional[str] = None  # Frontend sends this

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, values):
        # Handle alias: 'semester' -> 'term_name'
        if isinstance(values, dict):
            # Handle term_name vs semester
            if "semester" in values and "term_name" not in values:
                values["term_name"] = values["semester"]
            elif "semester" in values and not values.get("term_name"):
                values["term_name"] = values["semester"]
        return values


class StudentData(BaseModel):
    name: Optional[str] = None
    student_number: Optional[str] = None
    date_of_birth: Optional[str] = None
    campus: Optional[str] = None
    programme: Optional[ProgrammeData] = None
    terms: List[TermData] = Field(default_factory=list)
    overall_gpa: Optional[float] = None
    programme_summary: List[ProgrammeSummaryItem] = Field(default_factory=list)
    transcript_totals: Optional[TranscriptTotals] = None
    # Frontend alternative field names
    id: Optional[str] = None  # Alias for student_number
    gpa: Optional[float] = None  # Alias for overall_gpa
    creditsEarned: Optional[float] = None  # Direct credits value from frontend
    buckets: Optional[List[Any]] = None  # Frontend sends this

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, values):
        # Handle aliases: 'id' -> 'student_number', 'gpa' -> 'overall_gpa'
        if isinstance(values, dict):
            # Handle id vs student_number
            if "id" in values and "student_number" not in values:
                values["student_number"] = values["id"]

            # Handle gpa vs overall_gpa
            if "gpa" in values and "overall_gpa" not in values:
                values["overall_gpa"] = values["gpa"]

            # Handle programme format from frontend (simpler structure)
            if "programme" in values and isinstance(values["programme"], dict):
                prog = values["programme"]
                # Frontend sends {name, faculty, major, requiredCredits}
                # Backend expects {programme, faculty, major, ...}
                if "name" in prog and "programme" not in prog:
                    prog["programme"] = prog["name"]
        return values

    @property
    def total_credits(self) -> float:
        # Use creditsEarned if provided (from frontend), otherwise calculate from terms
        if self.creditsEarned is not None and self.creditsEarned > 0:
            return self.creditsEarned
        if not self.terms:
            return 0.0
        return sum(course.credits for course in self._iter_all_courses())

    @property
    def course_count(self) -> int:
        if not self.terms:
            return 0
        return sum(len(term.courses) for term in self.terms)

    @property
    def latest_term(self) -> Optional[TermData]:
        if not self.terms:
            return None
        return self.terms[-1]  # Assuming chronological order

    def _iter_all_courses(self) -> Generator[StudentCourse, None, None]:
        if not self.terms:
            return
        for term in self.terms:
            for course in term.courses:
                yield course

    @property
    def course_attempts(self) -> List[StudentCourse]:
        """
        Return every course attempt across all terms (flattened list).
        Does not deduplicate repeated attempts of the same course code.
        """
        return list(self._iter_all_courses())

    @property
    def passed_courses_latest(self) -> List[StudentCourse]:
        """
        Return unique passed courses (A-C with +/-), case-insensitive.
        Dedup policy: keep the latest passing attempt per course code.
        """
        if not self.terms:
            return []

        latest: Dict[str, StudentCourse] = {}
        for term in self.terms:
            for c in term.courses:
                grade = (c.grade or "").strip()
                if _PASSING_GRADE_RE.match(grade):
                    key = f"{c.subject.strip().upper()} {c.number}"
                    latest[key] = c

        return list(latest.values())

    @property
    def passed_courses_best(self) -> List[StudentCourse]:
        """
        Return unique passed courses (A-C with +/-), keeping the BEST grade.
        Tie-breaker: if grades are equal, keep the latest attempt by term order.
        """
        if not self.terms:
            return []

        # key -> (score, term_index, course)
        best: Dict[str, Tuple[int, int, StudentCourse]] = {}

        for ti, term in enumerate(self.terms):  # chronological
            for c in term.courses:
                g_raw = _normalize_grade(c.grade)
                if not _PASSING_GRADE_RE.match(g_raw):
                    continue
                score = _GRADE_SCORE.get(g_raw)
                if score is None:
                    continue  # safety: ignore weird-but-matching values

                key = f"{c.subject.strip().upper()} {c.number}"
                prev = best.get(key)

                if (
                    (prev is None)
                    or (score > prev[0])
                    or (score == prev[0] and ti > prev[1])
                ):
                    best[key] = (score, ti, c)

        return [t[2] for t in best.values()]

    @property
    def all_passed_courses_best(self) -> List[StudentCourse]:
        """Get all passed courses (best grade per course), sorted by credits descending."""
        if not self.terms:
            return []

        # key -> (score, term_index, course)
        best: Dict[str, Tuple[int, int, StudentCourse]] = {}

        for ti, term in enumerate(self.terms):
            for c in term.courses:
                g_raw = _normalize_grade(c.grade)
                if not _ALL_PASSING_GRADE_RE.match(g_raw):
                    continue

                # Special grades (EC, EX, CO) get score 0 for sorting
                # This ensures they don't override letter grades
                score = _GRADE_SCORE.get(g_raw, 0)

                key = f"{c.subject.strip().upper()} {c.number}"
                prev = best.get(key)

                if (
                    (prev is None)
                    or (score > prev[0])
                    or (score == prev[0] and ti > prev[1])
                ):
                    best[key] = (score, ti, c)

        # Sort by credits descending (highest first)
        courses = [t[2] for t in best.values()]
        courses.sort(key=lambda c: c.credits, reverse=True)
        return courses

    @property
    def passed_credits(self) -> float:
        # Use creditsEarned if provided and no terms data
        if self.creditsEarned is not None and self.creditsEarned > 0 and not self.terms:
            return self.creditsEarned
        return sum(c.credits for c in self.all_passed_courses_best)

    def __str__(self) -> str:
        # Basics
        name = self.name or "-"
        number = self.student_number or "-"
        campus = self.campus or "-"
        dob = self.date_of_birth or "-"

        # Programme one-liner
        prog = self.programme
        prog_bits = []
        if prog:
            for bit in (prog.degree, prog.programme, prog.major, prog.programme_level):
                if bit:
                    prog_bits.append(bit)
        programme_str = " | ".join(prog_bits) if prog_bits else "-"

        # Progress (e.g., "Credits: 45/120, Core: 8/12")
        if self.programme_summary:
            progress_str = ", ".join(
                f"{item.name}: {item.progress_numerator}/{item.progress_denominator}"
                for item in self.programme_summary
            )
        else:
            progress_str = "-"

        # Academics
        terms_n = len(self.terms or [])
        latest_term_name = self.latest_term.term_name if self.latest_term else "-"
        overall_gpa = f"{self.overall_gpa:.2f}" if self.overall_gpa is not None else "-"
        degree_gpa = (
            f"{prog.degree_gpa:.2f}" if (prog and prog.degree_gpa is not None) else "-"
        )
        courses_n = self.course_count
        total_credits = f"{self.total_credits:.1f}"
        passed_credits = f"{self.passed_credits:.1f}"

        return (
            "StudentData("
            f"name='{name}', number='{number}', campus='{campus}', dob='{dob}', "
            f"programme='{programme_str}', overall_gpa={overall_gpa}, degree_gpa={degree_gpa}, "
            f"terms={terms_n}, latest_term='{latest_term_name}', courses={courses_n}, "
            f"total_credits={total_credits}, passed_credits={passed_credits}, "
            f"progress=[{progress_str}]"
            ")"
        )
