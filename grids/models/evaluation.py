# Evaluation models
# Bucket, Major, Degree definitions and JSON loaders
from django.conf import settings
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
    contributes_to_degree_gpa: bool = True
    description: Optional[str] = None
    rules: List[Any] = Field(default_factory=list)


class Major(BaseModel):
    id: str
    name: str
    faculty: Optional[str] = None
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


class Minor(BaseModel):
    """A named minor programme with its own set of requirement buckets."""
    id: str
    name: str
    faculty: Optional[str] = None
    total_credits: float
    description: Optional[str] = None
    bucket_ids: List[str] = Field(default_factory=list)
    buckets: List['Bucket'] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _populate_buckets_from_ids(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        bucket_ids = data.get("bucket_ids") or []
        if bucket_ids and not data.get("buckets"):
            try:
                global BUCKETS
                registry: Dict[str, Any] = BUCKETS if isinstance(BUCKETS, dict) else {b.id: b for b in BUCKETS}
            except NameError:
                return data
            dedup_ids: List[str] = list(dict.fromkeys(bucket_ids))
            unknown = [bid for bid in dedup_ids if bid not in registry]
            if unknown:
                raise ValueError(
                    f"Unknown bucket_ids for Minor '{data.get('id', '?')}': {unknown}"
                )
            data["bucket_ids"] = dedup_ids
            data["buckets"] = [registry[bid] for bid in dedup_ids]
        return data

    @model_validator(mode="after")
    def _sync_ids_from_buckets(self) -> 'Minor':
        if self.buckets and not self.bucket_ids:
            self.bucket_ids = [b.id for b in self.buckets]
        self.bucket_ids = list(dict.fromkeys(self.bucket_ids))
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


def _load_minors(path: str) -> dict[Any, Minor]:
    with open(path, 'r', encoding="utf-8") as f:
        data = json.load(f)
    return {m['id']: Minor(**m) for m in data['minors']}



# ── Faculty name normalisation ───────────────────────────────
# Transcript text may say "Science and Technology" while bucket IDs use "FST".
_FACULTY_ALIASES: Dict[str, str] = {
    "science and technology": "FST",
    "fst": "FST",
    "engineering": "ENG",
    "eng": "ENG",
    "humanities and education": "FHE",
    "fhe": "FHE",
    "food and agriculture": "FFA",
    "ffa": "FFA",
    "social sciences": "FSS",
    "fss": "FSS",
    "medical sciences": "MEDSCI",
    "medsci": "MEDSCI",
    "fms": "MEDSCI",
    "law": "LAW",
    "sport": "SPORT",
}


def _normalise_faculty(raw: str) -> Optional[str]:
    """Map free-text faculty names to canonical bucket-ID suffixes."""
    if not raw:
        return None
    key = raw.strip().lower()
    return _FACULTY_ALIASES.get(key, raw.upper())


# Define BASEDIR as the grids package data directory
# BASEDIR = Path(__file__).parent.parent / 'data'

# CHANGE: Safely anchors to the project root while maintaining the Pathlib object type
BASEDIR = settings.BASE_DIR / 'grids' / 'data'

# Try to load buckets, majors, and minors, but handle missing files gracefully
try:
    BUCKETS = _load_buckets(str(BASEDIR / 'buckets.json'))
    MAJORS = _load_majors(str(BASEDIR / 'majors.json'))
except FileNotFoundError:
    print("Warning: buckets.json or majors.json not found. Using empty dictionaries.")
    BUCKETS = {}
    MAJORS = {}

try:
    MINORS = _load_minors(str(BASEDIR / 'minors.json'))
except FileNotFoundError:
    print("Warning: minors.json not found. Using empty dictionary.")
    MINORS = {}


class Degree(BaseModel):
    majors: List[Major] = Field(default_factory=list)
    minors: List[Minor] = Field(default_factory=list)
    general_requirements: List[Bucket] = Field(default_factory=list)
    total_credits: int = Field(default_factory=int)

    @classmethod
    def from_student_data(cls, student: StudentData):
        return cls.from_programme_data(student.programme)

    @classmethod
    def from_programme_data(cls, programme: ProgrammeData):
        majors: List[Major] = []
        minors: List[Minor] = []
        general_requirements: List[Bucket] = []

        for major in list(MAJORS.values()):
            if programme.major:
                major_list = [m.strip() for m in programme.major.split(",")]
                if major.name in major_list:
                    majors.append(major.model_copy(deep=True))

        # ── Minor detection ────────────────────────────────────────
        if programme.minor:
            minor_list = [m.strip() for m in programme.minor.split(",")]
            for minor in list(MINORS.values()):
                if minor.name in minor_list:
                    minors.append(minor.model_copy(deep=True))

        # ── Faculty-based general requirements ────────────────────
        # Resolve the faculty from the matched major or the programme data.
        faculty = None
        if majors and majors[0].faculty:
            faculty = majors[0].faculty
        elif programme.faculty:
            faculty = _normalise_faculty(programme.faculty)

        # Look up the faculty-specific FLR bucket from buckets.json.
        flr_bucket_id = f"FLR_{faculty}" if faculty else None
        if flr_bucket_id and flr_bucket_id in BUCKETS:
            general_requirements.append(BUCKETS[flr_bucket_id].model_copy(deep=True))
        else:
            # Fallback: use FST rules when faculty is unknown (preserves old behaviour)
            if "FLR_FST" in BUCKETS:
                general_requirements.append(BUCKETS["FLR_FST"].model_copy(deep=True))

        if majors:
            total_credits = max([m.total_credits for m in majors])
        else:
            total_credits = 93

        return cls(
            majors=majors,
            minors=minors,
            general_requirements=general_requirements,
            total_credits=total_credits,
        )
