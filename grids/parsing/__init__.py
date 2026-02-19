from .parser_service import parse_text, identify_doc_type
from .transcript_parser import parse_transcripts
from .grid_parser import parse_grids
from .splitter import (
    split_transcript_documents,
    split_grid_documents,
    get_document_boundaries,
    get_grid_document_boundaries,
    validate_document_structure,
    validate_grid_structure
)
from .grades import (
    quality_points_to_grade,
    grade_to_quality_points,
    score_to_grade,
    grade_to_score_range,
    GRADE_TABLE,
    GRADE_SYNONYMS
)

__all__ = [
    # Main API
    'parse_text', 'identify_doc_type',
    # Parsers
    'parse_transcripts', 'parse_grids',
    # Splitter utilities
    'split_transcript_documents', 'split_grid_documents',
    'get_document_boundaries', 'get_grid_document_boundaries',
    'validate_document_structure', 'validate_grid_structure',
    # Grade utilities
    'quality_points_to_grade', 'grade_to_quality_points',
    'score_to_grade', 'grade_to_score_range',
    'GRADE_TABLE', 'GRADE_SYNONYMS',
]
