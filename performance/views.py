from django.views import View
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib.auth.mixins import LoginRequiredMixin


# Student Grids imports
from grids.models import Degree
from grids.models.evaluation import MAJORS
from grids.evaluation.rule_engine import RequirementEvaluator, _find_course
from grids.parsing.parser_service import parse_text


class UploadGridView(LoginRequiredMixin, View):
    template_name = "upload.html"
    
    def get(self, request, *args, **kwargs):
        last_results = request.session.get('last_results', [])
        last_summary = request.session.get('last_summary', {})
        return render(request, self.template_name, {
            "last_results": last_results,
            "last_summary": last_summary
        })
    
    def post(self, request, *args, **kwargs):
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return JsonResponse({"error": "No file uploaded"}, status=400)

        try:
            raw_text = uploaded_file.read().decode("utf-8")
            request.session["last_uploaded_text"] = raw_text

            students = parse_text(raw_text, dtype="GRID")
            evaluator = RequirementEvaluator(courses=[])

            results = []
            can_graduate_count = 0
            cannot_graduate_count = 0

            for student in students:
                degree = Degree.from_student_data(student)
                result = evaluator.evaluate_degree(student, degree)

                can_graduate = len(result.unmet_requirements) == 0
                if can_graduate:
                    can_graduate_count += 1
                else:
                    cannot_graduate_count += 1

                results.append({
                    "student_number": student.student_number,
                    "name": student.name,
                    "programme": student.programme.programme if student.programme else "Unknown",
                    "major": student.programme.major if student.programme else "Unknown",
                    "gpa": student.overall_gpa,
                    "can_graduate": can_graduate,
                    "unmet_requirements": result.unmet_requirements,
                    "detail_url": f"/grid/{student.student_number}/"
                })

            summary = {
                "total_students": len(students),
                "can_graduate": can_graduate_count,
                "cannot_graduate": cannot_graduate_count,
            }

            request.session['last_results'] = results
            request.session['last_summary'] = summary

            return JsonResponse({"summary": summary, "results": results})

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)


class StudentDetailView(LoginRequiredMixin, View):
    template_name = "student_details.html"

    def get(self, request, student_number, *args, **kwargs):
        raw_text = request.session.get("last_uploaded_text")
        if not raw_text:
            return redirect("upload_grid")

        students = parse_text(raw_text, dtype="GRID")
        student = next((s for s in students if s.student_number == student_number), None)
        if not student:
            return JsonResponse({"error": "Student not found"}, status=404)

        evaluator = RequirementEvaluator(courses=[])
        degree = Degree.from_student_data(student)
        result = evaluator.evaluate_degree(student, degree)

        # Attach courses and remaining requirements to each bucket
        for major in result.major_results:
            for bucket in major.bucket_results:
                bucket.courses = [
                    _find_course(student, code)
                    for rule in bucket.rule_results
                    for code in rule.courses_used
                    if _find_course(student, code) is not None
                ]
                bucket.courses_needed = []
                bucket.is_all_required = False
                for rule in bucket.rule_results:
                    if rule.requirement_type == "all_credits_from":
                        bucket.is_all_required = True
                    bucket.courses_needed.extend(rule.courses_needed)

        context = {
            "student": student,
            "result": result,
        }
        return render(request, self.template_name, context)