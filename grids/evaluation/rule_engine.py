# Degree requirement evaluation engine
# Evaluates student progress against bucket and major requirements

from grids.parsing.grades import grade_to_quality_points, GRADE_SYNONYMS
from grids.evaluation.equivalencies import get_equivalent_codes
from typing import Dict, Set, Any, Optional, List
from collections import defaultdict
from pydantic import BaseModel, Field
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)
from ..models import Bucket, Major, Minor, Degree, StudentData, StudentCourse, Course
from ..models.evaluation import BUCKETS
from .filters import CourseFilter


class RequirementResult(BaseModel):
    """Result of evaluating a single requirement"""

    requirement_type: str
    requirement_name: str
    is_met: bool
    progress: Optional[str] = None
    details: Optional[str] = None
    courses_used: List[str] = Field(default_factory=list)
    courses_needed: List[str] = Field(default_factory=list)
    credits_earned: Optional[float] = None
    credits_required: Optional[float] = None
    gpa_achieved: Optional[float] = None
    gpa_required: Optional[float] = None
    # Exemption tracking (for EX grades - exemption without credit)
    exemptions_without_credits: List[str] = Field(default_factory=list)
    exemption_mappings: List[Dict[str, Any]] = Field(default_factory=list)


class BucketResult(BaseModel):
    """Result of evaluating a bucket requirement"""

    bucket_id: str
    bucket_name: str
    is_met: bool
    credits_earned: float
    credits_required: float
    contributes_to_degree_gpa: bool = True
    rule_results: List[RequirementResult] = Field(default_factory=list)
    overall_progress: str
    # Exemption tracking (aggregated from rules)
    exemptions_without_credits: List[str] = Field(default_factory=list)

    # KAREEM
    courses: List[StudentCourse] = Field(default_factory=list)
    courses_needed: List[str] = Field(default_factory=list)
    is_all_required: bool = False


class ComponentResult(BaseModel):
    """Result for major/minor component"""

    component_name: str
    component_type: str  # "major" or "minor"
    is_met: bool
    total_credits_earned: float
    total_credits_required: float
    bucket_results: List[BucketResult] = Field(default_factory=list)
    gpa_requirement_result: Optional[RequirementResult] = None


class DegreeEvaluationResult(BaseModel):
    """Complete evaluation result for a degree"""

    is_complete: bool
    overall_progress: str
    total_credits_earned: float
    total_credits_required: float
    overall_gpa: float

    # Component results
    major_results: List[ComponentResult] = Field(default_factory=list)
    minor_results: List[ComponentResult] = Field(default_factory=list)
    general_requirements: List[BucketResult] = Field(default_factory=list)

    # Graduation requirements
    graduation_requirements: Optional[Dict[str, Any]] = None

    # Summary of unmet requirements
    unmet_requirements: List[str] = Field(default_factory=list)
    next_steps: Dict[str, Any] = Field(default_factory=dict)


# ── Rule Evaluators ───────────────────────────────
def _evaluate_all_credits_from(
    student: StudentData,
    rule_data: Dict[str, Any],
    used_courses: Set[str],
    courses: List[Course],
) -> RequirementResult:
    result = RequirementResult(
        requirement_type="all_credits_from",
        requirement_name=rule_data.get("description", "-"),
        is_met=False,
    )

    if "list" in rule_data:
        required_courses = set(rule_data["list"])
    elif "filter" in rule_data:
        filter_obj = CourseFilter(**rule_data["filter"])
        required_courses = set([c.code for c in filter_obj.apply(courses)])
    else:
        return result

    completed_courses = {c.course_code for c in _get_effective_passed_courses(student)}

    courses_missing = []

    for req_code in required_courses:
        # Expand the requirement to include legacy alternatives
        eligible_equivalents = get_equivalent_codes(req_code)

        # Check if the student has ANY of the equivalents
        matches = eligible_equivalents & completed_courses

        if matches:
            for course_code in matches:
                course = _find_course(student, course_code)
                if course and course.grade.upper() == "EX":
                    if course_code not in result.exemptions_without_credits:
                        result.exemptions_without_credits.append(course_code)
                    # FIXED: Add EX to the main list so the Django template actually renders it
                    if course_code not in result.courses_used:
                        result.courses_used.append(course_code)
                else:
                    if course_code not in result.courses_used:
                        result.courses_used.append(course_code)
        else:
            courses_missing.append(req_code)

    result.courses_needed = courses_missing
    result.is_met = len(courses_missing) == 0
    result.progress = f"{len(required_courses) - len(courses_missing)}/{len(required_courses)} courses"

    return result


