"""
Validation script for the grids module.
Tests imports, model creation, parsing, filtering, and evaluation.
"""

import json
import sys
from pathlib import Path

def test_imports():
    """Test that all required imports work."""
    print("=" * 60)
    print("1. Testing imports...")
    print("=" * 60)

    try:
        from grids import (
            DocType,
            Course,
            ProgrammeData, ProgrammeSummaryItem,
            TranscriptTotalRow, TranscriptTotals,
            StudentCourse, TermData, StudentData,
            Bucket, Major, Degree,
            EvaluationRequest, EvaluationResponse,
            BUCKETS, MAJORS,
            parse_text, identify_doc_type,
        )
        from grids.evaluation import (
            RequirementEvaluator,
            CourseFilter,
            RequirementResult,
            BucketResult,
            ComponentResult,
            DegreeEvaluationResult,
        )
        print("   All imports successful!")
        return True
    except ImportError as e:
        print(f"   Import error: {e}")
        return False


def test_course_creation():
    """Test Course dataclass creation."""
    print("\n" + "=" * 60)
    print("2. Testing Course creation...")
    print("=" * 60)

    from grids import Course

    # Test basic creation
    course = Course(
        subject="COMP",
        number=1600,
        title="Introduction to Computing",
        credits=3.0,
        department="Computing",
        faculty="Science & Technology"
    )

    print(f"   Created: {course.code} - {course.title}")
    print(f"   Level: {course.level}, Credits: {course.credits}")

    assert course.code == "COMP 1600", f"Expected 'COMP 1600', got '{course.code}'"
    assert course.level == 1, f"Expected level 1, got {course.level}"
    print("   Course creation works!")
    return True


def load_courses_from_json():
    """Load courses from the JSON file."""
    from grids import Course

    json_path = Path(__file__).parent.parent / "backend" / "dataset" / "data" / "courses.json"
    if not json_path.exists():
        print(f"   Warning: courses.json not found at {json_path}")
        return []

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    courses = []
    for c in data.get('courses', []):
        courses.append(Course(
            subject=c['subject'],
            number=c['number'],
            title=c['title'],
            credits=float(c['credits']),
            description=c.get('description', ''),
            department=c.get('department', ''),
            faculty=c.get('faculty', ''),
            is_active=c.get('is_active', True),
            tags=c.get('tags', [])
        ))

    return courses


def test_course_filter():
    """Test CourseFilter with in-memory courses."""
    print("\n" + "=" * 60)
    print("3. Testing CourseFilter...")
    print("=" * 60)

    from grids.evaluation import CourseFilter

    courses = load_courses_from_json()
    if not courses:
        print("   No courses loaded, creating test courses...")
        from grids import Course
        courses = [
            Course(subject="COMP", number=1600, title="Intro to Computing", credits=3.0),
            Course(subject="COMP", number=1601, title="Programming I", credits=3.0),
            Course(subject="COMP", number=2601, title="Data Structures", credits=3.0),
            Course(subject="MATH", number=1115, title="Calculus I", credits=3.0),
            Course(subject="FOUN", number=1101, title="Caribbean Civilization", credits=3.0),
        ]

    print(f"   Loaded {len(courses)} courses")

    # Test filter by subject
    filter1 = CourseFilter(subjects=["COMP"])
    comp_courses = filter1.apply(courses)
    print(f"   COMP courses: {len(comp_courses)}")

    # Test filter by level
    filter2 = CourseFilter(min_level=2)
    advanced_courses = filter2.apply(courses)
    print(f"   Advanced (level 2+) courses: {len(advanced_courses)}")

    # Test combined filter
    filter3 = CourseFilter(subjects=["COMP"], min_level=1, max_level=1)
    comp_level1 = filter3.apply(courses)
    print(f"   COMP Level 1 courses: {len(comp_level1)}")

    print("   CourseFilter works!")
    return True


