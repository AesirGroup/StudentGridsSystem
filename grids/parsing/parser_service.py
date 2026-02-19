from typing import List

from ..common import DocType
from .grid_parser import parse_grids
from .transcript_parser import parse_transcripts
from ..models import StudentData


def parse_text(source_text: str, dtype: DocType) -> List[StudentData]:
    if dtype == "GRID":
        return parse_grids(source_text)
    elif dtype == "TRANSCRIPT":
        return parse_transcripts(source_text)
    else:
        raise ValueError(f"Invalid document type: {dtype}. Must be 'GRID' or 'TRANSCRIPT'")


def identify_doc_type(source_text: str) -> DocType:
    if "UNOFFICIAL TRANSCRIPT" in source_text:
        return "TRANSCRIPT"
    elif "Report Run Date" in source_text:
        return "GRID"
    else:
        raise ValueError("Unsupported document format. Valid document formats include: TRANSCRIPT, GRID")
