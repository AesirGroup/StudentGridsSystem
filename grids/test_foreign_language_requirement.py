import sys
from pathlib import Path

# Add the project root and grids module to the path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

# Configure Django settings
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'student_grids.settings')
# Set required environment variables for testing
os.environ.setdefault('SECRET_KEY', 'test-secret-key-for-testing-only')
os.environ.setdefault('DEBUG', 'True')
os.environ.setdefault('DATABASE_URL', 'sqlite:///db.sqlite3')
import django
django.setup()

from grids.models.student import StudentData, StudentCourse, TermData, ProgrammeData
from grids.evaluation.rule_engine import _evaluate_foreign_language_requirement


def create_student(admit_term=None, courses=None):
    """Helper to create a StudentData instance"""
    programme = ProgrammeData(admit_term=admit_term) if admit_term else None
    terms = []

    if courses:
        term = TermData()
        term.courses = courses
        terms = [term]

    return StudentData(
        name="Test Student",
        student_number="12345",
        programme=programme,
        terms=terms
    )


def create_course(subject, number, title, grade, credits=3.0):
    """Helper to create a StudentCourse instance"""
    return StudentCourse(
        subject=subject,
        number=number,
        title=title,
        grade=grade,
        credits=credits
    )


def test_foreign_language_requirement():
    """Run comprehensive tests for the foreign language requirement"""
    print("=" * 60)
    print("Testing Foreign Language Requirement")
    print("=" * 60)

    rule_data = {
        'description': 'Foreign Language Requirement',
        'credits': 3.0
    }
    used_courses = set()
    courses = []  # Empty course catalog

    tests_passed = 0
    total_tests = 0

    # Test 1: Student admitted before 2023 should automatically meet requirement
    total_tests += 1
    student = create_student(admit_term="2022/2023 Semester I")
    result = _evaluate_foreign_language_requirement(student, rule_data, used_courses, courses)
    if result.is_met and result.details == "Requirement does not apply (admit year: 2022)":
        print("✓ Test 1 passed: Student admitted before 2023 automatically meets requirement")
        tests_passed += 1
    else:
        print("✗ Test 1 failed: Student admitted before 2023 should automatically meet requirement")

    # Test 2: Student admitted in 2023+ with no foreign language courses should not meet requirement
    total_tests += 1
    student = create_student(admit_term="2023/2024 Semester I")
    result = _evaluate_foreign_language_requirement(student, rule_data, used_courses, courses)
    if not result.is_met and "No foreign language courses completed" in result.details:
        print("✓ Test 2 passed: Student with no foreign language courses does not meet requirement")
        tests_passed += 1
    else:
        print("✗ Test 2 failed: Student with no foreign language courses should not meet requirement")

    # Test 3: Student with approved French course (FREN 1009) should meet requirement
    total_tests += 1
    courses_list = [create_course("FREN", 1009, "French for Beginners I (Blended)", "A")]
    student = create_student(admit_term="2023/2024 Semester I", courses=courses_list)
    result = _evaluate_foreign_language_requirement(student, rule_data, used_courses, courses)
    if result.is_met and ("FREN 1009" in result.courses_used):
        print("✓ Test 3 passed: Student with approved French course meets requirement")
        tests_passed += 1
    else:
        print(f"✗ Test 3 failed: Student with approved French course should meet requirement (is_met={result.is_met}, courses_used={result.courses_used})")

    # Test 4: Student with EX grade on approved course should meet requirement
    total_tests += 1
    courses_list = [create_course("SPAN", 1007, "Spanish for Beginners I (Blended)", "EX")]
    student = create_student(admit_term="2023/2024 Semester I", courses=courses_list)
    result = _evaluate_foreign_language_requirement(student, rule_data, used_courses, courses)
    if result.is_met and "SPAN 1007" in result.exemptions_without_credits:
        print("✓ Test 4 passed: Student with EX grade on approved course meets requirement")
        tests_passed += 1
    else:
        print(f"✗ Test 4 failed: Student with EX grade on approved course should meet requirement (is_met={result.is_met}, exemptions={result.exemptions_without_credits})")

    # Test 5: Student with non-foreign language course should not meet requirement
    total_tests += 1
    courses_list = [create_course("COMP", 1600, "Computer Science I", "A")]
    student = create_student(admit_term="2023/2024 Semester I", courses=courses_list)
    result = _evaluate_foreign_language_requirement(student, rule_data, used_courses, courses)
    if not result.is_met:
        print("✓ Test 5 passed: Student with only non-foreign language courses does not meet requirement")
        tests_passed += 1
    else:
        print("✗ Test 5 failed: Student with only non-foreign language courses should not meet requirement")

    # Test 6: Student with multiple approved foreign language courses
    total_tests += 1
    courses_list = [
        create_course("FREN", 1009, "French for Beginners I (Blended)", "A"),
        create_course("SPAN", 1007, "Spanish for Beginners I (Blended)", "B"),
        create_course("CHIN", 1007, "Chinese (Mandarin) Beginners I (Blended)", "A-")
    ]
    student = create_student(admit_term="2023/2024 Semester I", courses=courses_list)
    result = _evaluate_foreign_language_requirement(student, rule_data, used_courses, courses)
    if result.is_met and len(result.courses_used) == 3 and result.credits_earned == 9.0:
        print("✓ Test 6 passed: Student with multiple approved foreign language courses meets requirement")
        tests_passed += 1
    else:
        print(f"✗ Test 6 failed: Student with multiple approved courses should meet requirement (is_met={result.is_met}, courses_used={result.courses_used}, credits={result.credits_earned})")

    # Test 7: Student with failing approved foreign language course should not meet requirement
    total_tests += 1
    courses_list = [create_course("FREN", 1009, "French for Beginners I (Blended)", "F")]
    student = create_student(admit_term="2023/2024 Semester I", courses=courses_list)
    result = _evaluate_foreign_language_requirement(student, rule_data, used_courses, courses)
    if not result.is_met:
        print("✓ Test 7 passed: Student with failing approved language course does not meet requirement")
        tests_passed += 1
    else:
        print("✗ Test 7 failed: Student with failing approved language course should not meet requirement")

    # ── Hybrid Method 1: Heuristic Proxy (FOUN 1101 XOR) ─────
    # Test 8: Student who passed FOUN 1101 but has NO foreign language course
    #         → FLR should be inferred as met (CSEC/CAPE holder took Caribbean Civ)
    total_tests += 1
    courses_list = [create_course("FOUN", 1101, "Caribbean Civilisation", "B+")]
    student = create_student(admit_term="2023/2024 Semester I", courses=courses_list)
    result = _evaluate_foreign_language_requirement(student, rule_data, set(), courses)
    if result.is_met and "FOUN 1101" in result.details:
        print("✓ Test 8 passed: FOUN 1101 heuristic proxy infers CSEC/CAPE exemption")
        tests_passed += 1
    else:
        print(f"✗ Test 8 failed: FOUN 1101 heuristic should infer exemption (is_met={result.is_met}, details={result.details})")

    # Test 9: Student who FAILED FOUN 1101 and has no FL course → should NOT meet
    total_tests += 1
    courses_list = [create_course("FOUN", 1101, "Caribbean Civilisation", "F")]
    student = create_student(admit_term="2023/2024 Semester I", courses=courses_list)
    result = _evaluate_foreign_language_requirement(student, rule_data, set(), courses)
    if not result.is_met:
        print("✓ Test 9 passed: Failing FOUN 1101 does not trigger heuristic")
        tests_passed += 1
    else:
        print("✗ Test 9 failed: Failing FOUN 1101 should not trigger heuristic")

    # ── Hybrid Method 2: Advisor Override ─────────────────────
    # Test 10: Advisor override should immediately satisfy FLR
    total_tests += 1
    student = create_student(admit_term="2023/2024 Semester I")
    result = _evaluate_foreign_language_requirement(student, rule_data, set(), courses, flr_override=True)
    if result.is_met and "verified by advisor" in result.details.lower():
        print("✓ Test 10 passed: Advisor override satisfies FLR")
        tests_passed += 1
    else:
        print(f"✗ Test 10 failed: Advisor override should satisfy FLR (is_met={result.is_met}, details={result.details})")

    # Test 11: Advisor override=False with no courses → should NOT meet
    total_tests += 1
    student = create_student(admit_term="2023/2024 Semester I")
    result = _evaluate_foreign_language_requirement(student, rule_data, set(), courses, flr_override=False)
    if not result.is_met:
        print("✓ Test 11 passed: No override + no courses = unmet")
        tests_passed += 1
    else:
        print("✗ Test 11 failed: No override + no courses should be unmet")

    # Test 12: Student with a language subject course NOT in approved list should NOT meet requirement
    total_tests += 1
    courses_list = [create_course("FREN", 2001, "Intermediate French", "A")]
    student = create_student(admit_term="2023/2024 Semester I", courses=courses_list)
    result = _evaluate_foreign_language_requirement(student, rule_data, set(), courses)
    if not result.is_met:
        print("✓ Test 12 passed: Non-approved language course (FREN 2001) does not meet requirement")
        tests_passed += 1
    else:
        print(f"✗ Test 12 failed: Non-approved language course should not meet requirement (is_met={result.is_met}, courses_used={result.courses_used})")

    # Test 13: Student with each approved course individually should meet requirement
    approved = [
        ("CHIN", 1007, "Chinese (Mandarin) Beginners I (Blended)"),
        ("FREN", 1009, "French for Beginners I (Blended)"),
        ("JAPA", 1007, "Japanese for Beginners I (Blended)"),
        ("SPAN", 1007, "Spanish for Beginners I (Blended)"),
        ("COCR", 1052, "Introduction to Sign Language"),
    ]
    all_approved_passed = True
    for subj, num, title in approved:
        total_tests += 1
        courses_list = [create_course(subj, num, title, "B+")]
        student = create_student(admit_term="2023/2024 Semester I", courses=courses_list)
        result = _evaluate_foreign_language_requirement(student, rule_data, set(), courses)
        code = f"{subj} {num}"
        if result.is_met and code in result.courses_used:
            print(f"✓ Test 13 ({code}) passed: Approved course meets requirement")
            tests_passed += 1
        else:
            print(f"✗ Test 13 ({code}) failed: Approved course should meet requirement (is_met={result.is_met}, courses_used={result.courses_used})")
            all_approved_passed = False

    # Test 14: Non-approved course from each language subject should NOT meet
    non_approved = [
        ("CHIN", 2001, "Intermediate Chinese"),
        ("FREN", 1001, "Old French Course"),
        ("JAPA", 2007, "Advanced Japanese"),
        ("SPAN", 2010, "Spanish Literature"),
        ("COCR", 1001, "Other Sign Language Course"),
    ]
    for subj, num, title in non_approved:
        total_tests += 1
        courses_list = [create_course(subj, num, title, "A")]
        student = create_student(admit_term="2023/2024 Semester I", courses=courses_list)
        result = _evaluate_foreign_language_requirement(student, rule_data, set(), courses)
        code = f"{subj} {num}"
        if not result.is_met:
            print(f"✓ Test 14 ({code}) passed: Non-approved language course does not meet requirement")
            tests_passed += 1
        else:
            print(f"✗ Test 14 ({code}) failed: Non-approved language course should NOT meet requirement (is_met={result.is_met}, courses_used={result.courses_used})")

    print("=" * 60)
    print(f"Tests passed: {tests_passed}/{total_tests}")
    if tests_passed == total_tests:
        print("🎉 All tests passed!")
        return True
    else:
        print("❌ Some tests failed!")
        return False


if __name__ == "__main__":
    success = test_foreign_language_requirement()
    sys.exit(0 if success else 1)