import os
import io
import json
import re
import pdfplumber
from functools import lru_cache

from django.conf import settings
from django.db import transaction
from django.views import View
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.mixins import LoginRequiredMixin

from grids.parsing.parser_service import parse_text, identify_doc_type
from grids.models import Degree, Course
from grids.evaluation.rule_engine import RequirementEvaluator, _find_course
from .models import StudentProfile, AuditRecord, BucketResult

# --- HELPER FUNCTIONS ---

def extract_text_from_grid_pdf(file_obj):
    """Parses the 3-column PDF directly from memory"""
    all_text = []
    with pdfplumber.open(file_obj) as pdf:
        for page in pdf.pages:
            width = page.width
            height = page.height
            third_width = width / 3
            padding = 5

            box_left = (0, 0, third_width, height)
            box_mid = (third_width - padding, 0, third_width * 2 - padding, height)
            box_right = (third_width * 2, 0, width, height)

            try:
                text_left = page.crop(box_left).extract_text()
                text_mid = page.crop(box_mid).extract_text()
                text_right = page.crop(box_right).extract_text()

                if text_left: all_text.append(text_left)
                if text_mid: all_text.append(text_mid)
                if text_right: all_text.append(text_right)
            except Exception as e:
                print(f"Error on PDF extraction: {e}")
                
    return "\n".join(all_text) 


def extract_text_from_transcript_pdf(file_obj):
    """Parses a transcript PDF from memory, filtering out large watermark text."""
    all_text = []
    with pdfplumber.open(file_obj) as pdf:
        for page in pdf.pages:
            clean_page = page.filter(lambda obj: 
                obj.get("object_type") != "char" or 
                obj.get("size", 0) <= 20
            )
            text = clean_page.extract_text()
            if text:
                all_text.append(text)
    return "\n".join(all_text)


def is_valid_student_text(text):
    """Guardrail: Checks if the parsed text contains actual student data"""
    safe_text = str(text) if text else ""
    has_student_number = re.search(r"Student Number:\s*\d+", safe_text, re.IGNORECASE)
    has_record_of = re.search(r"Record of:\s*[A-Za-z]+", safe_text, re.IGNORECASE)
    return bool(has_student_number and has_record_of)


@lru_cache(maxsize=1) # Caches the JSON in RAM for performance boost
def load_catalog_courses():
    json_path = os.path.join(settings.BASE_DIR, "grids", "data", "course_listing.json")
    
    if not os.path.exists(json_path):
        return []
    
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    courses = []
    for subject, levels in data.items():
        for level_name, clist in levels.items():
            for c in clist:
                # Safely split the course code to prevent startup crashes
                parts = c["code"].split()
                subj_code = parts[0] if len(parts) > 0 else "UNKNOWN"
                num_code = parts[1] if len(parts) > 1 else "0000"
                
                # Strip non-numeric characters from num_code just in case
                clean_num = ''.join(filter(str.isdigit, num_code))
                final_num = int(clean_num) if clean_num else 0

                courses.append(
                    Course(
                        subject=subj_code,
                        number=final_num,
                        title=c.get("title", "Unknown Title"),
                        credits=float(c.get("credits", 0.0)),
                    )
                )
    return tuple(courses)


def build_student_result_dict(student_number, name, programme, major, gpa, can_graduate):
    """helper to prevent duplicating dictionary creation"""
    return {
        "student_number": student_number,
        "name": name,
        "programme": programme,
        "major": major,
        "gpa": gpa,
        "can_graduate": can_graduate,
        "detail_url": f"/grid/{student_number}/",
    }