def _evaluate_min_credits_from(
    student: StudentData,
    rule_data: Dict[str, Any],
    used_courses: Set[str],
    courses: List[Course],
) -> RequirementResult:
    required_credits = rule_data.get("credits", 0)
    result = RequirementResult(
        requirement_type="min_credits_from",
        requirement_name=rule_data.get(
            "description", f"Minimum {required_credits} credits"
        ),
        is_met=False,
        credits_required=required_credits,
    )

    if "list" in rule_data:
        base_course_list = set(rule_data["list"])
    elif "filter" in rule_data:
        filter_obj = CourseFilter(**rule_data["filter"])
        base_course_list = set([c.code for c in filter_obj.apply(courses)])
    else:
        raise ValueError(
            f"No filter or list specified in min_credits_from rule: {rule_data}"
        )

    # Expand the allowed list to include legacy alternatives
    expanded_course_list = set()
    for code in base_course_list:
        expanded_course_list.update(get_equivalent_codes(code))

    eligible_courses = [
        c
        for c in _get_effective_passed_courses(student)
        if c.course_code in expanded_course_list and c.course_code not in used_courses
    ]

    max_per_subject = rule_data.get("max_per_subject")
    if max_per_subject:
        subject_credits = defaultdict(float)
        filtered_courses = []
        for course in eligible_courses:
            if subject_credits[course.subject] + course.credits <= max_per_subject:
                filtered_courses.append(course)
                subject_credits[course.subject] += course.credits
        eligible_courses = filtered_courses

    max_one_from = rule_data.get("max_one_from")
    if max_one_from:
        has_one = False
        filtered_courses = []
        for course in eligible_courses:
            if course.course_code in max_one_from:
                if not has_one:
                    filtered_courses.append(course)
                    has_one = True
            else:
                filtered_courses.append(course)
        eligible_courses = filtered_courses

    credits_earned = 0.0
    for course in eligible_courses:
        # FIXED: If the rule has enough credits, stop grabbing courses
        if credits_earned >= required_credits:
            break

        if course.grade.upper() == "EX":
            result.exemptions_without_credits.append(course.course_code)
            # FIXED: Add EX to the main list so the Django template actually renders it
            result.courses_used.append(course.course_code)
        else:
            result.courses_used.append(course.course_code)
            credits_earned += course.credits

    result.credits_earned = credits_earned
    result.is_met = credits_earned >= required_credits
    result.progress = f"{credits_earned:.1f}/{required_credits} credits"

    return result


def _evaluate_x_of(
    student: StudentData,
    rule_data: Dict[str, Any],
    used_courses: Set[str],
    courses: List[Course],
    flr_override: bool = False,
) -> RequirementResult:
    required_count = int(rule_data.get("x", 1))
    options = rule_data.get("options", [])

    result = RequirementResult(
        requirement_type="x_of",
        requirement_name=rule_data.get(
            "description", f"Complete {required_count} of {len(options)} options"
        ),
        is_met=False,
    )

    passed_best = _get_effective_passed_courses(student)
    passed_codes_best: Set[str] = {c.course_code for c in passed_best}

    satisfied_options: List[str] = []
    all_courses_used: List[str] = []

    for i, option in enumerate(options):
        option_name = option.get("name", f"Option {i + 1}")

        # When the admin override is active the student is NOT eligible for the
        # foreign language requirement, so they must take FOUN 1101 instead of
        # an FL substitute.  Skip the FL option entirely.
        if flr_override and "foreign language" in option_name.lower():
            continue

        min_credits = float(option.get("min_credits", 0.0))

        if "list" in option:
            base_eligible_codes = set(option["list"])
        elif "filter" in option:
            filter_obj = CourseFilter(**option["filter"])
            base_eligible_codes = {c.code for c in filter_obj.apply(courses)}
        else:
            raise ValueError(f"No filter or list specified in x_of rule: {option}")

        # Expand for equivalencies
        expanded_eligible_codes = set()
        for code in base_eligible_codes:
            expanded_eligible_codes.update(get_equivalent_codes(code))

        eligible_passed_courses = [
            c
            for c in passed_best
            if c.course_code in expanded_eligible_codes
            and c.course_code not in used_courses
        ]

        satisfied = False
        option_courses_used: List[str] = []

        if "list" in option and min_credits <= 0:
            # Must satisfy every required code (or its equivalent)
            has_all = True
            used_for_option = []

            for req_code in option["list"]:
                equivs = get_equivalent_codes(req_code)
                matches = equivs & passed_codes_best
                unused_matches = matches - used_courses
                if unused_matches:
                    used_for_option.append(list(unused_matches)[0])
                else:
                    has_all = False
                    break

            if has_all:
                satisfied = True
                option_courses_used = used_for_option
        else:
            earned = sum(c.credits for c in eligible_passed_courses)
            if earned >= max(min_credits, 0.0):
                satisfied = True
                option_courses_used = [c.course_code for c in eligible_passed_courses]

        if satisfied:
            satisfied_options.append(option_name)
            all_courses_used.extend(option_courses_used)

    result.is_met = len(satisfied_options) >= required_count
    result.courses_used = all_courses_used
    result.details = (
        f"Satisfied {len(satisfied_options)}/{required_count} options: {', '.join(satisfied_options)}"
        if satisfied_options
        else "No options satisfied"
    )
    result.progress = f"{len(satisfied_options)}/{required_count} options"

    return result


