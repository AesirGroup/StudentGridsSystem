from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import AuditRecord, BucketResult, StudentProfile


# --- MODEL TESTS ---


class StudentProfileModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.profile = StudentProfile.objects.create(
            student_number="816001",
            name="Jane Doe",
            programme="BSc Computer Science",
            major="Computer Science",
            overall_gpa=3.5,
        )

    def test_student_profile_str(self):
        self.assertEqual(str(self.profile), "Jane Doe (816001)")

    def test_student_profile_fields(self):
        self.assertEqual(self.profile.student_number, "816001")
        self.assertEqual(self.profile.name, "Jane Doe")
        self.assertEqual(self.profile.programme, "BSc Computer Science")
        self.assertEqual(self.profile.major, "Computer Science")
        self.assertEqual(self.profile.overall_gpa, 3.5)

    def test_flr_exempt_verified_defaults_to_false(self):
        self.assertFalse(self.profile.flr_exempt_verified)


class AuditRecordModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.profile = StudentProfile.objects.create(
            student_number="816002",
            name="John Smith",
        )
        cls.audit = AuditRecord.objects.create(
            student=cls.profile,
            evaluated_programme="BSc Computer Science",
            evaluated_major="Computer Science",
            can_graduate=True,
            total_credits_earned=90.0,
            total_credits_required=90.0,
            overall_progress="90/90",
            unmet_requirements_json=[],
            next_steps_json=[],
        )

    def test_audit_record_str(self):
        self.assertIn("816002", str(self.audit))

    def test_audit_record_fields(self):
        self.assertTrue(self.audit.can_graduate)
        self.assertEqual(self.audit.total_credits_earned, 90.0)
        self.assertEqual(self.audit.total_credits_required, 90.0)
        self.assertEqual(self.audit.overall_progress, "90/90")

    def test_audit_record_related_name(self):
        self.assertEqual(self.profile.audits.count(), 1)
        self.assertEqual(self.profile.audits.first(), self.audit)


class BucketResultModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.profile = StudentProfile.objects.create(
            student_number="816003",
            name="Alice Brown",
        )
        cls.audit = AuditRecord.objects.create(
            student=cls.profile,
            can_graduate=False,
        )
        cls.bucket = BucketResult.objects.create(
            audit=cls.audit,
            component_name="Computer Science",
            bucket_name="Core Courses",
            is_met=False,
            credits_earned=12.0,
            credits_required=18.0,
        )

    def test_bucket_result_str_unmet(self):
        self.assertEqual(str(self.bucket), "Core Courses: UNMET")

    def test_bucket_result_str_met(self):
        self.bucket.is_met = True
        self.bucket.save()
        self.assertEqual(str(self.bucket), "Core Courses: MET")
        # Reset for other tests
        self.bucket.is_met = False
        self.bucket.save()

    def test_bucket_result_fields(self):
        self.assertEqual(self.bucket.component_name, "Computer Science")
        self.assertEqual(self.bucket.credits_earned, 12.0)
        self.assertEqual(self.bucket.credits_required, 18.0)

    def test_bucket_result_related_name(self):
        self.assertEqual(self.audit.bucket_results.count(), 1)


# --- UPLOAD GRID VIEW TESTS ---


class UploadGridViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="advisor",
            email="advisor@test.com",
            password="testpass123",
        )
        cls.profile = StudentProfile.objects.create(
            student_number="816010",
            name="Test Student",
            programme="BSc Computer Science",
            major="Computer Science",
            overall_gpa=3.2,
        )
        cls.audit = AuditRecord.objects.create(
            student=cls.profile,
            evaluated_programme="BSc Computer Science",
            evaluated_major="Computer Science",
            can_graduate=True,
            total_credits_earned=90.0,
            total_credits_required=90.0,
            overall_progress="90/90",
        )

    def test_url_exists_at_correct_location(self):
        self.client.login(username="advisor", password="testpass123")
        response = self.client.get("/performance/upload/")
        self.assertEqual(response.status_code, 200)

    def test_upload_grid_view_name(self):
        self.client.login(username="advisor", password="testpass123")
        response = self.client.get(reverse("upload_grid"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "upload_grid.html")

    def test_upload_grid_redirects_unauthenticated_user(self):
        response = self.client.get(reverse("upload_grid"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/", response["Location"])

    def test_upload_grid_get_contains_student_data(self):
        self.client.login(username="advisor", password="testpass123")
        response = self.client.get(reverse("upload_grid"))
        self.assertContains(response, "Test Student")

    def test_upload_grid_post_no_file_returns_400(self):
        self.client.login(username="advisor", password="testpass123")
        response = self.client.post(reverse("upload_grid"), {})
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_upload_grid_post_unsupported_file_type_returns_400(self):
        self.client.login(username="advisor", password="testpass123")
        from django.core.files.uploadedfile import SimpleUploadedFile
        bad_file = SimpleUploadedFile("data.csv", b"col1,col2", content_type="text/csv")
        response = self.client.post(reverse("upload_grid"), {"file": bad_file})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Unsupported file type", response.json()["error"])

    def test_upload_grid_post_oversized_file_returns_400(self):
        self.client.login(username="advisor", password="testpass123")
        from django.core.files.uploadedfile import SimpleUploadedFile
        big_file = SimpleUploadedFile(
            "big.pdf",
            b"%PDF" + b"x" * (51 * 1024 * 1024),
            content_type="application/pdf",
        )
        response = self.client.post(reverse("upload_grid"), {"file": big_file})
        self.assertEqual(response.status_code, 400)

    def test_upload_grid_post_invalid_pdf_magic_bytes_returns_400(self):
        self.client.login(username="advisor", password="testpass123")
        from django.core.files.uploadedfile import SimpleUploadedFile
        fake_pdf = SimpleUploadedFile(
            "fake.pdf", b"NOTAPDF content here", content_type="application/pdf"
        )
        response = self.client.post(reverse("upload_grid"), {"file": fake_pdf})
        self.assertEqual(response.status_code, 400)
        self.assertIn("not a valid PDF", response.json()["error"])

    def test_upload_grid_post_txt_non_utf8_returns_400(self):
        self.client.login(username="advisor", password="testpass123")
        from django.core.files.uploadedfile import SimpleUploadedFile
        bad_txt = SimpleUploadedFile(
            "data.txt", b"\xff\xfe invalid bytes", content_type="text/plain"
        )
        response = self.client.post(reverse("upload_grid"), {"file": bad_txt})
        self.assertEqual(response.status_code, 400)
        self.assertIn("UTF-8", response.json()["error"])

    def test_upload_grid_post_txt_missing_student_data_returns_400(self):
        self.client.login(username="advisor", password="testpass123")
        from django.core.files.uploadedfile import SimpleUploadedFile
        empty_txt = SimpleUploadedFile(
            "data.txt", b"Some random text with no student info.", content_type="text/plain"
        )
        response = self.client.post(reverse("upload_grid"), {"file": empty_txt})
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())


# --- STUDENT DETAIL VIEW TESTS ---


class StudentDetailViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="advisor2",
            email="advisor2@test.com",
            password="testpass123",
        )
        cls.profile = StudentProfile.objects.create(
            student_number="816020",
            name="Detail Student",
            programme="BSc Computer Science",
            major="Computer Science",
            overall_gpa=3.0,
        )
        cls.audit = AuditRecord.objects.create(
            student=cls.profile,
            evaluated_programme="BSc Computer Science",
            evaluated_major="Computer Science",
            can_graduate=False,
            total_credits_earned=60.0,
            total_credits_required=90.0,
            overall_progress="60/90",
            unmet_requirements_json=["Missing COMP 3000"],
            next_steps_json=["Complete COMP 3000"],
        )

    def test_url_exists_at_correct_location(self):
        self.client.login(username="advisor2", password="testpass123")
        response = self.client.get("/performance/816020/")
        self.assertEqual(response.status_code, 200)

    def test_student_detail_view_name(self):
        self.client.login(username="advisor2", password="testpass123")
        response = self.client.get(
            reverse("student_detail", kwargs={"student_number": 816020})
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "student_details.html")

    def test_student_detail_redirects_unauthenticated_user(self):
        response = self.client.get(
            reverse("student_detail", kwargs={"student_number": 816020})
        )
        self.assertEqual(response.status_code, 302)

    def test_student_detail_contains_student_name(self):
        self.client.login(username="advisor2", password="testpass123")
        response = self.client.get(
            reverse("student_detail", kwargs={"student_number": 816020})
        )
        self.assertContains(response, "Detail Student")

    def test_student_detail_nonexistent_student_returns_404(self):
        self.client.login(username="advisor2", password="testpass123")
        response = self.client.get(
            reverse("student_detail", kwargs={"student_number": 999999})
        )
        self.assertEqual(response.status_code, 404)

    def test_student_detail_no_audit_redirects(self):
        self.client.login(username="advisor2", password="testpass123")
        # Create a profile with no audit
        StudentProfile.objects.create(
            student_number="816021",
            name="No Audit Student",
        )
        response = self.client.get(
            reverse("student_detail", kwargs={"student_number": 816021})
        )
        self.assertEqual(response.status_code, 302)


# --- TOGGLE FLR EXEMPTION VIEW TESTS ---


class ToggleFLRExemptionViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="advisor3",
            email="advisor3@test.com",
            password="testpass123",
        )
        cls.profile = StudentProfile.objects.create(
            student_number="816030",
            name="FLR Student",
            flr_exempt_verified=False,
        )
        # Required so student_detail returns 200 instead of redirecting again
        AuditRecord.objects.create(
            student=cls.profile,
            can_graduate=False,
        )

    def test_toggle_flr_redirects_unauthenticated_user(self):
        response = self.client.post(
            reverse("toggle_flr_exemption", kwargs={"student_number": 816030})
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/", response["Location"])

    def test_toggle_flr_sets_true_when_false(self):
        self.client.login(username="advisor3", password="testpass123")
        self.client.post(
            reverse("toggle_flr_exemption", kwargs={"student_number": 816030})
        )
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.flr_exempt_verified)

    def test_toggle_flr_sets_false_when_true(self):
        self.client.login(username="advisor3", password="testpass123")
        self.profile.flr_exempt_verified = True
        self.profile.save()
        self.client.post(
            reverse("toggle_flr_exemption", kwargs={"student_number": 816030})
        )
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.flr_exempt_verified)

    def test_toggle_flr_redirects_to_student_detail_after_post(self):
        self.client.login(username="advisor3", password="testpass123")
        response = self.client.post(
            reverse("toggle_flr_exemption", kwargs={"student_number": 816030})
        )
        self.assertRedirects(
            response,
            reverse("student_detail", kwargs={"student_number": 816030}),
        )

    def test_toggle_flr_nonexistent_student_returns_404(self):
        self.client.login(username="advisor3", password="testpass123")
        response = self.client.post(
            reverse("toggle_flr_exemption", kwargs={"student_number": 999999})
        )
        self.assertEqual(response.status_code, 404)


