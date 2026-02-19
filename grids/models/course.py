from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class Course:
    """
    Course dataclass representing a course in the catalog.
    Converted from SQLModel entity for standalone use.
    """
    subject: str
    number: int
    title: str
    credits: float
    code: str = ""
    level: int = 0
    description: Optional[str] = None
    department: Optional[str] = None
    faculty: Optional[str] = None
    is_active: bool = True
    tags: Optional[List[str]] = None

    def __post_init__(self):
        # Auto-compute code from subject and number if not provided
        if not self.code:
            self.code = f"{self.subject} {self.number}"
        # Auto-compute level from number if not provided (e.g., 1600 -> 1)
        if not self.level:
            self.level = self.number // 1000
