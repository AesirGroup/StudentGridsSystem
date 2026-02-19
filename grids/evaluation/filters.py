# Course filtering for degree evaluation
# Filters courses by subject, level, department, faculty, tags, etc.

from typing import List, Optional, Tuple
from pydantic import BaseModel

from ..models import Course


class CourseFilter(BaseModel):
    """Filter courses by subject, level, department, etc."""
    subjects: Optional[List[str]] = None
    min_level: Optional[int] = None
    max_level: Optional[int] = None
    departments: Optional[List[str]] = None
    faculties: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    include_codes: Optional[List[str]] = None
    exclude_codes: Optional[List[str]] = None
    exclude_pairs: Optional[List[Tuple[str, int]]] = None

    def apply(self, courses: List[Course]) -> List[Course]:
        """
        Apply filters to an in-memory list of courses.
        Returns filtered courses.
        """
        result = list(courses)  # Make a copy

        if self.subjects:
            result = [c for c in result if c.subject in self.subjects]
        if self.min_level is not None:
            result = [c for c in result if c.level >= self.min_level]
        if self.max_level is not None:
            result = [c for c in result if c.level <= self.max_level]
        if self.departments:
            result = [c for c in result if c.department in self.departments]
        if self.faculties:
            result = [c for c in result if c.faculty in self.faculties]
        if self.include_codes:
            result = [c for c in result if c.code in self.include_codes]
        if self.exclude_codes:
            result = [c for c in result if c.code not in self.exclude_codes]
        if self.exclude_pairs:
            exclude_set = {(s, n) for s, n in self.exclude_pairs}
            result = [c for c in result if (c.subject, c.number) not in exclude_set]
        if self.tags:
            want = {t.lower() for t in self.tags}
            result = [c for c in result if c.tags and any(t.lower() in want for t in c.tags)]

        return result

    def __str__(self):
        parts = []
        if self.subjects: parts.append(f"subjects={self.subjects}")
        if self.min_level is not None: parts.append(f"min_level={self.min_level}")
        if self.max_level is not None: parts.append(f"max_level={self.max_level}")
        if self.departments: parts.append(f"departments={self.departments}")
        if self.faculties: parts.append(f"faculties={self.faculties}")
        if self.tags: parts.append(f"tags={self.tags}")
        if self.include_codes: parts.append(f"include_codes={self.include_codes}")
        if self.exclude_codes: parts.append(f"exclude_codes={self.exclude_codes}")
        if self.exclude_pairs: parts.append(f"exclude_pairs={self.exclude_pairs}")
        return f"CourseFilter({', '.join(parts)})" if parts else "CourseFilter(<no filters>)"

    def __repr__(self):
        return str(self)