def test_student_data():
    """Test StudentData creation with courses."""
    print("\n" + "=" * 60)
    print("4. Testing StudentData creation...")
    print("=" * 60)

    from grids import StudentData, ProgrammeData, TermData, StudentCourse

    # Create a student with courses
    student = StudentData(
        name="John Doe",
        student_number="816012345",
        date_of_birth="01-Jan-2000",
        campus="St. Augustine",
        programme=ProgrammeData(
            admit_term="2020/2021 Semester I",
            programme_level="Undergraduate",
            degree="Bachelor of Science",
            programme="Computer Science (Special)",
            faculty="Science & Technology",
            department="Computing",
            major="Computer Science",
            degree_gpa=3.2,
        ),
        terms=[
            TermData(
                term_name="2020/2021 Semester I",
                courses=[
                    StudentCourse(subject="COMP", number=1600, title="Intro", credits=3.0, grade="A", points=12.0),
                    StudentCourse(subject="COMP", number=1601, title="Prog I", credits=3.0, grade="B+", points=9.9),
                    StudentCourse(subject="MATH", number=1115, title="Calc I", credits=3.0, grade="A-", points=11.1),
                ],
                gpa=3.67
            ),
            TermData(
                term_name="2020/2021 Semester II",
                courses=[
                    StudentCourse(subject="COMP", number=1602, title="Prog II", credits=3.0, grade="B", points=9.0),
                    StudentCourse(subject="COMP", number=1603, title="OOP", credits=3.0, grade="A", points=12.0),
                    StudentCourse(subject="FOUN", number=1101, title="CC", credits=3.0, grade="B-", points=8.1),
                ],
                gpa=3.23
            ),
        ],
        overall_gpa=3.45,
        programme_summary=[]
    )

    print(f"   Created student: {student.name} ({student.student_number})")
    print(f"   Programme: {student.programme.programme}")
    print(f"   Terms: {len(student.terms)}")

    # Test computed properties
    all_courses = student.course_attempts  # All course attempts (flattened)
    passed = student.all_passed_courses_best
    credits = student.passed_credits

    print(f"   All course attempts: {len(all_courses)}")
    print(f"   Passed courses (best attempts): {len(passed)}")
    print(f"   Total passed credits: {credits}")

    assert len(all_courses) == 6, f"Expected 6 courses, got {len(all_courses)}"
    assert credits == 18.0, f"Expected 18.0 credits, got {credits}"

    print("   StudentData works!")
    return True


def test_degree_and_buckets():
    """Test Degree and Bucket models."""
    print("\n" + "=" * 60)
    print("5. Testing Degree/Bucket models and BUCKETS/MAJORS data...")
    print("=" * 60)

    from grids import Bucket, Major, Degree, BUCKETS, MAJORS

    print(f"   Loaded {len(BUCKETS)} buckets from data")
    print(f"   Loaded {len(MAJORS)} majors from data")

    # Show a few bucket names
    if BUCKETS:
        print(f"   Sample buckets: {list(BUCKETS.keys())[:3]}")

    # Show a few major names
    if MAJORS:
        print(f"   Sample majors: {list(MAJORS.keys())[:3]}")

    # Create a simple degree
    test_bucket = Bucket(
        id="test_core",
        name="Test Core Requirements",
        credits_required=12.0,
        description="Test bucket",
        rules=[{
            "type": "min_credits_from",
            "credits": 12,
            "description": "Test rule",
            "filter": {"subjects": ["COMP"], "min_level": 1, "max_level": 1}
        }]
    )

    test_major = Major(
        id="test_major",
        name="Computer Science",
        total_credits=93,
        buckets=[test_bucket]
    )

    test_degree = Degree(
        total_credits=93,
        majors=[test_major],
        general_requirements=[]
    )

    print(f"   Created degree with {len(test_degree.majors)} major(s)")
    print(f"   Majors: {len(test_degree.majors)}")

    print("   Degree/Bucket models work!")
    return True


