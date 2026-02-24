# Django imports
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt

# Student Grids imports
from .forms import EmailLoginForm
from grids.models import Degree
from grids.models.evaluation import MAJORS
from grids.evaluation.rule_engine import RequirementEvaluator, _find_course
from grids.parsing.parser_service import parse_text


def login_view(request):
    next_url = request.GET.get("next", "home")

    if request.method == "POST":
        form = EmailLoginForm(request.POST)
        if form.is_valid():
            login(request, form.cleaned_data["user"])
            return redirect(next_url) 
    else:
        form = EmailLoginForm()

    return render(request, "login.html", {"form": form})


@login_required
def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
def home(request):
    return render(request, "index.html")


@login_required
def upload_grid(request):
    if request.method == "POST":
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return JsonResponse({"error": "No file uploaded"}, status=400)

        try:
            raw_text = uploaded_file.read().decode("utf-8")

            # Save raw uploaded text in session for detail view
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
                    # Add link to details page
                    "detail_url": f"/grid/{student.student_number}/"
                })

            summary = {
                "total_students": len(students),
                "can_graduate": can_graduate_count,
                "cannot_graduate": cannot_graduate_count,
            }

            # Save in session
            request.session['last_results'] = results
            request.session['last_summary'] = summary

            return JsonResponse({"summary": summary, "results": results})

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)

    # GET request -> render page and load session results if available
    last_results = request.session.get('last_results', [])
    last_summary = request.session.get('last_summary', {})
    return render(request, "upload.html", {"last_results": last_results, "last_summary": last_summary})


@login_required
def student_detail(request, student_number):
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
            # Completed courses
            bucket.courses = [
                _find_course(student, code)
                for rule in bucket.rule_results
                for code in rule.courses_used
                if _find_course(student, code) is not None
            ]
            # Courses still needed
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
    return render(request, "student_detail.html", context)