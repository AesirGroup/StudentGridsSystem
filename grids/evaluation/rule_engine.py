# Degree requirement evaluation engine
# Evaluates student progress against bucket and major requirements
# from .equivalencies import get_equivalent_codes # Added

from grids.evaluation.equivalencies import get_equivalent_codes
from typing import Dict, Set, Any, Optional, List
from collections import defaultdict
from pydantic import BaseModel, Field

from ..models import Bucket, Major, Degree, StudentData, StudentCourse, Course
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
    next_steps: List[str] = Field(default_factory=list)


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


def _calculate_gpa(courses: List[StudentCourse]) -> float:
    """Calculate GPA for a list of courses"""
    if not courses:
        return 0.0

    grade_points = {
        "A+": 4.3,
        "A": 4.0,
        "A-": 3.7,
        "B+": 3.3,
        "B": 3.0,
        "B-": 2.7,
        "C+": 2.3,
        "C": 2.0,
        "C-": 1.7,
        "D+": 1.3,
        "D": 1.0,
        "D-": 0.7,
        "F": 0.0,
    }

    total_points = 0.0
    total_credits = 0.0

    for course in courses:
        grade = course.grade.upper().strip()
        if grade in grade_points:
            total_points += grade_points[grade] * course.credits
            total_credits += course.credits

    return total_points / total_credits if total_credits > 0 else 0.0


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


def _check_degree_completion(result: DegreeEvaluationResult) -> bool:
    """Check if all degree requirements are met"""
    # Check majors
    if not all(m.is_met for m in result.major_results):
        return False

    # Check general requirements
    if not all(g.is_met for g in result.general_requirements):
        return False

    # Check graduation requirements
    if result.graduation_requirements:
        for req_name, req_data in result.graduation_requirements.items():
            if not req_data.get("met", False):
                return False

    # Check total credits
    if result.total_credits_earned < result.total_credits_required:
        return False

    return True


def _generate_progress_summary(result: DegreeEvaluationResult) -> str:
    """Generate a progress summary"""
    pct = (
        (result.total_credits_earned / result.total_credits_required * 100)
        if result.total_credits_required > 0
        else 0
    )
    status = "Complete" if result.is_complete else "In Progress"
    return f"{status}: {result.total_credits_earned:.1f}/{result.total_credits_required} credits ({pct:.1f}%), GPA: {result.overall_gpa:.2f}"


def _list_unmet_requirements(result: DegreeEvaluationResult) -> List[str]:
    """List all unmet requirements"""
    unmet = []

    # Check major requirements
    for major in result.major_results:
        if not major.is_met:
            for bucket in major.bucket_results:
                if not bucket.is_met:
                    unmet.append(
                        f"{major.component_name}: {bucket.bucket_name} ({bucket.overall_progress})"
                    )

    # Check general requirements
    for req in result.general_requirements:
        if not req.is_met:
            unmet.append(f"General: {req.bucket_name} ({req.overall_progress})")

    # Check graduation requirements
    if result.graduation_requirements:
        for req_name, req_data in result.graduation_requirements.items():
            if not req_data.get("met", False):
                unmet.append(
                    f"Graduation: {req_name} (need {req_data.get('required')})"
                )

    return unmet


def _suggest_next_steps(result: DegreeEvaluationResult) -> List[str]:
    """Suggest next steps for degree completion"""
    suggestions = []

    # Find missing required courses
    for major in result.major_results:
        for bucket in major.bucket_results:
            for rule in bucket.rule_results:
                if not rule.is_met and rule.courses_needed:
                    suggestions.append(
                        f"Take required courses: {', '.join(rule.courses_needed[:3])}"
                    )
                    break

    # Check credit shortfalls
    credits_needed = result.total_credits_required - result.total_credits_earned
    if credits_needed > 0:
        suggestions.append(f"Need {credits_needed:.1f} more credits")

    # Check GPA requirements
    if result.overall_gpa < 2.0:
        suggestions.append("Improve overall GPA to meet minimum 2.0 requirement")

    # return suggestions[:5]  # Limit to top 5 suggestions
    return suggestions