# --- REPORT VIEW TESTS ---


class ReportViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="advisor4",
            email="advisor4@test.com",
            password="testpass123",
        )

    def test_url_exists_at_correct_location(self):
        self.client.login(username="advisor4", password="testpass123")
        response = self.client.get("/performance/report/")
        self.assertEqual(response.status_code, 200)

    def test_report_view_name(self):
        self.client.login(username="advisor4", password="testpass123")
        response = self.client.get(reverse("report"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "report.html")

    def test_report_redirects_unauthenticated_user(self):
        response = self.client.get(reverse("report"))
        self.assertEqual(response.status_code, 302)


# --- REPORT STUDENTS API TESTS ---


class ReportStudentsViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="advisor5",
            email="advisor5@test.com",
            password="testpass123",
        )
        cls.profile1 = StudentProfile.objects.create(
            student_number="816040",
            name="Alpha Student",
            programme="BSc CS",
            major="CS",
            overall_gpa=3.8,
        )
        cls.profile2 = StudentProfile.objects.create(
            student_number="816041",
            name="Beta Student",
            programme="BSc IT",
            major="IT",
            overall_gpa=2.9,
        )
        AuditRecord.objects.create(
            student=cls.profile1,
            can_graduate=True,
            total_credits_earned=90.0,
            total_credits_required=90.0,
            overall_progress="90/90",
        )
        AuditRecord.objects.create(
            student=cls.profile2,
            can_graduate=False,
            total_credits_earned=45.0,
            total_credits_required=90.0,
            overall_progress="45/90",
        )

    def test_report_students_returns_all_students(self):
        self.client.login(username="advisor5", password="testpass123")
        response = self.client.get(reverse("report_students"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("students", data)
        self.assertEqual(len(data["students"]), 2)

    def test_report_students_filter_by_ids(self):
        self.client.login(username="advisor5", password="testpass123")
        response = self.client.get(reverse("report_students") + "?ids=816040")
        data = response.json()
        self.assertEqual(len(data["students"]), 1)
        self.assertEqual(data["students"][0]["student_number"], "816040")

    def test_report_students_redirects_unauthenticated_user(self):
        response = self.client.get(reverse("report_students"))
        self.assertEqual(response.status_code, 302)

    def test_report_students_returns_expected_fields(self):
        self.client.login(username="advisor5", password="testpass123")
        response = self.client.get(reverse("report_students") + "?ids=816040")
        student = response.json()["students"][0]
        for field in [
            "student_number", "name", "programme", "major",
            "gpa", "can_graduate", "credits_earned",
            "credits_required", "overall_progress",
        ]:
            self.assertIn(field, student)


# --- STUDENT REPORT DATA VIEW TESTS ---


class StudentReportDataViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="advisor6",
            email="advisor6@test.com",
            password="testpass123",
        )
        cls.profile = StudentProfile.objects.create(
            student_number="816050",
            name="Report Data Student",
            programme="BSc CS",
            major="CS",
            overall_gpa=3.1,
        )
        cls.audit = AuditRecord.objects.create(
            student=cls.profile,
            evaluated_programme="BSc CS",
            evaluated_major="CS",
            can_graduate=True,
            total_credits_earned=90.0,
            total_credits_required=90.0,
            overall_progress="90/90",
            unmet_requirements_json=[],
            next_steps_json=[],
        )
        cls.no_audit_profile = StudentProfile.objects.create(
            student_number="816051",
            name="No Audit Report Student",
        )

    def test_url_exists_at_correct_location(self):
        self.client.login(username="advisor6", password="testpass123")
        response = self.client.get("/performance/api/student-report-data/816050/")
        self.assertEqual(response.status_code, 200)

    def test_student_report_data_view_name(self):
        self.client.login(username="advisor6", password="testpass123")
        response = self.client.get(
            reverse("student_report_data", kwargs={"student_number": 816050})
        )
        self.assertEqual(response.status_code, 200)

    def test_student_report_data_returns_expected_fields(self):
        self.client.login(username="advisor6", password="testpass123")
        response = self.client.get(
            reverse("student_report_data", kwargs={"student_number": 816050})
        )
        data = response.json()
        self.assertTrue(data["has_audit"])
        self.assertTrue(data["can_graduate"])
        self.assertEqual(data["name"], "Report Data Student")
        self.assertEqual(data["total_credits_earned"], 90.0)

    def test_student_report_data_no_audit_returns_has_audit_false(self):
        self.client.login(username="advisor6", password="testpass123")
        response = self.client.get(
            reverse("student_report_data", kwargs={"student_number": 816051})
        )
        data = response.json()
        self.assertFalse(data["has_audit"])
        self.assertFalse(data["can_graduate"])

    def test_student_report_data_nonexistent_returns_404(self):
        self.client.login(username="advisor6", password="testpass123")
        response = self.client.get(
            reverse("student_report_data", kwargs={"student_number": 999999})
        )
        self.assertEqual(response.status_code, 404)

    def test_student_report_data_redirects_unauthenticated_user(self):
        response = self.client.get(
            reverse("student_report_data", kwargs={"student_number": 816050})
        )
        self.assertEqual(response.status_code, 302)


# --- TRANSCRIPT GRID VIEW TESTS ---


class TranscriptGridViewTests(TestCase):
    def test_url_exists_at_correct_location(self):
        response = self.client.get("/performance/transcript/")
        self.assertEqual(response.status_code, 200)

    def test_transcript_grid_view_name(self):
        response = self.client.get(reverse("transcript_grid"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "upload_transcript.html")

    def test_transcript_grid_accessible_without_login(self):
        # TranscriptGridView has no LoginRequiredMixin — public access is intentional
        response = self.client.get(reverse("transcript_grid"))
        self.assertEqual(response.status_code, 200)

    def test_transcript_grid_post_no_file_returns_400(self):
        response = self.client.post(reverse("transcript_grid"), {})
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_transcript_grid_post_unsupported_file_type_returns_400(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        bad_file = SimpleUploadedFile("data.csv", b"col1,col2", content_type="text/csv")
        response = self.client.post(reverse("transcript_grid"), {"file": bad_file})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Unsupported file type", response.json()["error"])

    def test_transcript_grid_post_invalid_pdf_magic_bytes_returns_400(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        fake_pdf = SimpleUploadedFile(
            "fake.pdf", b"NOTAPDF content here", content_type="application/pdf"
        )
        response = self.client.post(reverse("transcript_grid"), {"file": fake_pdf})
        self.assertEqual(response.status_code, 400)
        self.assertIn("not a valid PDF", response.json()["error"])

    def test_transcript_grid_post_txt_non_utf8_returns_400(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        bad_txt = SimpleUploadedFile(
            "data.txt", b"\xff\xfe invalid bytes", content_type="text/plain"
        )
        response = self.client.post(reverse("transcript_grid"), {"file": bad_txt})
        self.assertEqual(response.status_code, 400)
        self.assertIn("UTF-8", response.json()["error"])

    def test_transcript_grid_post_txt_missing_student_data_returns_400(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        empty_txt = SimpleUploadedFile(
            "data.txt", b"Random text with no student info.", content_type="text/plain"
        )
        response = self.client.post(reverse("transcript_grid"), {"file": empty_txt})
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_transcript_grid_get_uses_session_data(self):
        session = self.client.session
        session["last_results"] = [{"name": "Session Student"}]
        session["last_summary"] = {"total_students": 1}
        session.save()
        response = self.client.get(reverse("transcript_grid"))
        self.assertEqual(response.status_code, 200)
        # The view passes session data into the template context;
        # the upload_transcript.html template does not render it in the HTML,
        # so we verify via context rather than the rendered output.
        self.assertEqual(response.context["last_results"], [{"name": "Session Student"}])
        self.assertEqual(response.context["last_summary"], {"total_students": 1})


# --- TRANSCRIPT STUDENT DETAIL VIEW TESTS ---


class TranscriptStudentDetailViewTests(TestCase):
    def setUp(self):
        # Use setUp (not setUpTestData) because we write to the session per test
        self.student_number = "816060"
        session = self.client.session
        session["preview_students"] = {
            self.student_number: {
                "student_number": self.student_number,
                "name": "Preview Student",
                "overall_gpa": 3.3,
                "audit": {
                    "evaluated_programme": "BSc CS",
                    "evaluated_major": "CS",
                    "can_graduate": False,
                    "total_credits_earned": 50.0,
                    "total_credits_required": 90.0,
                    "overall_progress": "50/90",
                    "unmet_requirements_json": ["COMP 3000"],
                    "next_steps_json": ["Complete COMP 3000"],
                    "bucket_results": [],
                },
            }
        }
        session.save()

    def test_url_exists_at_correct_location(self):
        response = self.client.get(f"/performance/transcript/{self.student_number}/")
        self.assertEqual(response.status_code, 200)

    def test_transcript_student_detail_view_name(self):
        response = self.client.get(
            reverse(
                "transcript_student_detail",
                kwargs={"student_number": int(self.student_number)},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "student_details.html")

    def test_transcript_student_detail_contains_student_name(self):
        response = self.client.get(
            reverse(
                "transcript_student_detail",
                kwargs={"student_number": int(self.student_number)},
            )
        )
        self.assertContains(response, "Preview Student")

    def test_transcript_student_detail_no_session_redirects(self):
        # Clear the session so there is no preview data
        session = self.client.session
        session["preview_students"] = {}
        session.save()
        response = self.client.get(
            reverse(
                "transcript_student_detail",
                kwargs={"student_number": int(self.student_number)},
            )
        )
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("transcript_grid"))

    def test_transcript_student_detail_accessible_without_login(self):
        # No LoginRequiredMixin on this view — public access is intentional
        response = self.client.get(
            reverse(
                "transcript_student_detail",
                kwargs={"student_number": int(self.student_number)},
            )
        )
        self.assertEqual(response.status_code, 200)