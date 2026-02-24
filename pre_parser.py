# NOTE: Parses the original PDF with pdfplumber, crops it into 3 columns, and linearizes the text into a single string. 
# Then splits that string into lines and saves to raw_lines.txt for use in test_runner_evaluation.py.

# Import necessary libraries
import pdfplumber
import re
import json

# 1. Open the PDF
# Replace 'student_grids.pdf' with your actual PDF file name, keep it in the same directory for simplicity.


# KAREEM - Reading from INFO_INFT_redacted.pdf that has both INFO and INFT merged
# Sergios majors.json checks for "Information Technology (Special)" but in grids it is Information Technology (Spec) so I changed it


# with pdfplumber.open("student_grids_info_redacted.pdf") as pdf:
with pdfplumber.open("INFO_INFT_redacted.pdf") as pdf:
    
    # I'll store all clean, linearized text here
    all_text = []

    # 2. Loop through every physical page in the PDF
    for i, page in enumerate(pdf.pages):
        
        # Get page dimensions
        width = page.width
        height = page.height
        
        # Calculate the 1/3 split point
        # I divide the total width by 3 to get the width of one column
        third_width = width / 3

        # 3. Define the 3 Bounding Boxes
        # A box is defined as: (x0, y0, x1, y1)
        # (left, top, right, bottom)
        padding = 5  # Optional padding to avoid cutting off text

        # LEFT COLUMN
        # Starts at 0, ends at 1/3 of the page
        box_left = (0, 0, third_width, height)

        # MIDDLE COLUMN
        # Starts at 1/3, ends at 2/3 of the page
        box_mid = (third_width - padding, 0, third_width * 2 - padding, height)

        # RIGHT COLUMN
        # Starts at 2/3, ends at the full width
        box_right = (third_width * 2, 0, width, height)

        # 4. Perform the Crop and Extract
        try:
            # Crop the page to the box area, then extract text from that crop
            text_left = page.crop(box_left).extract_text()
            text_mid = page.crop(box_mid).extract_text()
            text_right = page.crop(box_right).extract_text()

            # 5. Add to master list in the correct reading order
            if text_left:
                all_text.append(text_left)

            if text_mid:
                all_text.append(text_mid)

            if text_right:
                all_text.append(text_right)
                
            print(f"Processed Page {i+1}...")

        except Exception as e:
            print(f"Error on page {i+1}: {e}")

# 6. Join all the column blocks into one massive string
full_text_blob = "\n".join(all_text)

# 7. Split that blob into individual lines
raw_lines = full_text_blob.splitlines()

# 8. Save the raw lines to a file
with open("raw_lines_2.txt", "w") as f:
    f.write("\n".join(raw_lines))