def test_requirement_evaluator():
    """Test RequirementEvaluator with student data."""
    print("\n" + "=" * 60)
    print("6. Testing RequirementEvaluator...")
    print("=" * 60)

    from grids import StudentData, ProgrammeData, TermData, StudentCourse, Bucket, Major, Degree
    from grids.evaluation import RequirementEvaluator

    # Load courses
    courses = load_courses_from_json()
    if not courses:
        from grids import Course
        courses = [
            Course(subject="COMP", number=1600, title="Intro to Computing", credits=3.0),
            Course(subject="COMP", number=1601, title="Programming I", credits=3.0),
            Course(subject="COMP", number=1602, title="Programming II", credits=3.0),
            Course(subject="COMP", number=1603, title="OOP", credits=3.0),
        ]

    # Create evaluator
    evaluator = RequirementEvaluator(courses)
    print(f"   Created evaluator with {len(courses)} courses")

    # Create student
    student = StudentData(
        name="Test Student",
        student_number="816000000",
        date_of_birth="01-Jan-2000",
        campus="St. Augustine",
        programme=ProgrammeData(
            admit_term="2020/2021 Semester I",
            programme_level="Undergraduate",
            degree="Bachelor of Science",
            programme="Computer Science",
            faculty="Science & Technology",
            department="Computing",
            major="Computer Science",
            degree_gpa=3.0,
        ),
        terms=[
            TermData(
                term_name="2020/2021 Semester I",
                courses=[
                    StudentCourse(subject="COMP", number=1600, title="Intro", credits=3.0, grade="A", points=12.0),
                    StudentCourse(subject="COMP", number=1601, title="Prog I", credits=3.0, grade="B+", points=9.9),
                ],
                gpa=3.65
            ),
        ],
        overall_gpa=3.65,
        programme_summary=[]
    )

    # Create a simple degree for testing
    test_bucket = Bucket(
        id="level1_core",
        name="Level 1 Core",
        credits_required=12.0,
        description="Level 1 COMP core courses",
        rules=[{
            "type": "min_credits_from",
            "credits": 12,
            "description": "Complete 12 credits from COMP Level 1",
            "filter": {"subjects": ["COMP"], "min_level": 1, "max_level": 1}
        }]
    )

    test_major = Major(
        id="test_major",
        name="Computer Science",
        total_credits=93,
        buckets=[test_bucket]
    )

    degree = Degree(
        total_credits=93,
        majors=[test_major],
        general_requirements=[]
    )

    # Evaluate
    result = evaluator.evaluate_degree(student, degree)

    print(f"   Evaluation result:")
    print(f"     - Is complete: {result.is_complete}")
    print(f"     - Credits: {result.total_credits_earned}/{result.total_credits_required}")
    print(f"     - GPA: {result.overall_gpa}")
    print(f"     - Progress: {result.overall_progress}")

    if result.major_results:
        for major_result in result.major_results:
            print(f"     - Major '{major_result.component_name}':")
            for bucket_result in major_result.bucket_results:
                print(f"       - {bucket_result.bucket_name}: {bucket_result.overall_progress}")

    if result.unmet_requirements:
        print(f"     - Unmet: {result.unmet_requirements[:2]}")

    print("   RequirementEvaluator works!")
    return True


