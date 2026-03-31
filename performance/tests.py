from django.test import TestCase
from grids.models.student import StudentData, StudentCourse, TermData, ProgrammeData
from grids.models.course import Course
from grids.evaluation.rule_engine import _evaluate_foreign_language_requirement


class ForeignLanguageRequirementTestCase(TestCase):
    """Test cases for the foreign language requirement evaluation"""

    def setUp(self):
        """Set up test data"""
        self.rule_data = {
            'description': 'Foreign Language Requirement',
            'credits': 3.0
        }
        self.used_courses = set()
        self.courses = []  # Empty course catalog for these tests

    def _create_student(self, admit_term=None, courses=None):
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

    def _create_course(self, subject, number, title, grade, credits=3.0):
        """Helper to create a StudentCourse instance"""
        return StudentCourse(
            subject=subject,
            number=number,
            title=title,
            grade=grade,
            credits=credits
        )

    def test_student_admitted_before_2023_automatically_met(self):
        """Students admitted before 2023 should automatically meet the requirement"""
        student = self._create_student(admit_term="2022/2023 Semester I")

        result = _evaluate_foreign_language_requirement(student, self.rule_data, self.used_courses, self.courses)

        self.assertTrue(result.is_met)
        self.assertEqual(result.details, "Requirement does not apply (admit year: 2022)")
        self.assertEqual(result.progress, "N/A")

    def test_student_admitted_2023_or_later_no_foreign_language_courses(self):
        """Students admitted in 2023+ with no foreign language courses should not meet requirement"""
        student = self._create_student(admit_term="2023/2024 Semester I")

        result = _evaluate_foreign_language_requirement(student, self.rule_data, self.used_courses, self.courses)

        self.assertFalse(result.is_met)
        self.assertEqual(result.progress, "0/3.0 credits")
        self.assertEqual(result.details, "No foreign language courses completed")

    def test_student_with_french_course_met(self):
        """Student with a French course should meet the requirement"""
        courses = [self._create_course("FREN", 101, "French I", "A")]
        student = self._create_student(admit_term="2023/2024 Semester I", courses=courses)

        result = _evaluate_foreign_language_requirement(student, self.rule_data, self.used_courses, self.courses)

        self.assertTrue(result.is_met)
        self.assertEqual(result.progress, "3.0/3.0 credits")
        self.assertEqual(result.details, "Completed 1 foreign language course(s)")
        self.assertEqual(result.courses_used, ["FREN 101"])
        self.assertEqual(result.credits_earned, 3.0)

    def test_student_with_spanish_course_met(self):
        """Student with a Spanish course should meet the requirement"""
        courses = [self._create_course("SPAN", 201, "Spanish II", "B+")]
        student = self._create_student(admit_term="2023/2024 Semester I", courses=courses)

        result = _evaluate_foreign_language_requirement(student, self.rule_data, self.used_courses, self.courses)

        self.assertTrue(result.is_met)
        self.assertEqual(result.progress, "3.0/3.0 credits")
        self.assertEqual(result.details, "Completed 1 foreign language course(s)")

    def test_student_with_german_course_met(self):
        """Student with a German course should meet the requirement"""
        courses = [self._create_course("GERM", 301, "German III", "A-")]
        student = self._create_student(admit_term="2023/2024 Semester I", courses=courses)

        result = _evaluate_foreign_language_requirement(student, self.rule_data, self.used_courses, self.courses)

        self.assertTrue(result.is_met)

    def test_student_with_japanese_course_met(self):
        """Student with a Japanese course should meet the requirement"""
        courses = [self._create_course("JAPA", 101, "Japanese I", "B")]
        student = self._create_student(admit_term="2023/2024 Semester I", courses=courses)

        result = _evaluate_foreign_language_requirement(student, self.rule_data, self.used_courses, self.courses)

        self.assertTrue(result.is_met)

    def test_student_with_non_foreign_language_course_not_met(self):
        """Student with only non-foreign language courses should not meet requirement"""
        courses = [
            self._create_course("COMP", 1600, "Computer Science I", "A"),
            self._create_course("MATH", 1000, "Calculus I", "B"),
            self._create_course("ENGL", 1000, "English Composition", "A")
        ]
        student = self._create_student(admit_term="2023/2024 Semester I", courses=courses)

        result = _evaluate_foreign_language_requirement(student, self.rule_data, self.used_courses, self.courses)

        self.assertFalse(result.is_met)
        self.assertEqual(result.details, "No foreign language courses completed")

    def test_student_with_foreign_language_exemption_met(self):
        """Student with EX grade in foreign language course should meet requirement"""
        courses = [self._create_course("FREN", 101, "French I", "EX")]
        student = self._create_student(admit_term="2023/2024 Semester I", courses=courses)

        result = _evaluate_foreign_language_requirement(student, self.rule_data, self.used_courses, self.courses)

        self.assertTrue(result.is_met)
        self.assertEqual(result.progress, "Exempted (1 EX course(s))")
        self.assertEqual(result.details, "Exempted from foreign language requirement via 1 EX course(s)")
        self.assertEqual(result.exemptions_without_credits, ["FREN 101"])
        self.assertEqual(result.exemption_mappings, [{"course": "FREN 101", "reason": "Foreign Language Exemption"}])

    def test_student_with_multiple_foreign_language_courses(self):
        """Student with multiple foreign language courses should meet requirement"""
        courses = [
            self._create_course("FREN", 101, "French I", "A"),
            self._create_course("SPAN", 102, "Spanish I", "B"),
            self._create_course("FREN", 201, "French II", "A-")
        ]
        student = self._create_student(admit_term="2023/2024 Semester I", courses=courses)

        result = _evaluate_foreign_language_requirement(student, self.rule_data, self.used_courses, self.courses)

        self.assertTrue(result.is_met)
        self.assertEqual(result.details, "Completed 3 foreign language course(s)")
        self.assertEqual(len(result.courses_used), 3)
        self.assertEqual(result.credits_earned, 9.0)  # 3 courses * 3 credits each

    def test_student_with_mixed_grades_in_foreign_language(self):
        """Student with both regular grades and EX in foreign language courses"""
        courses = [
            self._create_course("FREN", 101, "French I", "A"),
            self._create_course("FREN", 201, "French II", "EX"),
            self._create_course("COMP", 1600, "Computer Science", "B")
        ]
        student = self._create_student(admit_term="2023/2024 Semester I", courses=courses)

        result = _evaluate_foreign_language_requirement(student, self.rule_data, self.used_courses, self.courses)

        self.assertTrue(result.is_met)
        self.assertEqual(result.progress, "Exempted (1 EX course(s))")
        self.assertEqual(result.courses_used, ["FREN 101"])  # Only non-EX courses count for credits
        self.assertEqual(result.credits_earned, 3.0)
        self.assertEqual(result.exemptions_without_credits, ["FREN 201"])

    def test_student_with_failing_foreign_language_course_not_met(self):
        """Student with only failing grades in foreign language courses should not meet requirement"""
        courses = [
            self._create_course("FREN", 101, "French I", "F"),
            self._create_course("SPAN", 102, "Spanish I", "D")
        ]
        student = self._create_student(admit_term="2023/2024 Semester I", courses=courses)

        result = _evaluate_foreign_language_requirement(student, self.rule_data, self.used_courses, self.courses)

        self.assertFalse(result.is_met)
        self.assertEqual(result.details, "No foreign language courses completed")

    def test_student_with_ec_grade_in_foreign_language_met(self):
        """Student with EC (Exemption with Credit) in foreign language should meet requirement"""
        courses = [self._create_course("FREN", 101, "French I", "EC")]
        student = self._create_student(admit_term="2023/2024 Semester I", courses=courses)

        result = _evaluate_foreign_language_requirement(student, self.rule_data, self.used_courses, self.courses)

        self.assertTrue(result.is_met)
        self.assertEqual(result.courses_used, ["FREN 101"])
        self.assertEqual(result.credits_earned, 3.0)

    def test_course_subject_extraction_from_course_code(self):
        """Test that subject is correctly extracted from course_code when subject field is missing"""
        # Create course with code field (which triggers the validator to set subject)
        course = StudentCourse(
            code="FREN 101",
            title="French I",
            grade="A",
            credits=3.0
        )
        courses = [course]
        student = self._create_student(admit_term="2023/2024 Semester I", courses=courses)

        result = _evaluate_foreign_language_requirement(student, self.rule_data, self.used_courses, self.courses)

        self.assertTrue(result.is_met)
        self.assertEqual(result.courses_used, ["FREN 101"])

    def test_admit_year_extraction_edge_cases(self):
        """Test admit year extraction with various formats"""
        # Test with None admit_term
        student = self._create_student(admit_term=None)
        result = _evaluate_foreign_language_requirement(student, self.rule_data, self.used_courses, self.courses)
        self.assertTrue(result.is_met)  # Should default to not applying

        # Test with malformed admit_term
        student = self._create_student(admit_term="invalid")
        result = _evaluate_foreign_language_requirement(student, self.rule_data, self.used_courses, self.courses)
        self.assertTrue(result.is_met)  # Should default to not applying

    def test_multiple_terms_with_foreign_language_courses(self):
        """Test student with foreign language courses across multiple terms"""
        term1 = TermData()
        term1.courses = [self._create_course("FREN", 101, "French I", "A")]

        term2 = TermData()
        term2.courses = [self._create_course("SPAN", 102, "Spanish I", "B")]

        student = StudentData(
            name="Test Student",
            student_number="12345",
            programme=ProgrammeData(admit_term="2023/2024 Semester I"),
            terms=[term1, term2]
        )

        result = _evaluate_foreign_language_requirement(student, self.rule_data, self.used_courses, self.courses)

        self.assertTrue(result.is_met)
        self.assertEqual(len(result.courses_used), 2)
        self.assertEqual(result.credits_earned, 6.0)

    def test_used_courses_are_excluded_from_credit_calculation(self):
        """Test that courses already used in other requirements are excluded from credit calculation"""
        courses = [self._create_course("FREN", 101, "French I", "A")]
        student = self._create_student(admit_term="2023/2024 Semester I", courses=courses)

        # Mark the course as used
        used_courses = {"FREN 101"}

        result = _evaluate_foreign_language_requirement(student, self.rule_data, used_courses, self.courses)

        self.assertTrue(result.is_met)  # Still met because they have the course
        self.assertEqual(result.courses_used, [])  # But no credits earned since it's used
        self.assertEqual(result.credits_earned, 0.0)
