# Degree requirement evaluation engine
# Evaluates student progress against bucket and major requirements
# from .equivalencies import get_equivalent_codes # Added

from grids.parsing.grades import grade_to_quality_points, GRADE_SYNONYMS
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
                try:
                    qp_multiplier = grade_to_quality_points(canonical_grade)
                    total_points += (qp_multiplier * course.credits)
                    gpa_hours += course.credits
                except ValueError:
                    # Failsafe logging could go here for unmapped grades
                    continue

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

    return unmet


def _suggest_next_steps(result) -> List[str]:
    """Suggest all necessary next steps for degree completion"""
    suggestions = []
    
    missing_credits_total = 0.0

    # 1. Find missing required courses AND calculate actual credit deficits
    for major in result.major_results:
        for bucket in major.bucket_results:
            if not bucket.is_met:
                # Add specific missing courses
                for rule in getattr(bucket, 'rule_results', []):
                    if not rule.is_met and getattr(rule, 'courses_needed', None):
                        suggestions.append(f"Take required courses: {', '.join(rule.courses_needed)}")
                        # Removed the break statement here so we catch all rules
                
                # Aggregate credit deficits at the bucket level instead of gross totals
                earned = getattr(bucket, 'credits_earned', 0.0)
                required = getattr(bucket, 'credits_required', 0.0)
                if earned < required:
                    missing_credits_total += (required - earned)

    # Do the same for general requirements
    if getattr(result, 'general_requirements', None):
        for req in result.general_requirements:
            if not req.is_met:
                earned = getattr(req, 'credits_earned', 0.0)
                required = getattr(req, 'credits_required', 0.0)
                if earned < required:
                    missing_credits_total += (required - earned)

    # 2. Append accurate credit shortfall
    if missing_credits_total > 0:
        suggestions.append(f"Need {missing_credits_total:.1f} more applicable credits across unmet buckets")

    # 3. Check GPA requirements
    if result.overall_gpa < 2.0:
        suggestions.append("Improve overall GPA to meet minimum 2.0 requirement")

    # Deduplicate suggestions (in case multiple rules triggered the same course suggestion)
    unique_suggestions = list(dict.fromkeys(suggestions))

    return unique_suggestions


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
