"""
Grids - Standalone transcript/grid parsing and degree evaluation module.

This module provides:
- Transcript and degree grid document parsing
- Degree requirement evaluation engine
- Course filtering utilities

No database or AI dependencies - fully standalone.

Usage:
    from grids import parse_text, identify_doc_type, StudentData
    from grids.evaluation import RequirementEvaluator, Degree

    # Parse a transcript
    doc_type = identify_doc_type(raw_text)
    students = parse_text(raw_text, doc_type)

    # Evaluate degree requirements
    courses = [...]  # Load course catalog
    evaluator = RequirementEvaluator(courses)
    for student in students:
        degree = Degree.from_student_data(student)
        result = evaluator.evaluate_degree(student, degree)
"""

from .common import DocType
from .models import (
    # Course
    Course,
    # Programme
    ProgrammeData, ProgrammeSummaryItem,
    # Transcript
    TranscriptTotalRow, TranscriptTotals,
    # Student
    StudentCourse, TermData, StudentData,
    # Evaluation models
    Bucket, Major, Degree,
    EvaluationRequest, EvaluationResponse,
    BUCKETS, MAJORS,
)
from .parsing import parse_text, identify_doc_type
from .evaluation import (
    RequirementEvaluator,
    CourseFilter,
    RequirementResult,
    BucketResult,
    ComponentResult,
    DegreeEvaluationResult,
)

__all__ = [
    # Types
    'DocType',
    # Course
    'Course',
    # Programme
    'ProgrammeData', 'ProgrammeSummaryItem',
    # Transcript
    'TranscriptTotalRow', 'TranscriptTotals',
    # Student
    'StudentCourse', 'TermData', 'StudentData',
    # Evaluation models
    'Bucket', 'Major', 'Degree',
    'EvaluationRequest', 'EvaluationResponse',
    'BUCKETS', 'MAJORS',
    # Parsing
    'parse_text', 'identify_doc_type',
    # Evaluation
    'RequirementEvaluator', 'CourseFilter',
    'RequirementResult', 'BucketResult',
    'ComponentResult', 'DegreeEvaluationResult',
]