def save_bucket_to_db(audit, component_name, b_result, student):
    """Extracted from post() to improve readability and testing"""
    completed_courses = []
    courses_needed = []
    is_all_req = False

    for rule in b_result.rule_results:
        if rule.requirement_type == "all_credits_from":
            is_all_req = True
        courses_needed.extend(rule.courses_needed)
        for code in rule.courses_used:
            sc = _find_course(student, code)
            if sc:
                completed_courses.append({
                    "code": sc.course_code,
                    "grade": sc.grade,
                    "credits": sc.credits,
                })

    BucketResult.objects.create(
        audit=audit,
        component_name=component_name,
        bucket_name=b_result.bucket_name,
        is_met=b_result.is_met,
        credits_earned=b_result.credits_earned,
        credits_required=b_result.credits_required,
        is_all_required=is_all_req,
        courses_completed_json=completed_courses,
        courses_needed_json=courses_needed,
    )


from django.db.models import Prefetch

# --- CLASS BASED VIEWS ---

class UploadGridView(LoginRequiredMixin, View):
    template_name = "upload.html"

    def get(self, request, *args, **kwargs):
        # Prefetch grabs all related audits in a single bulk database query, 
        # rather than querying the database 1,000 times for 1,000 students.
        profiles = StudentProfile.objects.prefetch_related(
            Prefetch('audits', queryset=AuditRecord.objects.order_by("-audit_date"))
        )
        
        results = []
        can_graduate_count = 0
        cannot_graduate_count = 0

        for profile in profiles:
            # Because of prefetch, this is now an instant RAM lookup, not a DB hit
            latest_audit = profile.audits.first()
            if latest_audit:
                if latest_audit.can_graduate:
                    can_graduate_count += 1
                else:
                    cannot_graduate_count += 1

                results.append(build_student_result_dict(
                    profile.student_number, profile.name, profile.programme, 
                    profile.major, profile.overall_gpa, latest_audit.can_graduate
                ))

        summary = {
            "total_students": len(profiles),
            "can_graduate": can_graduate_count,
            "cannot_graduate": cannot_graduate_count,
        }

        return render(request, self.template_name, {
            "last_results": results,
            "last_summary": summary,
        })


    def post(self, request, *args, **kwargs):
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return JsonResponse({"error": "No file uploaded"}, status=400)

        # Prevents Out-Of-Memory (OOM) Denial of Service attacks
        MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB Limit
        if uploaded_file.size > MAX_UPLOAD_SIZE:
            return JsonResponse({"error": "File size exceeds the 5MB limit. Please upload a smaller document."}, status=400)

        try:
            filename = uploaded_file.name.lower()
            raw_text = ""
            
            # Read the file bytes safely into memory once
            file_bytes = uploaded_file.read()

            # 1. ROUTING
            if filename.endswith(".pdf"):
                # Check PDF Magic Bytes to prevent renamed malware files
                if not file_bytes.startswith(b"%PDF"):
                    return JsonResponse({"error": "Invalid file format. The uploaded file is not a valid PDF document."}, status=400)
                
                pdf_io = io.BytesIO(file_bytes)
                is_transcript = False
                
                # Peek safely
                with pdfplumber.open(pdf_io) as pdf:
                    # Guard against 0-page/corrupt PDFs
                    if not pdf.pages:
                        return JsonResponse({"error": "The uploaded PDF contains no readable pages."}, status=400)
                        
                    first_page_text = pdf.pages[0].extract_text() or ""
                    if "UNOFFICIAL TRANSCRIPT" in first_page_text:
                        is_transcript = True
                
                pdf_io.seek(0)
                
                if is_transcript:
                    raw_text = extract_text_from_transcript_pdf(pdf_io)
                else:
                    raw_text = extract_text_from_grid_pdf(pdf_io)

            elif filename.endswith(".txt"):
                try:
                    raw_text = file_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    return JsonResponse({"error": "Text file must be UTF-8 encoded. If using Windows, save as UTF-8."}, status=400)
            else:
                return JsonResponse({"error": "Unsupported file type. Please upload a .pdf or .txt file."}, status=400)

            # 2. VALIDATION
            if not is_valid_student_text(raw_text):
                return JsonResponse({
                    "error": "The uploaded file appears to be redacted or is missing critical student identification data (Student Number, Name). Please upload an unredacted PDF or a formatted TXT file."
                }, status=400)

            # 3. PROCEED TO PARSING
            try:
                detected_dtype = identify_doc_type(raw_text)
            except ValueError as e:
                return JsonResponse({"error": str(e)}, status=400)

            students = parse_text(raw_text, dtype=detected_dtype)

            # Prevent server lockup from massive batch files
            MAX_BATCH_SIZE = 300
            if len(students) > MAX_BATCH_SIZE:
                return JsonResponse({
                    "error": f"File contains {len(students)} students. The maximum allowed per upload is {MAX_BATCH_SIZE}. Please split the file and try again."
                }, status=400)

            # VIRTUAL CATALOG INJECTION
            catalog_courses = list(load_catalog_courses())
            existing_codes = {c.code for c in catalog_courses}

            for student in students:
                for term in student.terms:
                    for sc in term.courses:
                        if sc.course_code not in existing_codes:
                            virtual_course = Course(
                                subject=sc.subject,
                                number=sc.number,
                                title=sc.title,
                                credits=sc.credits,
                                code=sc.course_code,
                                level=sc.level,
                            )
                            catalog_courses.append(virtual_course)
                            existing_codes.add(sc.course_code)

            evaluator = RequirementEvaluator(courses=catalog_courses)
            results, can_graduate_count, cannot_graduate_count = [], 0, 0

            for student in students:
                degree = Degree.from_student_data(student)
                result = evaluator.evaluate_degree(student, degree)

                can_graduate = len(result.unmet_requirements) == 0
                if can_graduate:
                    can_graduate_count += 1
                else:
                    cannot_graduate_count += 1

                prog_name = student.programme.programme if student.programme else ""
                major_name = student.programme.major if student.programme else ""

                # Atomic Transaction ensures no orphaned records if a crash occurs mid-save
                with transaction.atomic():
                    # 1. Save Profile
                    profile, _ = StudentProfile.objects.update_or_create(
                        student_number=student.student_number,
                        defaults={
                            "name": student.name,
                            "programme": prog_name,
                            "major": major_name,
                            "overall_gpa": student.overall_gpa,
                        },
                    )

                    # 2. Save Audit Record
                    audit = AuditRecord.objects.create(
                        student=profile,
                        evaluated_programme=prog_name,
                        evaluated_major=major_name,
                        can_graduate=can_graduate,
                        total_credits_earned=result.total_credits_earned,
                        total_credits_required=result.total_credits_required,
                        overall_progress=result.overall_progress,
                        unmet_requirements_json=result.unmet_requirements,
                        next_steps_json=result.next_steps,
                    )

                    # 3. Save Buckets
                    for major in result.major_results:
                        for b_result in major.bucket_results:
                            save_bucket_to_db(audit, major.component_name, b_result, student)

                    for g_result in result.general_requirements:
                        save_bucket_to_db(audit, "General Requirements", g_result, student)

                # Use the dictionary helper outside the transaction
                results.append(build_student_result_dict(
                    student.student_number, student.name, prog_name, major_name, 
                    student.overall_gpa, can_graduate
                ))

            summary = {
                "total_students": len(students),
                "can_graduate": can_graduate_count,
                "cannot_graduate": cannot_graduate_count,
            }

            return JsonResponse({"summary": summary, "results": results})

        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"CRITICAL PARSE ERROR: {str(e)}", exc_info=True)
            
            return JsonResponse({
                "error": "An unexpected system error occurred while processing the document. Please ensure the file is a valid format."
            }, status=500)


class StudentDetailView(LoginRequiredMixin, View):
    template_name = "student_details.html"

    def get(self, request, student_number, *args, **kwargs):
        # Prefetch the audits here, ensuring we only make one query for the audit list
        profile = get_object_or_404(
            StudentProfile.objects.prefetch_related(
                Prefetch('audits', queryset=AuditRecord.objects.order_by("-audit_date"))
            ), 
            student_number=student_number
        )
        
        audit = profile.audits.first()
        
        if not audit:
            return redirect("upload_grid")

        return render(request, self.template_name, {"student": profile, "audit": audit})