def test_doc_type_identification():
    """Test document type identification (without actual PDF text)."""
    print("\n" + "=" * 60)
    print("7. Testing document type identification...")
    print("=" * 60)

    from grids import identify_doc_type

    # Test with transcript-like text (must contain "UNOFFICIAL TRANSCRIPT")
    transcript_text = """
    UNOFFICIAL TRANSCRIPT
    STUDENT INFORMATION
    John Doe
    Record of: 816012345 Student Number:
    Date of Birth: 01-Jan-2000

    CURRICULUM INFORMATION
    CURRENT PROGRAMME
    2020/2021 Semester I
    """

    # Test with grid-like text (must contain "Report Run Date")
    grid_text = """
    Report Run Date: 2024-01-15
    Student Number: 816012345
    Dg GPA
    John Doe
    CURRENT CURRICULUM
    2020/2021 Semester I
    Undergraduate
    Bachelor of Science
    """

    try:
        doc_type_transcript = identify_doc_type(transcript_text)
        print(f"   Transcript-like text identified as: {doc_type_transcript}")
        assert doc_type_transcript == "TRANSCRIPT", f"Expected TRANSCRIPT, got {doc_type_transcript}"

        doc_type_grid = identify_doc_type(grid_text)
        print(f"   Grid-like text identified as: {doc_type_grid}")
        assert doc_type_grid == "GRID", f"Expected GRID, got {doc_type_grid}"

        print("   Document type identification works!")
        return True
    except Exception as e:
        print(f"   Error: {e}")
        return False

def test_course_equivalencies(): # ADDED
    """Test that the Rule Engine respects legacy course equivalencies."""
    print("\n" + "=" * 60)
    print("8. Testing Course Equivalencies...")
    print("=" * 60)

    from grids import StudentData, ProgrammeData, TermData, StudentCourse, Bucket, Major, Degree
    from grids.evaluation import RequirementEvaluator

    # Create a student who took the LEGACY course (COMP 1400)
    student = StudentData(
        name="Legacy Student",
        student_number="816000001",
        programme=ProgrammeData(major="Computer Science"),
        terms=[
            TermData(
                term_name="2015/2016 Semester I",
                courses=[
                    StudentCourse(subject="COMP", number=1401, title="Legacy Intro", credits=4.0, grade="A", points=16.0),
                ],
                gpa=4.0
            ),
        ]
    )

    # Create a bucket that requires the NEW course (COMP 1600)
    test_bucket = Bucket(
        id="new_core",
        name="Modern Core",
        credits_required=3.0, # The modern rule wants 3 credits
        rules=[{
            "type": "all_credits_from",
            "list": ["COMP 1600"],
            "description": "Must take modern COMP 1600"
        }]
    )

    degree = Degree(total_credits=93, majors=[Major(id="test", name="CS", total_credits=93, buckets=[test_bucket])])

    evaluator = RequirementEvaluator(courses=[])
    result = evaluator.evaluate_degree(student, degree)

    # The bucket should pass because COMP 1401 maps to COMP 1600!
    bucket_result = result.major_results[0].bucket_results[0]
    
    print(f"   Required: COMP 1600")
    print(f"   Student took: COMP 1401")
    print(f"   Bucket Is Met: {bucket_result.is_met}")
    print(f"   Courses Used by Rule: {bucket_result.rule_results[0].courses_used}")
    
    assert bucket_result.is_met == True, "Equivalency failed: Engine did not map COMP 1401 to COMP 1600."
    
    print("   Equivalency logic works!")
    return True

def run_all_tests():
    """Run all validation tests."""
    print("\n" + "=" * 60)
    print("GRIDS MODULE VALIDATION")
    print("=" * 60)

    results = []

    results.append(("Imports", test_imports()))
    results.append(("Course creation", test_course_creation()))
    results.append(("CourseFilter", test_course_filter()))
    results.append(("StudentData", test_student_data()))
    results.append(("Degree/Bucket models", test_degree_and_buckets()))
    results.append(("RequirementEvaluator", test_requirement_evaluator()))
    results.append(("Document type identification", test_doc_type_identification()))
    results.append(("Course Equivalencies", test_course_equivalencies()))
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"   {name}: {status}")

    print(f"\n   Total: {passed}/{total} tests passed")

    if passed == total:
        print("\n   All tests passed! Module is ready for use.")
        return 0
    else:
        print("\n   Some tests failed. Please investigate.")
        return 1


if __name__ == "__main__":
    # Add parent directory to path for imports
    sys.path.insert(0, str(Path(__file__).parent.parent))
    sys.exit(run_all_tests())
