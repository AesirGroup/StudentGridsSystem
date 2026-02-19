# Utilities for splitting multi-student PDF text into individual documents

from typing import List, Tuple
import re


def split_transcript_documents(raw_text: str) -> List[str]:
    """Split text containing multiple transcripts by 'STUDENT INFORMATION' markers."""
    if not isinstance(raw_text, str) or not raw_text.strip():
        return []

    pattern = re.compile(r'STUDENT\s+INFORMATION', re.IGNORECASE)
    matches = list(pattern.finditer(raw_text))

    if not matches:
        return [raw_text.strip()] if raw_text.strip() else []

    documents = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw_text)
        doc = raw_text[start:end].strip()
        if doc:
            documents.append(doc)

    return documents


def split_grid_documents(raw_text: str) -> List[str]:
    """Split text containing multiple grids by 'Student Number:' markers."""
    if not isinstance(raw_text, str) or not raw_text.strip():
        return []

    pattern = re.compile(r'Student\s+Number:\s*\d+', re.IGNORECASE)
    matches = list(pattern.finditer(raw_text))

    if not matches:
        return [raw_text.strip()] if raw_text.strip() else []

    documents = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw_text)
        doc = raw_text[start:end].strip()
        if doc:
            documents.append(doc)

    return documents


def get_document_boundaries(raw_text: str) -> List[Tuple[int, int]]:
    """Get (start, end) positions for each transcript in the text."""
    if not isinstance(raw_text, str) or not raw_text.strip():
        return []

    pattern = re.compile(r'STUDENT\s+INFORMATION', re.IGNORECASE)
    matches = list(pattern.finditer(raw_text))

    if not matches:
        return [(0, len(raw_text))]

    boundaries = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw_text)
        boundaries.append((start, end))

    return boundaries


def get_grid_document_boundaries(raw_text: str) -> List[Tuple[int, int]]:
    """Get (start, end) positions for each grid document in the text."""
    if not isinstance(raw_text, str) or not raw_text.strip():
        return []

    pattern = re.compile(r'Student\s+Number:\s*\d+', re.IGNORECASE)
    matches = list(pattern.finditer(raw_text))

    if not matches:
        return [(0, len(raw_text))]

    boundaries = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw_text)
        boundaries.append((start, end))

    return boundaries


def validate_document_structure(document_text: str) -> bool:
    """Check if text looks like a valid transcript (has required markers)."""
    if not document_text or not document_text.strip():
        return False

    # Must have these
    required = [r'STUDENT\s+INFORMATION', r'RECORD\s+OF']
    for pattern in required:
        if not re.search(pattern, document_text, re.IGNORECASE):
            return False

    # Should have at least one of these
    optional = [
        r'CURRENT\s+PROGRAMME',
        r'UNOFFICIAL\s+TRANSCRIPT',
        r'\d{4}/\d{4}\s+Semester',
    ]
    return any(re.search(p, document_text, re.IGNORECASE) for p in optional)


def validate_grid_structure(document_text: str) -> bool:
    """Check if text looks like a valid grid document (has required markers)."""
    if not document_text or not document_text.strip():
        return False

    # Must have these
    required = [r'Student\s+Number:\s*\d+', r'Record\s+of:']
    for pattern in required:
        if not re.search(pattern, document_text, re.IGNORECASE):
            return False

    # Should have at least one of these
    optional = [
        r'CURRENT\s+PROGRAMME',
        r'Report\s+Run\s+Date',
        r'\d{4}/\d{4}\s+Semester',
        r'DEGREE\s+GPA\s+TOTALS',
    ]
    return any(re.search(p, document_text, re.IGNORECASE) for p in optional)