def _get_admit_year(student: StudentData) -> Optional[int]:
    """Extract the admit year from student's programme data"""
    if not student.programme or not student.programme.admit_term:
        return None

    admit_term = student.programme.admit_term
    # Admit term format is like "2023/2024 Semester I"
    # Extract the first year
    try:
        year_str = admit_term.split('/')[0]
        return int(year_str)
    except (ValueError, IndexError):
        return None


def _calculate_gpa(courses: List[StudentCourse]) -> float:
    """
    Calculate GPA strictly using the UWI grading scheme established in grades.py.
    Differentiates between GPA-contributing attempts and administrative credits.
    """
    if not courses:
        return 0.0

    total_points = 0.0
    gpa_hours = 0.0

    # Strict list of grades that do NOT factor into GPA math (Denominator = 0)
    # Note: UWI policy dictates 'FA' (Failed Absent) is a strict fail and SHOULD 
    # normally factor into GPA, but we map to your specific system rules.
    NON_GPA_GRADES = {
        "EX", "EC", "FMS", "I", "IP", "LW", "NR", 
        "P", "NP", "NV", "EI", "FMP", "CO", "AM", "AB", "DB", "V", "W"
    }

    for course in courses:
        grade = course.grade.upper().strip()

        # Check if the grade is academically recognized by the system
        if grade in GRADE_SYNONYMS:
            # Map legacy/synonym grades to their canonical versions (e.g., F1CW -> F1)
            canonical_grade = GRADE_SYNONYMS[grade]
            
            # If it is a GPA-contributing grade (A+, B, F1, F3, FO, etc.)
            if canonical_grade not in NON_GPA_GRADES:
                qp_multiplier = grade_to_quality_points(canonical_grade)
                total_points += (qp_multiplier * course.credits)
                gpa_hours += course.credits
        else:
            # Grade is not in GRADE_SYNONYMS at all — truly unknown
            logger.warning(
                f"Unrecognized grade '{grade}' on course {course.course_code}. "
                f"Skipping — contributes 0 quality points to GPA."
            )
            
    return total_points / gpa_hours if gpa_hours > 0 else 0.0


def _get_effective_passed_courses(student: StudentData) -> List[StudentCourse]:
    """Get all passed courses PLUS any EX (Exemption) courses."""
    courses = list(student.all_passed_courses_best)
    ex_codes = {c.course_code for c in courses}  # Track what's already there

    # Manually dig through terms to find hidden EX grades
    if hasattr(student, "terms") and student.terms:
        for term in student.terms:
            for c in term.courses:
                if c.grade and c.grade.upper() == "EX":
                    if c.course_code not in ex_codes:
                        courses.append(c)
                        ex_codes.add(c.course_code)
    return courses


def _find_course(student: StudentData, course_code: str) -> Optional[StudentCourse]:
    """Find a course in student's record"""
    for course in _get_effective_passed_courses(student):
        if course.course_code == course_code:
            return course
    return None


