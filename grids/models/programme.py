from typing import Optional
from pydantic import BaseModel


class ProgrammeData(BaseModel):
    admit_term: Optional[str] = None
    programme_level: Optional[str] = None
    degree: Optional[str] = None
    programme: Optional[str] = None
    faculty: Optional[str] = None
    department: Optional[str] = None
    major: Optional[str] = None
    degree_gpa: Optional[float] = None


class ProgrammeSummaryItem(BaseModel):
    name: str
    progress_numerator: int
    progress_denominator: int
