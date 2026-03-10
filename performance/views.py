import os
import json
from django.views import View
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.mixins import LoginRequiredMixin

from grids.models import Degree, Course
from grids.evaluation.rule_engine import RequirementEvaluator, _find_course
from grids.parsing.parser_service import parse_text
from .models import StudentProfile, AuditRecord, BucketResult


def load_catalog_courses():
    json_path = os.path.join("grids", "data", "course_listing.json")
    if not os.path.exists(json_path):
        return []
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    courses = []
    for subject, levels in data.items():
        for level_name, clist in levels.items():
            for c in clist:
                subj_code, num_code = c["code"].split()
                courses.append(
                    Course(
                        subject=subj_code,
                        number=int(num_code),
                        title=c["title"],
                        credits=float(c["credits"]),
                    )
                )
    return courses

class UploadGridView(LoginRequiredMixin, View):
    template_name = "upload.html"

    def get(self, request, *args, **kwargs):
        # 1. Fetch all students permanently stored in the database
        profiles = StudentProfile.objects.all()
        
        results = []
        can_graduate_count = 0
        cannot_graduate_count = 0

        # 2. Rebuild the results list dynamically
        for profile in profiles:
            # Grab the most recent audit for this student
            latest_audit = profile.audits.order_by("-audit_date").first()
            
            if latest_audit:
                if latest_audit.can_graduate:
                    can_graduate_count += 1
                else:
                    cannot_graduate_count += 1
                    
                results.append({
                    "student_number": profile.student_number,
                    "name": profile.name,
                    "programme": profile.programme,
                    "major": profile.major,
                    "gpa": profile.overall_gpa,
                    "can_graduate": latest_audit.can_graduate,
                    "detail_url": f"/grid/{profile.student_number}/",
                })

        # 3. Rebuild the summary
        summary = {
            "total_students": len(profiles),
            "can_graduate": can_graduate_count,
            "cannot_graduate": cannot_graduate_count,
        }

        # 4. Render the template using the database-backed data
        return render(
            request,
            self.template_name,
            {
                "last_results": results,
                "last_summary": summary,
            }
        )

    def post(self, request, *args, **kwargs):
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return JsonResponse({"error": "No file uploaded"}, status=400)

        try:
            raw_text = uploaded_file.read().decode("utf-8")
            students = parse_text(raw_text, dtype="GRID")

            # VIRTUAL CATALOG INJECTION
            # Ensure the web UI sees legacy and out-of-faculty courses.
            catalog_courses = load_catalog_courses()
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

            # Initialize evaluator with the enriched catalog
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

                # 3. Helper to save buckets
                def save_bucket(component_name, b_result):
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
                                completed_courses.append(
                                    {
                                        "code": sc.course_code,
                                        "grade": sc.grade,
                                        "credits": sc.credits,
                                    }
                                )

                    from .models import (
                        BucketResult,
                    )  # Ensure this is imported at top of file

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

                # Save Major Buckets
                for major in result.major_results:
                    for b_result in major.bucket_results:
                        save_bucket(major.component_name, b_result)

                # Save General Buckets
                for g_result in result.general_requirements:
                    save_bucket("General Requirements", g_result)

                results.append(
                    {
                        "student_number": student.student_number,
                        "name": student.name,
                        "programme": prog_name,
                        "major": major_name,
                        "gpa": student.overall_gpa,
                        "can_graduate": can_graduate,
                        "detail_url": f"/grid/{student.student_number}/",
                    }
                )

            summary = {
                "total_students": len(students),
                "can_graduate": can_graduate_count,
                "cannot_graduate": cannot_graduate_count,
            }

            return JsonResponse({"summary": summary, "results": results})

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)


class StudentDetailView(LoginRequiredMixin, View):
    template_name = "student_details.html"

    def get(self, request, student_number, *args, **kwargs):
        profile = get_object_or_404(StudentProfile, student_number=student_number)

        # Grab the most recent audit
        audit = profile.audits.order_by("-audit_date").first()
        if not audit:
            return redirect("upload_grid")

        return render(request, self.template_name, {"student": profile, "audit": audit})
