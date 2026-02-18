# NOTE: This is a test runner script for the Grids parsing module. It reads raw text from a modified 'raw_lines.txt', passes it to the parser, and prints the results. 
# Make sure to have the 'grids' folder with the parsing service in the same directory as this script.
import pdfplumber
import json
import sys

# Import the parsing service from your module
# (Make sure the 'grids' folder is in the same directory as this script)
try:
    from grids.parsing import parse_text
except ImportError:
    print("Error: Could not find the 'grids' module.")
    print("Make sure this script is running in the folder containing the 'grids' directory.")
    sys.exit(1)

def main():
    try:
        with open("raw_lines.txt", "r") as f:
            raw_lines = f.read()
        print(f"--- Step 1.5: Read raw_lines.txt ({len(raw_lines)} chars) ---")
    except FileNotFoundError:
        print("Error: File 'raw_lines.txt' not found.")
        return

    # --- GLUE CODE STARTS HERE ---
    
    print("--- Step 2: Passing text to Grids Module ---")
    
    try:
        # Call the parser service
        # We explicitly tell it this is a "GRID" document
        students = parse_text(raw_lines, dtype="GRID")
        
        print(f"\nSuccess! Parsed {len(students)} student(s).\n")
        
        # --- Step 3: Print the Results ---
        for i, student in enumerate(students):
            print(f"Student #{i+1}:")
            print(f"  Name: {student.name}")
            print(f"  Number: {student.student_number}")
            print(f"  Programme: {student.programme.programme if student.programme else 'Unknown'}")
            print(f"  Major: {student.programme.major if student.programme else 'Unknown'}")
            print(f"  GPA: {student.overall_gpa}")
            print(f"  Terms Found: {len(student.terms)}")
            
            if student.terms:
                last_term = student.terms[-1]
                print(f"  Latest Term: {last_term.term_name} (GPA: {last_term.gpa})")
                print(f"  Courses in latest term: {len(last_term.courses)}")
            
            # Uncomment the line below to see the FULL JSON data for the student
            # print(student.model_dump_json(indent=2))
            print("-" * 40)

    except Exception as e:
        print(f"Parser Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()