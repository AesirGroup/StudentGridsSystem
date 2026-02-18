# NOTE: This can only work with an actual unredacted grids PDF file named "student_grids.pdf" in the same folder as this script.
import pdfplumber
import json
import sys

# Import the parsing service from your module
# (Make sure the 'grids' folder is in the same directory as this script)
try:
    from grids.parsing.parser_service import parse_text
except ImportError:
    print("Error: Could not find the 'grids' module.")
    print("Make sure this script is running in the folder containing the 'grids' directory.")
    sys.exit(1)

def main():
    pdf_path = "student_grids.pdf" # Make sure this file exists!
    
    print(f"--- Step 1: Extracting text from {pdf_path} ---")
    
    # --- YOUR PRE_PARSER LOGIC HERE ---
    all_text = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                width = page.width
                height = page.height
                third_width = width / 3
                padding = 5 

                # Define columns (Left, Mid, Right)
                box_left = (0, 0, third_width, height)
                box_mid = (third_width - padding, 0, third_width * 2 - padding, height)
                box_right = (third_width * 2, 0, width, height)

                # Extract
                text_left = page.crop(box_left).extract_text() or ""
                text_mid = page.crop(box_mid).extract_text() or ""
                text_right = page.crop(box_right).extract_text() or ""

                # Append in reading order
                if text_left: all_text.append(text_left)
                if text_mid: all_text.append(text_mid)
                if text_right: all_text.append(text_right)
                
                print(f"  Processed Page {i+1}...")
                
    except FileNotFoundError:
        print(f"Error: File '{pdf_path}' not found.")
        return
    except Exception as e:
        print(f"Error during PDF extraction: {e}")
        return

    # Join it all into one big string (The "Blob")
    full_text_blob = "\n".join(all_text)
    print(f"\n--- Extraction Complete ({len(full_text_blob)} chars) ---")

    # --- GLUE CODE STARTS HERE ---
    
    print("--- Step 2: Passing text to Grids Module ---")
    
    try:
        # Call the parser service
        # Explicitly tell it this is a "GRID" document
        students = parse_text(full_text_blob, dtype="GRID")
        
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