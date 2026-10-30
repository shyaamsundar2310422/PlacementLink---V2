import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import config
from services import file_storage


ROOT = Path(__file__).resolve().parents[1]


class FreeDeploymentConfigTests(unittest.TestCase):
    def test_free_blueprint_uses_free_plan_without_local_persistent_disk(self):
        blueprint = (ROOT / "render-free.yaml").read_text(encoding="utf-8")
        self.assertIn("plan: free", blueprint)
        self.assertIn("FILE_STORAGE_BACKEND\n        value: supabase", blueprint)
        self.assertIn("SUPABASE_SERVICE_ROLE_KEY", blueprint)
        self.assertNotIn("disk:", blueprint)
        self.assertIn('key: OLLAMA_URL\n        value: ""', blueprint)

    def test_private_remote_upload_uses_server_key_and_non_public_object_api(self):
        response = MagicMock()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "resume.pdf"
            source.write_bytes(b"private resume bytes")
            with patch.object(config.Config, "FILE_STORAGE_BACKEND", "supabase"), \
                 patch.object(config.Config, "SUPABASE_URL", "https://example.supabase.co"), \
                 patch.object(config.Config, "SUPABASE_STORAGE_BUCKET", "placementlink-documents"), \
                 patch.object(config.Config, "SUPABASE_SERVICE_ROLE_KEY", "server-only-secret"), \
                 patch.object(file_storage.requests, "post", return_value=response) as post:
                file_storage.store_file("resume-1.pdf", source, "application/pdf")

        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://example.supabase.co/storage/v1/object/placementlink-documents/resume-1.pdf")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer server-only-secret")
        self.assertEqual(kwargs["headers"]["x-upsert"], "false")
        response.raise_for_status.assert_called_once()

    def test_remote_download_uses_private_authenticated_api(self):
        response = MagicMock(status_code=200, content=b"jd contents")
        response.headers = {"Content-Type": "application/pdf"}
        with patch.object(config.Config, "FILE_STORAGE_BACKEND", "supabase"), \
             patch.object(config.Config, "SUPABASE_URL", "https://example.supabase.co"), \
             patch.object(config.Config, "SUPABASE_STORAGE_BUCKET", "placementlink-documents"), \
             patch.object(config.Config, "SUPABASE_SERVICE_ROLE_KEY", "server-only-secret"), \
             patch.object(file_storage.requests, "get", return_value=response) as get:
            result = file_storage.retrieve_file("jd-1.pdf")

        self.assertEqual(result, (b"jd contents", "application/pdf"))
        self.assertIn("/object/authenticated/", get.call_args.args[0])

    def test_remote_file_key_rejects_path_traversal(self):
        with self.assertRaises(ValueError):
            file_storage.retrieve_file("../secret.pdf")

    def test_production_placement_ai_does_not_try_localhost_when_unconfigured(self):
        from services import placement_llm

        with patch.object(placement_llm, "OLLAMA_URL", ""), \
             patch.object(placement_llm.requests, "post") as post:
            reply = placement_llm.ask_placement_agent({}, [], "How should I prepare?")

        post.assert_not_called()
        self.assertIn("not configured", reply)

    def test_remote_uploaded_files_still_use_the_existing_authorized_route(self):
        from app import create_app

        cursor = MagicMock()
        cursor.fetchall.return_value = [{"student_user_id": 7, "mentor_user_id": None}]
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        with patch.object(config.Config, "FILE_STORAGE_BACKEND", "supabase"), \
             patch("models.profile_model.ensure_profile_request_review_columns"), \
             patch("models.profile_model.ensure_profile_resume_columns"), \
             patch("models.job_model.ensure_application_status_audit_table"), \
             patch("models.job_model.ensure_job_embedding_column"), \
             patch("models.job_model.ensure_job_description_columns"), \
             patch("database.db.get_db_connection", return_value=connection), \
             patch("services.file_storage.retrieve_file", return_value=(b"resume bytes", "application/pdf")) as retrieve:
            client = create_app().test_client()
            with client.session_transaction() as session:
                session["user_id"] = 7
                session["role"] = "student"
            response = client.get("/static/uploads/resume-1.pdf")
            body = response.get_data()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body, b"resume bytes")
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")
        retrieve.assert_called_once_with("resume-1.pdf")

    def test_student_resume_upload_stages_locally_then_sends_to_remote_storage(self):
        from routes import student_routes

        app = __import__("flask").Flask(__name__)
        app.secret_key = "unit-test-secret"
        app.register_blueprint(student_routes.student_bp)
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 99
            session["role"] = "student"

        student = {"id": 77, "user_id": 99, "register_number": "TEST077", "department": "Computer Science"}
        profile = {"skills": "Python", "projects": "", "certifications": "", "department": "Computer Science"}
        stored = {}

        def record_remote_file(filename, source_path, content_type):
            stored["filename"] = filename
            stored["bytes"] = Path(source_path).read_bytes()
            stored["content_type"] = content_type

        with tempfile.TemporaryDirectory() as directory, \
             patch.object(config.Config, "FILE_STORAGE_BACKEND", "supabase"), \
             patch.object(config.Config, "UPLOAD_FOLDER", directory), \
             patch.object(student_routes, "get_student_by_user_id", return_value=student), \
             patch.object(student_routes, "get_student_profile", return_value=profile), \
             patch.object(student_routes, "extract_resume_text", return_value="Python developer resume"), \
             patch.object(student_routes, "generate_embedding", return_value=[0.25] * 384), \
             patch.object(student_routes, "store_file", side_effect=record_remote_file) as store, \
             patch.object(student_routes, "upload_document") as save_document, \
             patch.object(student_routes, "update_resume_data") as save_resume:
            response = client.post(
                "/student/upload_document",
                data={"doc_type": "Resume", "document_file": (BytesIO(b"pdf bytes"), "resume.docx")},
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(stored["bytes"], b"pdf bytes")
        self.assertTrue(stored["filename"].startswith("TEST077_"))
        store.assert_called_once()
        save_document.assert_called_once()
        self.assertIsNotNone(save_resume.call_args.args[2])

    def test_admin_job_description_upload_uses_remote_storage_before_database_insert(self):
        from routes import admin_routes
        from flask import Flask

        app = Flask(__name__)
        app.secret_key = "unit-test-secret"
        app.register_blueprint(admin_routes.admin_bp)
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 1
            session["role"] = "admin"

        with patch.object(config.Config, "FILE_STORAGE_BACKEND", "supabase"), \
             patch.object(admin_routes, "extract_resume_text", return_value="Python backend job description"), \
             patch.object(admin_routes, "generate_embedding", return_value=[0.25] * 384), \
             patch.object(admin_routes, "store_bytes") as store, \
             patch.object(admin_routes, "create_job", return_value=51) as create_job:
            response = client.post(
                "/admin/jobs",
                data={
                    "company_id": "4", "title": "Backend Engineer", "role": "Platform team",
                    "location": "Remote", "ctc": "12 LPA", "eligibility_criteria": "CGPA 7+",
                    "required_skills": "Python, AWS", "allowed_departments": ["Computer Science"],
                    "max_backlogs": "0", "min_cgpa": "7", "application_deadline": "2099-01-01",
                    "job_description_file": (BytesIO(b"jd document bytes"), "backend.pdf"),
                },
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(store.call_args.args[1], b"jd document bytes")
        create_job.assert_called_once()


if __name__ == "__main__":
    unittest.main()