class RequirementEvaluator:
    """Evaluates student progress against degree requirements."""

    def __init__(self, courses: List[Course]):
        self.courses = courses

    def evaluate_degree(
        self, student: StudentData, degree: Degree
    ) -> DegreeEvaluationResult:
        # Note: Course sorting by credits (descending) is now handled by the
        # all_passed_courses_best property in StudentData to ensure higher-credit
        # courses are matched first.

        # Inject dynamic requirements for EC grade exemptions
        self._inject_ec_requirements(student, degree)

        result = DegreeEvaluationResult(
            is_complete=False,
            overall_progress="",
            total_credits_earned=student.passed_credits,
            total_credits_required=degree.total_credits,
            overall_gpa=student.overall_gpa or 0.0,
        )

        used_courses = set()

        for major in degree.majors:
            major_result = self._evaluate_major(student, major, used_courses)
            result.major_results.append(major_result)

        for bucket in degree.general_requirements:
            bucket_result = self._evaluate_bucket(student, bucket, used_courses)
            result.general_requirements.append(bucket_result)

        # Map EX exemptions to replacement courses after all buckets evaluated
        all_bucket_results = []
        for major_result in result.major_results:
            all_bucket_results.extend(major_result.bucket_results)
        all_bucket_results.extend(result.general_requirements)

        self._map_exemptions(student, all_bucket_results, used_courses)

        # Determine if degree is complete
        result.is_complete = _check_degree_completion(result)

        # Generate summary
        result.overall_progress = _generate_progress_summary(result)
        result.unmet_requirements = _list_unmet_requirements(result)
        result.next_steps = _suggest_next_steps(result)

        return result

    def _evaluate_major(
        self, student: StudentData, major: Major, used_courses: Set[str]
    ) -> ComponentResult:
        """Evaluate major requirements"""
        result = ComponentResult(
            component_name=major.name,
            component_type="major",
            is_met=False,
            total_credits_earned=0,
            total_credits_required=major.total_credits,
        )

        for bucket in major.buckets:
            bucket_result = self._evaluate_bucket(student, bucket, used_courses)
            result.bucket_results.append(bucket_result)
            result.total_credits_earned += bucket_result.credits_earned

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
            overall_progress="",
        )

        for rule in bucket.rules:
            rule_result = self._evaluate_rule(student, rule, used_courses)
            result.rule_results.append(rule_result)

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
            return _evaluate_x_of(student, rule_data, used_courses, self.courses)
        raise ValueError(f"Unknown rule type: {rule_type}")

    def _inject_ec_requirements(self, student: StudentData, degree: Degree) -> None:
        """Add replacement requirements for EC (Exemption with Credit) grades."""
        for course in student.all_passed_courses_best:
            if course.course_code == "MATH 1115" and course.grade.upper() == "EC":
                # Add replacement requirement for EC exemption
                ec_bucket = Bucket(
                    id=f"EC_REPLACEMENT_{course.course_code}",
                    name=f"Level 1 Credits for {course.course_code} Exemption (EC)",
                    credits_required=course.credits,
                    description=f"Replacement credits for {course.course_code} EC exemption",
                    rules=[
                        {
                            "type": "min_credits_from",
                            "credits": course.credits,
                            "description": "Level 1 elective for EC replacement",
                            "filter": {
                                "min_level": 1,
                                "max_level": 1,
                                "exclude_codes": [
                                    "COMP 1011",
                                    "FOUN 1101",
                                    "FOUN 1105",
                                    "FOUN 1301",
                                    "MATH 1115",
                                ],
                            },
                        }
                    ],
                )

                # Insert into degree's major buckets (if major exists)
                if degree.majors:
                    degree.majors[0].buckets.append(ec_bucket)

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
