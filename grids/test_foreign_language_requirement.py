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

    # Test 3: Student with French course should meet requirement
    total_tests += 1
    courses_list = [create_course("FREN", 101, "French I", "A")]
    student = create_student(admit_term="2023/2024 Semester I", courses=courses_list)
    result = _evaluate_foreign_language_requirement(student, rule_data, used_courses, courses)
    if result.is_met and ("FREN 101" in result.courses_used):
        print("✓ Test 3 passed: Student with French course meets requirement")
        tests_passed += 1
    else:
        print("✗ Test 3 failed: Student with French course should meet requirement")

    # Test 4: Student with EX grade should meet requirement
    total_tests += 1
    courses_list = [create_course("SPAN", 101, "Spanish I", "EX")]
    student = create_student(admit_term="2023/2024 Semester I", courses=courses_list)
    result = _evaluate_foreign_language_requirement(student, rule_data, used_courses, courses)
    if result.is_met and "SPAN 101" in result.exemptions_without_credits:
        print("✓ Test 4 passed: Student with EX grade meets requirement")
        tests_passed += 1
    else:
        print("✗ Test 4 failed: Student with EX grade should meet requirement")

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

    # Test 6: Student with multiple foreign language courses
    total_tests += 1
    courses_list = [
        create_course("FREN", 101, "French I", "A"),
        create_course("SPAN", 102, "Spanish I", "B"),
        create_course("GERM", 103, "German I", "A-")
    ]
    student = create_student(admit_term="2023/2024 Semester I", courses=courses_list)
    result = _evaluate_foreign_language_requirement(student, rule_data, used_courses, courses)
    if result.is_met and len(result.courses_used) == 3 and result.credits_earned == 9.0:
        print("✓ Test 6 passed: Student with multiple foreign language courses meets requirement")
        tests_passed += 1
    else:
        print("✗ Test 6 failed: Student with multiple foreign language courses should meet requirement")

    # Test 7: Student with failing foreign language course should not meet requirement
    total_tests += 1
    courses_list = [create_course("FREN", 101, "French I", "F")]
    student = create_student(admit_term="2023/2024 Semester I", courses=courses_list)
    result = _evaluate_foreign_language_requirement(student, rule_data, used_courses, courses)
    if not result.is_met:
        print("✓ Test 7 passed: Student with failing foreign language course does not meet requirement")
        tests_passed += 1
    else:
        print("✗ Test 7 failed: Student with failing foreign language course should not meet requirement")

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