def _evaluate_foreign_language_requirement(student: StudentData, rule_data: Dict[str, Any], used_courses: Set[str], courses: List[Course], flr_override: bool = False) -> RequirementResult:
    """Evaluate foreign language requirement.

    By default every student admitted 2023+ is expected to complete an approved
    foreign-language course.  If an admin has reviewed the student's lower-level
    records and determined they are NOT eligible for the FLR (flr_override=True),
    the requirement is waived and the student must instead take FOUN 1101 in the
    Foundation bucket.
    """
    result = RequirementResult(
        requirement_type="foreign_language_requirement",
        requirement_name=rule_data.get('description', 'Foreign Language Requirement'),
        is_met=False
    )

    # Check if student was admitted in 2023 or later, otherwise ignore this requirement
    admit_year = _get_admit_year(student)
    if admit_year is not None and admit_year < 2023:
        result.is_met = True
        result.details = f"Requirement does not apply (admit year: {admit_year})"
        result.progress = "N/A"
        return result

    # Admin override: student is NOT eligible for FLR
    if flr_override:
        result.is_met = True
        result.details = "Student not eligible for foreign language requirement (verified by admin)"
        result.progress = "Exempt"
        return result

    # Get all passed courses (including EX exemptions)
    passed_courses = _get_effective_passed_courses(student)

    # Resolve approved courses from the rule's JSON data.
    # Every FLR bucket in buckets.json defines its own approved_courses list.
    # Hardcoded fallback only as a safety net for malformed bucket data.
    approved_courses = set(rule_data.get('approved_courses', []))
    if not approved_courses:
        approved_courses = {'CHIN 1007', 'FREN 1009', 'JAPA 1007', 'SPAN 1007', 'COCR 1052'}

    # Single pass: classify FL courses and accumulate credits in one loop
    # Only specific approved courses satisfy the FLR
    total_credits = 0.0
    courses_used = []
    exemptions = []

    for course in passed_courses:
        if course.course_code not in approved_courses:
            continue
        if course.grade.upper() == "EX":
            exemptions.append(course.course_code)
        else:
            courses_used.append(course.course_code)
            total_credits += course.credits

    has_any_foreign_language = bool(courses_used) or bool(exemptions)

    # Track exemptions separately
    result.exemptions_without_credits = exemptions
    result.exemption_mappings = [{"course": code, "reason": "Foreign Language Exemption"} for code in exemptions]

    result.is_met = has_any_foreign_language
    result.courses_used = courses_used
    result.credits_earned = total_credits
    result.credits_required = rule_data.get('credits', 3.0)

    if has_any_foreign_language:
        if exemptions:
            result.progress = f"Exempted ({len(exemptions)} EX course(s))"
            result.details = f"Exempted from foreign language requirement via {len(exemptions)} EX course(s)"
        else:
            result.progress = f"{total_credits:.1f}/{result.credits_required:.1f} credits"
            result.details = f"Completed {len(courses_used)} foreign language course(s)"
    else:
        result.progress = f"0/{result.credits_required:.1f} credits"
        result.details = "No foreign language courses completed"

    return result


def _calculate_applicable_credits(result) -> float:
    """
    Helper function: Calculates strictly the credits that apply toward the degree
    by capping the earned credits at the required limit for each bucket.
    This prevents excess Level I credits from masking deficits in Advanced buckets.
    """
    applicable_credits = 0.0
    
    # Sum capped credits from Major buckets
    for major in result.major_results:
        for bucket in major.bucket_results:
            earned = getattr(bucket, 'credits_earned', 0.0)
            required = getattr(bucket, 'credits_required', 0.0)
            applicable_credits += min(earned, required)
            
    # Sum capped credits from General/Foundation buckets
    for general in getattr(result, 'general_requirements', []):
        earned = getattr(general, 'credits_earned', 0.0)
        required = getattr(general, 'credits_required', 0.0)
        applicable_credits += min(earned, required)
        
    return applicable_credits


def _check_degree_completion(result) -> bool:
    """Check if all degree requirements are strictly met"""
    # 1. Check majors
    if not all(m.is_met for m in result.major_results):
        return False

    # 2. Check general requirements (Foundation courses, etc.)
    if getattr(result, 'general_requirements', None):
        if not all(g.is_met for g in result.general_requirements):
            return False

    # 3. Check graduation administrative requirements (e.g., minimum GPA)
    if getattr(result, 'graduation_requirements', None):
        for req_name, req_data in result.graduation_requirements.items():
            if not req_data.get("met", False):
                return False

    # Note: We removed the `total_credits_earned < total_credits_required` check. 
    # If all buckets are True, the degree is complete. Gross totals are irrelevant.
    return True


def _generate_progress_summary(result) -> str:
    """Generate a mathematically accurate progress summary"""
    applicable_credits = _calculate_applicable_credits(result)
    
    # Calculate percentage strictly based on applicable credits
    pct = (
        (applicable_credits / result.total_credits_required * 100)
        if result.total_credits_required > 0
        else 0.0
    )
    
    # Cap percentage at 100% just in case of rounding/float anomalies
    pct = min(pct, 100.0)
    
    status = "Complete" if result.is_complete else "In Progress"
    
    return f"{status}: {applicable_credits:.1f}/{result.total_credits_required} applicable credits ({pct:.1f}%), GPA: {result.overall_gpa:.2f}"


