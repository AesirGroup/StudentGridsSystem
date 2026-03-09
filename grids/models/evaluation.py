# Evaluation models
# Bucket, Major, Degree definitions and JSON loaders

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, model_validator
import json
from pathlib import Path

from .student import StudentData
from .programme import ProgrammeData


class EvaluationRequest(BaseModel):
    students: List[StudentData] = Field(default_factory=list)


class EvaluationResponse(BaseModel):
    data: List[dict] = Field(default_factory=list)  # Will contain DegreeEvaluationResult objects


# ── Buckets, Majors and Minors ───────────────────────────────

class Bucket(BaseModel):
    id: str
    name: str
    credits_required: float
    description: Optional[str] = None
    rules: List[Any] = Field(default_factory=list)


class Major(BaseModel):
    id: str
    name: str
    total_credits: float
    description: Optional[str] = None
    bucket_ids: List[str] = Field(default_factory=list)
    buckets: List['Bucket'] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _populate_buckets_from_ids(cls, data: Any) -> Any:
        # Auto-resolve bucket_ids to Bucket objects from global BUCKETS
        if not isinstance(data, dict):
            return data

        # Only populate when bucket_ids is present and buckets not explicitly provided
        bucket_ids = data.get("bucket_ids") or []
        if bucket_ids and not data.get("buckets"):
            # Build a lookup from global BUCKETS (list or dict)
            try:
                global BUCKETS  # must exist in the module at runtime
                if isinstance(BUCKETS, dict):
                    registry: Dict[str, Any] = BUCKETS
                else:
                    registry = {b.id: b for b in BUCKETS}
            except NameError:
                # If BUCKETS isn't defined yet, leave data unchanged
                return data

            # Dedup while preserving order
            dedup_ids: List[str] = list(dict.fromkeys(bucket_ids))

            # Validate IDs
            unknown = [bid for bid in dedup_ids if bid not in registry]
            if unknown:
                raise ValueError(
                    f"Unknown bucket_ids for Major '{data.get('id', '?')}': {unknown}"
                )

            # Resolve actual Bucket objects in the given order
            data["bucket_ids"] = dedup_ids
            data["buckets"] = [registry[bid] for bid in dedup_ids]

        return data

    @model_validator(mode="after")
    def _sync_ids_from_buckets(self) -> 'Major':
        # Keep bucket_ids and buckets in sync
        if self.buckets and not self.bucket_ids:
            self.bucket_ids = [b.id for b in self.buckets]

        # Keep bucket_ids deduped & ordered
        self.bucket_ids = list(dict.fromkeys(self.bucket_ids))

        # If both provided, align order of buckets to bucket_ids
        if self.buckets and self.bucket_ids:
            by_id = {b.id: b for b in self.buckets}
            self.buckets = [by_id[b_id] for b_id in self.bucket_ids if b_id in by_id]

        return self


def _load_buckets(path: str) -> dict[Any, Bucket]:
    with open(path, 'r', encoding="utf-8") as f:
        data = json.load(f)
    return {b['id']: Bucket(**b) for b in data['buckets']}


def _load_majors(path: str) -> dict[Any, Major]:
    with open(path, 'r', encoding="utf-8") as f:
        data = json.load(f)
    return {m['id']: Major(**m) for m in data['majors']}


def _load_foreign_languages(path: str) -> set[str]:
    with open(path, 'r', encoding="utf-8") as f:
        data = json.load(f)
    return {s['code'] for s in data['subjects']}


# Define BASEDIR as the grids package data directory
BASEDIR = Path(__file__).parent.parent / 'data'

# Try to load buckets, majors, and foreign languages, but handle missing files gracefully
try:
    BUCKETS = _load_buckets(str(BASEDIR / 'buckets.json'))
    MAJORS = _load_majors(str(BASEDIR / 'majors.json'))
    FOREIGN_LANGUAGES = _load_foreign_languages(str(BASEDIR / 'foreign_languages.json'))
except FileNotFoundError:
    print("Warning: buckets.json, majors.json, or foreign_languages.json not found. Using empty dictionaries/sets.")
    BUCKETS = {}
    MAJORS = {}
    FOREIGN_LANGUAGES = set()


class Degree(BaseModel):
    majors: List[Major] = Field(default_factory=list)
    general_requirements: List[Bucket] = Field(default_factory=list)
    total_credits: int = Field(default_factory=int)

    @classmethod
    def from_student_data(cls, student: StudentData):
        return cls.from_programme_data(student.programme)

    @classmethod
    def from_programme_data(cls, programme: ProgrammeData):
        majors: List[Major] = []
        general_requirements: List[Bucket] = []

        for major in list(MAJORS.values()):
            if programme.major == major.name:
                majors.append(major.model_copy(deep=True))

        # Add foreign language requirement
        foreign_language_bucket = Bucket(
            id="FOREIGN_LANGUAGE_REQUIREMENT",
            name="Foreign Language Requirement",
            credits_required=3,
            description="Foreign language requirement for students admitted in 2023 or later",
            rules=[{
                "type": "foreign_language_requirement",
                "description": "Complete 3 credits of foreign language courses",
                "credits": 3.0
            }]
        )
        general_requirements.append(foreign_language_bucket)

        total_credits = 93

        return cls(
            majors=majors,
            general_requirements=general_requirements,
            total_credits=total_credits,
        )
