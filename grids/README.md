# Grids

Standalone Python module for parsing university transcripts and degree audit grids, with a rule-based degree requirement evaluation engine.

## Features

- **Transcript Parsing** - Extract student data from university transcript PDFs (text-extracted)
- **Grid Parsing** - Extract student data from degree audit grid PDFs (text-extracted)
- **Degree Evaluation** - Evaluate student progress against degree requirements using a flexible rule engine
- **No Dependencies** - Standalone module with only `pydantic` as external dependency

## Installation

```bash
pip install pydantic>=2.0
```

## Quick Start

```python
from grids import parse_text, identify_doc_type, Course
from grids.evaluation import RequirementEvaluator, Degree

# Parse a document
raw_text = open("transcript.txt").read()
doc_type = identify_doc_type(raw_text)  # Returns "TRANSCRIPT" or "GRID"
students = parse_text(raw_text, doc_type)

# Evaluate degree requirements
courses = [...]  # Load your course catalog as List[Course]
evaluator = RequirementEvaluator(courses)

for student in students:
    degree = Degree.from_student_data(student)
    result = evaluator.evaluate_degree(student, degree)
    print(f"{student.name}: {result.overall_progress}")
```

## Project Structure

```
grids/
├── __init__.py          # Main exports
├── common.py            # DocType definition
├── requirements.txt     # Dependencies
├── data/
│   ├── buckets.json     # Requirement bucket definitions
│   └── majors.json      # Major definitions
├── models/
│   ├── course.py        # Course dataclass
│   ├── student.py       # StudentData, TermData, StudentCourse
│   ├── programme.py     # ProgrammeData, ProgrammeSummaryItem
│   ├── transcript.py    # TranscriptTotals
│   └── evaluation.py    # Bucket, Major, Degree
├── parsing/
│   ├── parser_service.py    # parse_text(), identify_doc_type()
│   ├── transcript_parser.py # Transcript parsing logic
│   ├── grid_parser.py       # Grid parsing logic
│   ├── splitter.py          # Document splitting utilities
│   └── grades.py            # Grade conversion utilities
└── evaluation/
    ├── filters.py       # CourseFilter for filtering courses
    └── rule_engine.py   # RequirementEvaluator
```

## Key Classes

| Class | Description |
|-------|-------------|
| `StudentData` | Student record with terms, courses, GPA |
| `Course` | Course catalog entry |
| `CourseFilter` | Filter courses by subject, level, department, etc. |
| `RequirementEvaluator` | Evaluate student against degree requirements |
| `Degree` | Degree definition with majors and requirements |
| `Bucket` | Requirement bucket with evaluation rules |
| `Major` | Major definition with bucket references |

## Document Types

The parser automatically identifies document types:

| Type | Detection |
|------|-----------|
| `TRANSCRIPT` | Contains "UNOFFICIAL TRANSCRIPT" |
| `GRID` | Contains "Report Run Date" |

## Testing

```bash
python validate_module.py
```

## License

MIT