def _list_unmet_requirements(result) -> List[str]:
    """List all unmet requirements accurately"""
    unmet = []

    # Check major requirements
    for major in result.major_results:
        if not major.is_met:
            for bucket in major.bucket_results:
                if not bucket.is_met:
                    unmet.append(f"{major.component_name}: {bucket.bucket_name} ({getattr(bucket, 'overall_progress', 'Incomplete')})")

    # Check general requirements
    if getattr(result, 'general_requirements', None):
        for req in result.general_requirements:
            if not req.is_met:
                unmet.append(f"General: {req.bucket_name} ({getattr(req, 'overall_progress', 'Incomplete')})")

    # Check graduation requirements
    if getattr(result, 'graduation_requirements', None):
        for req_name, req_data in result.graduation_requirements.items():
            if not req_data.get("met", False):
                required_val = req_data.get('required', 'N/A')
                unmet.append(f"Graduation: {req_name} (need {required_val})")

    # Report incomplete minors (informational — not blocking graduation)
    for minor_result in getattr(result, 'minor_results', []):
        if not minor_result.is_met:
            for bucket in minor_result.bucket_results:
                if not bucket.is_met:
                    unmet.append(
                        f"Minor ({minor_result.component_name}): "
                        f"{bucket.bucket_name} ({getattr(bucket, 'overall_progress', 'Incomplete')})"
                    )

    return unmet


