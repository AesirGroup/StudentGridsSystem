# NOTE: This is a test script to evaluate the parsing and evaluation of student data. It reads raw lines from a text file, parses them into student objects, and then runs an evaluation against a degree requirement model. The script also checks if the student's major matches any known majors in the system before attempting to evaluate their degree progress.
import sys
import json
from grids.parsing.parser_service import parse_text
from grids.models import Degree, Bucket
from grids.evaluation.rule_engine import RequirementEvaluator
from grids.models.evaluation import MAJORS

def main():
    try:
        with open("raw_lines.txt", "r", encoding="utf-8") as f:
            raw_lines = f.read()
    except FileNotFoundError:
        print("Error: raw_lines.txt not found.")
        return

    print("--- 1. Parsing Students ---")
    students = parse_text(raw_lines, dtype="GRID")
    print(f"Parsed {len(students)} students.\n")

    # Load Evaluator (Empty course catalog for now)
    evaluator = RequirementEvaluator(courses=[])

    print("--- 2. Running Evaluation ---")
    for student in students:
        print(f"Analyzing {student.name} ({student.student_number})...")
        
        # Check if their major exists in our JSON
        student_major = student.programme.major if student.programme else "Unknown"
        print(f"   Major detected: '{student_major}'")
        
        # Attempt to map scraped major to JSON keys if needed
        # (Simple check to see if the major string matches any 'name' in MAJORS)
        matched_major = None
        for m in MAJORS.values():
            if m.name.lower() == student_major.lower():
                matched_major = m.name
                break
        
        if not matched_major:
             print(f"Warning: Major '{student_major}' not found in majors.json. Skipping evaluation.")
             print("-" * 50)
             continue

        # Run Evaluation
        degree = Degree.from_student_data(student)
        result = evaluator.evaluate_degree(student, degree)

        print(f"   Credits: {result.total_credits_earned}/{result.total_credits_required}")
        print(f"   Status: {result.overall_progress}")
        
        # Show what they failed
        if result.unmet_requirements:
            print(f"   ❌ Missing Requirements: {len(result.unmet_requirements)}")
            for req in result.unmet_requirements[:3]: # Show first 3
                print(f"      - {req}")
        else:
            print("ALL REQUIREMENTS MET!")
            
        print("-" * 50)

if __name__ == "__main__":
    main()