from pydantic import BaseModel, Field


class TranscriptTotalRow(BaseModel):
    """Represents a single row of transcript totals (e.g., Total Institution, Overall, etc.)"""
    attempt_hours: float = 0.0
    passed_hours: float = 0.0
    earned_hours: float = 0.0
    gpa_hrs_hours: float = 0.0
    quality_points: float = 0.0
    gpa: float = 0.0


class TranscriptTotals(BaseModel):
    """Contains all four rows of transcript totals from the end of a transcript"""
    total_institution: TranscriptTotalRow = Field(default_factory=TranscriptTotalRow)
    total_transfer: TranscriptTotalRow = Field(default_factory=TranscriptTotalRow)
    overall: TranscriptTotalRow = Field(default_factory=TranscriptTotalRow)
    degree: TranscriptTotalRow = Field(default_factory=TranscriptTotalRow)
    