def _load_course_catalog() -> Dict[str, Dict[str, Any]]:
    """Load course_listing.json and return a flat dict keyed by course code.

    Returns:
        {"COMP 1601": {"title": "Computer Programming I", "credits": 3, "subject": "COMP", "level": 1}, ...}
    """
    catalog_path = Path(__file__).resolve().parent.parent / "data" / "course_listing.json"
    if not catalog_path.exists():
        return {}
    with open(catalog_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    catalog: Dict[str, Dict[str, Any]] = {}
    for subject, levels in raw.items():
        for level_key, courses in levels.items():
            # level_key is e.g. "level1" -> extract the digit
            level_num = int(level_key.replace("level", "")) if level_key.startswith("level") else 0
            for entry in courses:
                code = entry.get("code", "")
                if code:
                    catalog[code] = {
                        "title": entry.get("title", ""),
                        "credits": entry.get("credits", 0),
                        "subject": subject,
                        "level": level_num,
                    }
    return catalog


def _suggest_next_steps(result, student: StudentData) -> Dict[str, Any]:
    """Suggest actionable next steps by comparing the course catalog against
    the student's completed/used courses.

    Returns a dict with:
      - mandatory: list of course strings the student must take
      - elective_groups: list of dicts, each with bucket_name, credits_needed,
        num_courses, and courses (all available options)
      - notes: list of general advisory strings (e.g. GPA warning)
    """
    mandatory: List[str] = []
    elective_groups: List[Dict[str, Any]] = []
    notes: List[str] = []

    # -- Build lookup structures ------------------------------------------------
    catalog = _load_course_catalog()

    # All course codes the student has already passed (regardless of bucket usage)
    student_passed_codes: Set[str] = set()
    for term in student.terms:
        for c in term.courses:
            code = c.course_code
            if code:
                student_passed_codes.add(code)

    # All courses consumed by the evaluation (across every bucket)
    used_in_eval: Set[str] = set()
    all_buckets: List[BucketResult] = []
    for major in result.major_results:
        all_buckets.extend(major.bucket_results)
    if getattr(result, "general_requirements", None):
        all_buckets.extend(result.general_requirements)

    for bucket in all_buckets:
        for rule in getattr(bucket, "rule_results", []):
            for code in getattr(rule, "courses_used", []):
                used_in_eval.add(code)

    # Courses the student has taken or used — these are NOT available
    taken_codes = student_passed_codes | used_in_eval

    # Available catalog courses the student has NOT taken
    available_courses = {code: info for code, info in catalog.items() if code not in taken_codes}

    # -- Analyse each unmet bucket -----------------------------------------------
    def _process_unmet_bucket(bucket: BucketResult) -> None:

        if bucket.is_met:
            return

        earned = getattr(bucket, "credits_earned", 0.0)
        required = getattr(bucket, "credits_required", 0.0)
        shortfall = max(required - earned, 0.0)

        # Collect subjects and levels from courses already used in this bucket
        # to infer what subject/level area the bucket targets.
        bucket_subjects: Set[str] = set()
        bucket_levels: Set[int] = set()
        for rule in getattr(bucket, "rule_results", []):
            for code in getattr(rule, "courses_used", []):
                info = catalog.get(code)
                if info:
                    bucket_subjects.add(info["subject"])
                    bucket_levels.add(info["level"])

            # Also infer from courses_needed (these are explicit required courses)
            for code in getattr(rule, "courses_needed", []):
                info = catalog.get(code)
                if info:
                    bucket_subjects.add(info["subject"])
                    bucket_levels.add(info["level"])

        # 1. Specific missing required courses (from all_credits_from rules)
        required_credits_suggested = 0.0
        for rule in getattr(bucket, "rule_results", []):
            if not rule.is_met and getattr(rule, "courses_needed", None):
                for code in rule.courses_needed:
                    info = catalog.get(code)
                    if info:
                        mandatory.append(
                            f"{code} – {info['title']} ({info['credits']} cr)"
                        )
                        required_credits_suggested += info["credits"]
                    else:
                        mandatory.append(code)

        # 2. For remaining credit shortfall, list ALL available catalog courses
        #    that match the bucket's subject/level area so the student can choose.
        shortfall_remaining = shortfall - required_credits_suggested
        if shortfall_remaining > 0 and bucket_subjects:
            candidates = [
                (code, info)
                for code, info in available_courses.items()
                if info["subject"] in bucket_subjects
                and (not bucket_levels or info["level"] in bucket_levels)
            ]
            # Sort by level then code for stable ordering
            candidates.sort(key=lambda x: (x[1]["level"], x[0]))

            # Filter out courses already in mandatory list
            mandatory_codes = {m.split(" – ")[0].strip() for m in mandatory}
            candidates = [(c, i) for c, i in candidates if c not in mandatory_codes]

            if candidates:
                # Figure out how many 3-credit courses they'd need
                # (use ceiling of shortfall / typical credit weight)
                typical_credits = candidates[0][1]["credits"] if candidates else 3
                num_courses_needed = int(
                    -(-shortfall_remaining // typical_credits)  # ceiling division
                )

                course_list = [
                    f"{code} – {info['title']} ({info['credits']} cr)"
                    for code, info in candidates
                ]

                elective_groups.append({
                    "bucket_name": bucket.bucket_name,
                    "credits_needed": shortfall_remaining,
                    "num_courses": num_courses_needed,
                    "courses": course_list,
                })

    for major in result.major_results:
        for bucket in major.bucket_results:
            _process_unmet_bucket(bucket)

    if getattr(result, "general_requirements", None):
        for req in result.general_requirements:
            _process_unmet_bucket(req)

    # -- GPA check ---------------------------------------------------------------
    if result.overall_gpa < 2.0:
        notes.append("Improve overall GPA to meet minimum 2.0 requirement")

    # 4. Minor completion suggestions (informational)
    for minor_result in getattr(result, 'minor_results', []):
        if not minor_result.is_met:
            for bucket in minor_result.bucket_results:
                if not bucket.is_met:
                    for rule in getattr(bucket, 'rule_results', []):
                        if not rule.is_met and getattr(rule, 'courses_needed', None):
                            suggestions.append(
                                f"Minor ({minor_result.component_name}): "
                                f"Take required courses: {', '.join(rule.courses_needed)}"
                            )

    # Deduplicate suggestions (in case multiple rules triggered the same course suggestion)
    unique_suggestions = list(dict.fromkeys(suggestions))

    return {
        "mandatory": mandatory,
        "elective_groups": elective_groups,
        "notes": notes,
    }


class RequirementEvaluator:
    """Evaluates student progress against degree requirements."""

    def __init__(self, courses: List[Course]):
        self.courses = courses

    def evaluate_degree(
        self, student: StudentData, degree: Degree, flr_override: bool = False
    ) -> DegreeEvaluationResult:
        # Note: Course sorting by credits (descending) is now handled by the
        # all_passed_courses_best property in StudentData to ensure higher-credit
        # courses are matched first.

        # Store override flag so rule evaluators can access it
        self._flr_override = flr_override

        result = DegreeEvaluationResult(
            is_complete=False,
            overall_progress="",
            total_credits_earned=student.passed_credits,
            total_credits_required=degree.total_credits,
            overall_gpa=student.overall_gpa or 0.0,
        )

        global_used_courses = set()

        # Pass 0: Evaluate general requirements (FLR) first so that foreign-language
        # courses are added to used_courses before major/elective buckets run.
        for bucket in degree.general_requirements:
            bucket_result = self._evaluate_bucket(student, bucket, global_used_courses)
            result.general_requirements.append(bucket_result)

        # Initialize components and gather all buckets
        all_buckets_to_evaluate = []
        
        for major in degree.majors:
            major_result = ComponentResult(
                component_name=major.name,
                component_type="major",
                is_met=False,
                total_credits_earned=0,
                total_credits_required=major.total_credits,
            )
            result.major_results.append(major_result)
            for bucket in major.buckets:
                all_buckets_to_evaluate.append({"component": major_result, "bucket": bucket})

        for minor in degree.minors:
            minor_result = ComponentResult(
                component_name=minor.name,
                component_type="minor",
                is_met=False,
                total_credits_earned=0,
                total_credits_required=minor.total_credits,
            )
            result.minor_results.append(minor_result)
            for bucket in minor.buckets:
                all_buckets_to_evaluate.append({"component": minor_result, "bucket": bucket})

        def is_strict_core_bucket(bucket: Bucket) -> bool:
            return all(rule.get("type", "") == "all_credits_from" for rule in bucket.rules)

        bucket_results_map = {}

        # Pass 1: Strict Core Lock-in
        for item in all_buckets_to_evaluate:
            bucket = item["bucket"]
            if is_strict_core_bucket(bucket):
                bucket_result = self._evaluate_bucket(student, bucket, global_used_courses)
                bucket_results_map[bucket.id] = bucket_result

        # Pass 2: Flexible Electives
        for item in all_buckets_to_evaluate:
            bucket = item["bucket"]
            if not is_strict_core_bucket(bucket):
                bucket_result = self._evaluate_bucket(student, bucket, global_used_courses)
                bucket_results_map[bucket.id] = bucket_result

        # Finalize component results (preserving order, summing up credits and met status)
        for major, major_result in zip(degree.majors, result.major_results):
            major_result.bucket_results = [bucket_results_map[b.id] for b in major.buckets]
            major_result.total_credits_earned = sum(b.credits_earned for b in major_result.bucket_results)
            major_result.is_met = all(b.is_met for b in major_result.bucket_results) if major_result.bucket_results else True

        for minor, minor_result in zip(degree.minors, result.minor_results):
            minor_result.bucket_results = [bucket_results_map[b.id] for b in minor.buckets]
            minor_result.total_credits_earned = sum(b.credits_earned for b in minor_result.bucket_results)
            minor_result.is_met = all(b.is_met for b in minor_result.bucket_results) if minor_result.bucket_results else True

        # Map EX exemptions to replacement courses after all buckets evaluated
        all_bucket_results = []
        for major_result in result.major_results:
            all_bucket_results.extend(major_result.bucket_results)
        all_bucket_results.extend(result.general_requirements)
        
        # Include minor buckets in mapping too now that they are using the global pool
        for minor_result in result.minor_results:
            all_bucket_results.extend(minor_result.bucket_results)

        self._map_exemptions(student, all_bucket_results, global_used_courses)

        # Determine if degree is complete
        result.is_complete = _check_degree_completion(result)

        # Generate summary
        result.overall_progress = _generate_progress_summary(result)
        result.unmet_requirements = _list_unmet_requirements(result)
        result.next_steps = _suggest_next_steps(result)

        return result

    def _evaluate_bucket(
        self, student: StudentData, bucket: Bucket, used_courses: Set[str]
    ) -> BucketResult:
        """Evaluate a bucket requirement"""

        result = BucketResult(
            bucket_id=bucket.id,
            bucket_name=bucket.name,
            is_met=False,
            credits_earned=0.0,
            credits_required=bucket.credits_required,
            contributes_to_degree_gpa=bucket.contributes_to_degree_gpa,
            overall_progress="",
        )

        for rule in bucket.rules:
            rule_result = self._evaluate_rule(student, rule, used_courses)
            result.rule_results.append(rule_result)

            # Foreign language requirement is a pass/fail check, not credit-based.
            # FL courses are NOT locked into used_courses here — they will be
            # consumed by the Foundation x_of bucket where they actually contribute
            # credits.  This prevents the "double-consumption" bug where the FLR
            # bucket would steal the course before the Foundation bucket runs.
            # We also clear courses_used so the UI doesn't display them twice
            # (once in the FLR gate and again in the Foundation bucket).
            if rule_result.requirement_type == "foreign_language_requirement":
                result.credits_earned = max(
                    result.credits_earned, rule_result.credits_earned or 0.0
                )
                rule_result.courses_used = []
                continue

            # Track exactly what was consumed to prevent phantom frontend renders
            actually_consumed_for_rule = []

            # Add credits from courses used in this rule
            # Stop consuming courses once bucket reaches max_credits
            for course_code in rule_result.courses_used:
                # Stop if bucket already full
                if result.credits_earned >= bucket.credits_required:
                    break

                if course_code not in used_courses:
                    course = _find_course(student, course_code)
                    if course:
                        # Only grant credits if it's not an EX grade
                        if course.grade.upper() != "EX":
                            result.credits_earned += course.credits

                        used_courses.add(course_code)
                        actually_consumed_for_rule.append(course_code)

            # Override the rule's greedy list with reality
            rule_result.courses_used = actually_consumed_for_rule

        # Check if bucket is satisfied
        fl_rules = [
            r for r in result.rule_results
            if r.requirement_type == "foreign_language_requirement"
        ]
        if fl_rules:
            # Foreign language bucket: use the rule's own pass/fail result
            result.is_met = all(r.is_met for r in fl_rules)
        else:
            result.is_met = result.credits_earned >= bucket.credits_required and all(
                r.is_met
                for r in result.rule_results
                if r.requirement_type == "all_credits_from"
            )

        result.overall_progress = (
            f"{result.credits_earned:.1f}/{bucket.credits_required:.1f} credits"
        )
        return result

    def _evaluate_rule(
        self, student: StudentData, rule_data: Dict[str, Any], used_courses: Set[str]
    ) -> RequirementResult:
        """Evaluate a single rule"""
        rule_type = rule_data.get("type")

        if rule_type == "all_credits_from":
            return _evaluate_all_credits_from(
                student, rule_data, used_courses, self.courses
            )
        elif rule_type == "min_credits_from":
            return _evaluate_min_credits_from(
                student, rule_data, used_courses, self.courses
            )
        elif rule_type == "x_of":
            return _evaluate_x_of(student, rule_data, used_courses, self.courses, flr_override=self._flr_override)
        elif rule_type == 'foreign_language_requirement':
            return _evaluate_foreign_language_requirement(student, rule_data, used_courses, self.courses, flr_override=self._flr_override)
        raise ValueError(f"Unknown rule type: {rule_type}")



    def _map_exemptions(
        self,
        student: StudentData,
        bucket_results: List[BucketResult],
        used_courses: Set[str],
    ) -> None:
        """Map EX (Exemption without Credit) grades to replacement courses."""
        # Build pool of unused courses
        unused_courses = [
            c
            for c in student.all_passed_courses_best
            if c.course_code not in used_courses and c.grade.upper() != "EX"
        ]

        for bucket_result in bucket_results:
            # Collect all exemptions from rules in this bucket
            for rule_result in bucket_result.rule_results:
                for ex_code in rule_result.exemptions_without_credits:
                    ex_course = _find_course(student, ex_code)
                    if not ex_course:
                        continue

                    # Determine replacement level filter based on exempted course level
                    # Level 1 EX -> find Level 1 replacement (ANY_LVL1)
                    # Advanced EX -> find Advanced replacement (ANY_ADV, levels 2-3)
                    if hasattr(ex_course, "level"):
                        if ex_course.level == 1:
                            min_level, max_level = 1, 1
                        else:
                            min_level, max_level = 2, None  # Level 2+ (Advanced)
                    else:
                        # Fallback: use course number to determine level
                        course_num_str = (
                            str(ex_course.number)
                            if hasattr(ex_course, "number")
                            else ex_code.split()[-1]
                        )
                        first_digit = course_num_str[0] if course_num_str else "1"
                        if first_digit == "1":
                            min_level, max_level = 1, 1
                        else:
                            min_level, max_level = 2, None

                    # Find replacement course with same credits
                    replacement = None
                    for candidate in unused_courses:
                        # Check if candidate matches level requirement
                        cand_level = (
                            candidate.level if hasattr(candidate, "level") else None
                        )
                        if cand_level is None:
                            # Fallback: determine level from course number
                            cand_num_str = (
                                str(candidate.number)
                                if hasattr(candidate, "number")
                                else candidate.code.split()[-1]
                            )
                            cand_level = (
                                int(cand_num_str[0])
                                if cand_num_str and cand_num_str[0].isdigit()
                                else 1
                            )

                        # Check level match
                        level_match = cand_level >= min_level
                        if max_level is not None:
                            level_match = level_match and cand_level <= max_level

                        if candidate.credits == ex_course.credits and level_match:
                            replacement = candidate
                            break

                    if replacement:
                        # Safely get the course code depending on the object type
                        rep_code = (
                            replacement.course_code
                            if hasattr(replacement, "course_code")
                            else replacement.code
                        )

                        # Add replacement credits to bucket
                        bucket_result.credits_earned += replacement.credits
                        used_courses.add(rep_code)
                        unused_courses.remove(replacement)

                        # Record mapping in rule result
                        rule_result.exemption_mappings.append(
                            {
                                "exempted_course": ex_code,
                                "replacement_course": rep_code,
                                "credits": replacement.credits,
                            }
                        )

                        # Add to bucket's exemption tracking
                        if ex_code not in bucket_result.exemptions_without_credits:
                            bucket_result.exemptions_without_credits.append(ex_code)

                        # Recalculate bucket satisfaction
                        bucket_result.is_met = (
                            bucket_result.credits_earned
                            >= bucket_result.credits_required
                            and all(
                                r.is_met
                                for r in bucket_result.rule_results
                                if r.requirement_type == "all_credits_from"
                            )
                        )
                        bucket_result.overall_progress = f"{bucket_result.credits_earned:.1f}/{bucket_result.credits_required:.1f} credits"
