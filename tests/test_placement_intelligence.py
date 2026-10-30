import json
from io import BytesIO
import tempfile
import unittest
from datetime import date
from pathlib import Path
from zipfile import ZipFile
from unittest.mock import Mock, patch

from flask import Flask

from ml.semantic_matcher import calculate_resume_job_score, calculate_semantic_score, build_job_text, build_profile_text
from ml.embedding_service import embedding_matches_source, embedding_to_json, json_to_embedding
from ml.resume_parser import extract_resume_text
from ml.skill_extractor import extract_skills
from models import job_model
from models import profile_model
from routes import student_routes
from routes import admin_routes
from services import context_builder, placement_agent, placement_llm, readiness_score, resume_review
from seed_demo_jobs import DEMO_JOBS, DEMO_MARKER, seed_demo_jobs
from seed_demo_job_descriptions import build_demo_description, write_docx
from tune_demo_student_skills import _append_missing_skills


class _FakeCursor:
    def __init__(self, profile, jobs):
        self.profile = profile
        self.jobs = jobs
        self.query = ""

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, _params=None):
        self.query = query

    def fetchone(self):
        return self.profile

    def fetchall(self):
        return [dict(job) for job in self.jobs]


class _FakeConnection:
    def __init__(self, profile, jobs):
        self.fake_cursor = _FakeCursor(profile, jobs)

    def cursor(self):
        return self.fake_cursor

    def close(self):
        pass


class _SeedCursor:
    def __init__(self, backend):
        self.backend = backend
        self.lastrowid = None
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=()):
        if query.startswith("SELECT id FROM companies"):
            company_id = self.backend.companies.get(params[0])
            self.result = {"id": company_id} if company_id else None
        elif query.startswith("INSERT INTO companies"):
            company_id = self.backend.next_company_id
            self.backend.next_company_id += 1
            self.backend.companies[params[0]] = company_id
            self.lastrowid = company_id
            self.result = None
        elif query.startswith("SELECT id FROM jobs"):
            company_id, title, marker_pattern = params
            self.result = next((
                {"id": job_id}
                for job_id, job in self.backend.jobs.items()
                if job[0] == company_id
                and job[1] == title
                and marker_pattern.strip("%") in job[2]
            ), None)

    def fetchone(self):
        return self.result


class _SeedBackend:
    def __init__(self):
        self.companies = {"TCS": 1}
        self.next_company_id = 2
        self.jobs = {1: (1, DEMO_JOBS[0]["title"], "Existing employer posting")}

    def connect(self):
        return self

    def cursor(self):
        return _SeedCursor(self)

    def commit(self):
        pass

    def close(self):
        pass


def _job(**overrides):
    job = {
        "id": 1,
        "company_id": 10,
        "company_name": "Example Co",
        "title": "Software Engineer",
        "role": "Backend Engineer",
        "jd_text": "Build and maintain Python backend services.",
        "jd_file_url": "/static/uploads/example-jd.pdf",
        "required_skills": "Python, Machine Learning",
        "allowed_departments": "Computer Science",
        "min_cgpa": 7,
        "max_backlogs": 0,
        "application_deadline": None,
        "job_embedding": None,
    }
    job.update(overrides)
    return job


def _profile(**overrides):
    profile = {
        "department": "Computer Science",
        "cgpa": 8.0,
        "backlog_count": 0,
        "skills": "Python, Machine Learning",
        "projects": "",
        "certifications": "",
        "resume_text": "Python backend developer resume",
        "resume_url": "/static/uploads/example-resume.pdf",
        "resume_embedding": None,
    }
    profile.update(overrides)
    return profile


class MatchingContractTests(unittest.TestCase):
    @patch("models.job_model.calculate_resume_job_score", return_value=40)
    def test_hybrid_score_keeps_70_30_and_phrase_explanations(self, _semantic):
        profile = _profile(resume_text="Python developer resume")
        profile["resume_embedding"] = embedding_to_json([1.0] * 384, source_text=build_profile_text(profile))
        job = _job()
        job["job_embedding"] = embedding_to_json([1.0] * 384, source_text=build_job_text(job))
        result = job_model._calculate_profile_job_match(profile, job)
        self.assertEqual(result["rule_score"], 70)
        self.assertEqual(result["semantic_score"], 40)
        self.assertEqual(result["match_score"], 61)
        self.assertTrue(result["is_match"])
        self.assertEqual(result["explainability"]["matched_skills"], ["Python", "Machine Learning"])
        self.assertEqual(result["explainability"]["missing_skills"], [])

    def test_profile_without_resume_text_cannot_supply_resume_semantic_score(self):
        profile = _profile(resume_text="")
        profile["resume_embedding"] = embedding_to_json(
            [1.0] + [0.0] * 383,
            source_text=build_profile_text(profile),
        )
        job = _job()
        job["job_embedding"] = embedding_to_json([1.0] + [0.0] * 383, source_text=build_job_text(job))
        result = job_model._calculate_profile_job_match(profile, job)
        self.assertFalse(result["semantic_available"])
        self.assertIsNone(result["semantic_score"])
        self.assertIn("extracted text is missing", result["semantic_diagnostic"])

    def test_approved_profile_update_generates_source_bound_vector(self):
        connection = Mock()
        cursor = Mock()
        cursor_context = Mock()
        cursor_context.__enter__ = Mock(return_value=cursor)
        cursor_context.__exit__ = Mock(return_value=False)
        connection.cursor.return_value = cursor_context
        cursor.fetchone.return_value = {
            "resume_text": "",
            "skills": "Python, AWS",
            "projects": "Cloud deployment",
            "certifications": "",
            "department": "Computer Science",
        }
        with patch.object(profile_model, "get_db_connection", return_value=connection), \
             patch.object(profile_model, "generate_embedding", return_value=[1.0] + [0.0] * 383):
            profile_model.apply_profile_update(7, {
                "cgpa": 8.0, "skills": "Python, AWS", "projects": "Cloud deployment",
                "certifications": "", "backlog_count": 0, "contact_number": "",
            })
        generated_update = next(
            call for call in cursor.execute.call_args_list
            if "SET resume_embedding=%s" in call.args[0]
        )
        self.assertTrue(embedding_matches_source(
            generated_update.args[1][0],
            build_profile_text(cursor.fetchone.return_value),
        ))

    @patch("models.job_model.calculate_resume_job_score", return_value=float("nan"))
    def test_invalid_semantic_score_is_unavailable_and_ineligible_job_stays_ineligible(self, _semantic):
        profile = _profile(resume_text="Python developer resume")
        profile["resume_embedding"] = embedding_to_json([1.0] * 384, source_text=build_profile_text(profile))
        job = _job(allowed_departments="Mechanical Engineering")
        job["job_embedding"] = embedding_to_json([1.0] * 384, source_text=build_job_text(job))
        result = job_model._calculate_profile_job_match(
            profile,
            job,
        )
        self.assertIsNone(result["semantic_score"])
        self.assertFalse(result["semantic_available"])
        self.assertFalse(result["is_match"])

    def test_recommendations_filter_by_existing_eligibility_flag(self):
        jobs = [_job(id=1, is_match=False, match_score=99), _job(id=2, is_match=True, match_score=61)]
        self.assertEqual([job["id"] for job in placement_agent.get_top_recommended_jobs(1, jobs=jobs)], [2])
        self.assertEqual(len(jobs), 2)  # caller retains all open opportunities

    @patch("models.job_model._calculate_profile_job_match")
    @patch("models.job_model.get_db_connection")
    def test_model_contract_separates_all_open_jobs_from_eligible_jobs(self, get_connection, calculate):
        profile = _profile()
        jobs = [_job(id=1, application_deadline="2099-01-01"), _job(id=2, application_deadline="2099-01-01")]
        connection = _FakeConnection(profile, jobs)
        get_connection.return_value = connection
        calculate.side_effect = lambda _profile, job: {"is_match": job["id"] == 1, "match_score": 70 if job["id"] == 1 else 55}

        all_jobs = job_model.get_all_active_jobs_with_match(1)
        self.assertEqual([job["id"] for job in all_jobs], [1, 2])
        self.assertIn("application_deadline >= CURDATE()", connection.fake_cursor.query)
        self.assertNotIn("application_deadline IS NULL", connection.fake_cursor.query)

        get_connection.return_value = _FakeConnection(profile, jobs)
        matched_jobs = job_model.get_jobs_matching_profile(1)
        self.assertEqual([job["id"] for job in matched_jobs], [1])

    @patch("models.job_model.get_db_connection")
    def test_model_contract_handles_empty_mysql_fetchall_tuple(self, get_connection):
        connection = _FakeConnection(_profile(), [])
        connection.fake_cursor.fetchall = lambda: ()
        get_connection.return_value = connection

        self.assertEqual(job_model.get_all_active_jobs_with_match(1), [])

    def test_missing_embeddings_keep_rule_score_and_mark_semantic_unavailable(self):
        result = job_model._calculate_profile_job_match(_profile(), _job())
        self.assertIsNone(result["semantic_score"])
        self.assertFalse(result["semantic_available"])
        self.assertEqual(result["match_score"], result["rule_score"])
        self.assertIn("embedding", result["semantic_diagnostic"].lower())

    def test_missing_jd_document_reports_document_stage(self):
        profile = _profile(resume_text="Python developer resume")
        profile["resume_embedding"] = embedding_to_json(
            [1.0] + [0.0] * 383, source_text=build_profile_text(profile)
        )
        job = _job(jd_text="", jd_file_url=None)
        job["job_embedding"] = embedding_to_json(
            [1.0] + [0.0] * 383, source_text=build_job_text(job)
        )
        result = job_model._calculate_profile_job_match(profile, job)
        self.assertFalse(result["semantic_available"])
        self.assertIsNone(result["semantic_score"])
        self.assertIn("Job description file is missing", result["semantic_diagnostic"])

    def test_cosine_similarity_maps_to_0_100_and_relevant_text_scores_higher(self):
        def vector_for(text):
            value = text.lower()
            if "machine learning" in value or "python" in value:
                return [1.0, 1.0] + [0.0] * 382
            if "opposite" in value:
                return [-1.0, -1.0] + [0.0] * 382
            return [0.0, 0.0, 1.0] + [0.0] * 381

        with patch("ml.semantic_matcher.generate_embedding", side_effect=vector_for):
            relevant = calculate_semantic_score("Python machine learning projects", "Python machine learning engineer")
            unrelated = calculate_semantic_score("Python machine learning projects", "Sales role")
            opposite = calculate_semantic_score("Python machine learning projects", "Opposite")
        self.assertEqual(relevant, 100.0)
        self.assertEqual(unrelated, 50.0)
        self.assertEqual(opposite, 0.0)
        self.assertGreater(relevant, unrelated)

    @patch("models.job_model.generate_embedding", side_effect=AssertionError("page requests must not generate embeddings"))
    @patch("models.job_model.get_db_connection")
    def test_page_request_does_not_generate_missing_embeddings(self, get_connection, _generate):
        profile = _profile(resume_text="Current student resume")
        profile["resume_embedding"] = embedding_to_json(
            [1.0] + [0.0] * 383,
            source_text=build_profile_text(profile),
        )
        job = _job(id=2, job_embedding=None, application_deadline="2099-01-01")
        get_connection.return_value = _FakeConnection(profile, [job])
        jobs = job_model.get_all_active_jobs_with_match(7)
        result = jobs[0]
        self.assertFalse(result["semantic_available"])
        self.assertEqual(result["match_score"], result["rule_score"])
        self.assertIn("JD embedding", result["semantic_diagnostic"])

    def test_zero_norm_vectors_are_not_reported_as_available(self):
        profile = _profile(resume_text="student resume")
        profile["resume_embedding"] = embedding_to_json([0.0] * 384, source_text=build_profile_text(profile))
        job = _job()
        job["job_embedding"] = embedding_to_json([1.0] * 384, source_text=build_job_text(job))
        result = job_model._calculate_profile_job_match(
            profile,
            job,
        )
        self.assertFalse(result["semantic_available"])

    def test_corrupt_or_stale_embedding_is_unavailable_without_a_score(self):
        profile = _profile(resume_text="current resume")
        profile["resume_embedding"] = embedding_to_json(
            [1.0] + [0.0] * 383,
            source_text="old profile text",
        )
        job = _job()
        job["job_embedding"] = embedding_to_json([1.0] + [0.0] * 383, source_text=build_job_text(job))
        result = job_model._calculate_profile_job_match(profile, job)
        self.assertFalse(result["semantic_available"])
        self.assertIsNone(result["semantic_score"])
        self.assertIn("Profile/resume embedding", result["semantic_diagnostic"])

    def test_legacy_resume_vector_logs_exact_validation_failure(self):
        profile = _profile(resume_text="Real extracted resume text", student_id=7)
        profile["resume_embedding"] = json.dumps([1.0] + [0.0] * 383)
        job = _job(id=29)
        job["job_embedding"] = embedding_to_json([1.0] + [0.0] * 383, source_text=build_job_text(job))
        with self.assertLogs("models.job_model", level="WARNING") as captured:
            result = job_model._calculate_profile_job_match(profile, job)
        self.assertFalse(result["semantic_available"])
        self.assertIsNone(result["semantic_score"])
        self.assertIn("stage=stored_vector_validation", captured.output[0])
        self.assertIn("resume_vector_dims=384", captured.output[0])
        self.assertIn("resume_model=legacy_or_missing", captured.output[0])
        self.assertIn("resume_source_match=False", captured.output[0])

    def test_default_job_order_uses_semantic_score_when_available(self):
        jobs = [
            {"id": 1, "semantic_available": False, "semantic_score": None, "match_score": 100},
            {"id": 2, "semantic_available": True, "semantic_score": 78, "match_score": 20},
            {"id": 3, "semantic_available": True, "semantic_score": 92, "match_score": 15},
        ]
        ordered = student_routes._sort_jobs(jobs, "match")
        self.assertEqual([job["id"] for job in ordered], [3, 2, 1])

    def test_embedding_json_records_model_and_source_for_stale_detection(self):
        vector = [1.0] + [0.0] * 383
        stored = embedding_to_json(vector, source_text="current resume text")
        self.assertEqual(json_to_embedding(stored), vector)
        self.assertTrue(embedding_matches_source(stored, "current resume text"))
        self.assertFalse(embedding_matches_source(stored, "updated resume text"))

    def test_embedding_validation_handles_bad_and_mismatched_vectors(self):
        self.assertIsNone(calculate_resume_job_score({"resume_embedding": "not json"}, _job()))
        self.assertEqual(calculate_resume_job_score(
            {"resume_embedding": json.dumps([1] * 384)},
            _job(job_embedding=json.dumps([1] * 383)),
        ), None)
        self.assertEqual(calculate_resume_job_score(
            {"resume_embedding": json.dumps([float("nan")] * 384)},
            _job(job_embedding=json.dumps([1] * 384)),
        ), None)


class PlacementFeatureTests(unittest.TestCase):
    def test_missing_skills_preserve_display_case_and_empty_jobs(self):
        jobs = [{"explainability": {"missing_skills": ["Machine Learning"]}}]
        self.assertEqual(placement_agent.get_missing_skills_analysis(1, jobs=jobs), [("Machine Learning", 1)])
        self.assertEqual(placement_agent.get_learning_recommendations(1, jobs=[]), [])

    def test_what_if_counts_only_threshold_crossings(self):
        jobs = [
            {"match_score": 50, "rule_score": 50, "semantic_score": 50,
             "explainability": {"matched_skills": [], "missing_skills": ["Machine Learning"]}},
            {"match_score": 61, "rule_score": 61, "semantic_score": 61,
             "explainability": {"matched_skills": [], "missing_skills": ["Machine Learning"]}},
            {"match_score": 50, "rule_score": 50, "semantic_score": 50,
             "match_gates": {"academic_gate": True, "department_gate": False},
             "explainability": {"matched_skills": [], "missing_skills": ["Machine Learning"]}},
        ]
        result = placement_agent.what_if_analysis(1, jobs=jobs)
        self.assertEqual(result["affected_jobs"], 3)
        self.assertEqual(result["unlocks"], 1)

    @patch("services.readiness_score.get_student_profile", return_value=None)
    def test_readiness_handles_missing_profile(self, _profile_lookup):
        result = readiness_score.calculate_readiness(1, recommended_jobs=[])
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["status"], "Needs Improvement")

    def test_closest_companies_aggregates_and_keeps_best_job(self):
        jobs = [
            _job(id=1, title="Junior", match_score=44, is_match=False),
            _job(id=2, title="Senior", match_score=72, is_match=True),
        ]
        companies = placement_agent.get_closest_companies(1, jobs=jobs)
        self.assertEqual(len(companies), 1)
        self.assertEqual(companies[0]["job_count"], 2)
        self.assertEqual(companies[0]["title"], "Senior")

    @patch("services.context_builder.get_all_active_jobs_with_match")
    def test_context_reuses_one_job_payload_and_keeps_expected_keys(self, fetch_jobs):
        context_builder.clear_student_context(55123)
        fetch_jobs.return_value = [_job(is_match=True, match_score=75)]
        context = context_builder.build_student_context(55123)
        fetch_jobs.assert_called_once_with(55123)
        self.assertIn("top_jobs", context)
        self.assertEqual(context["top_jobs"][0]["company"], "Example Co")
        context_builder.clear_student_context(55123)


class AIAndRouteTests(unittest.TestCase):
    def test_demo_skill_additions_are_additive_and_idempotent(self):
        original = "Python, SQL"
        first = _append_missing_skills(original, ["SQL", "Git", "React"])
        second = _append_missing_skills(first, ["SQL", "Git", "React"])
        self.assertEqual(first, "Python, SQL, Git, React")
        self.assertEqual(second, first)

    def test_demo_jd_is_role_specific_and_explicitly_labeled(self):
        analyst = build_demo_description({
            "company_name": "Example Analytics", "title": "Data Analyst — Demo",
            "role": "Prepare datasets, build dashboards, and explain findings.",
            "required_skills": "SQL, Python, Power BI", "eligibility_criteria": "CGPA 6.5+",
            "allowed_departments": "All", "location": "Chennai", "ctc": "8 LPA",
            "application_deadline": "2027-01-01",
        })
        self.assertIn("DEMO JOB DESCRIPTION", analyst)
        self.assertIn("dashboards", analyst.lower())
        self.assertIn("SQL, Python, Power BI", analyst)
        with tempfile.TemporaryDirectory() as directory:
            doc_path = Path(directory) / "demo.docx"
            write_docx(doc_path, analyst)
            extracted = extract_resume_text(doc_path).strip()
            self.assertIn("DEMO JOB DESCRIPTION", extracted)
            self.assertIn("Power BI", extracted)

    def test_admin_jd_docx_upload_extracts_and_saves_source_bound_embedding(self):
        from ml.semantic_matcher import build_job_text

        app = Flask(__name__)
        app.secret_key = "unit-test-secret"
        app.register_blueprint(admin_routes.admin_bp)
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 1
            session["role"] = "admin"

        with tempfile.TemporaryDirectory() as directory, \
             patch.object(admin_routes.Config, "UPLOAD_FOLDER", directory), \
             patch.object(admin_routes, "extract_resume_text", return_value="Build distributed Python services."), \
             patch.object(admin_routes, "generate_embedding", return_value=[0.25] * 384), \
             patch.object(admin_routes, "create_job") as create_job:
            response = client.post(
                "/admin/jobs",
                data={
                    "company_id": "4", "title": "Backend Engineer", "role": "Platform team",
                    "location": "Remote", "ctc": "12 LPA", "eligibility_criteria": "CGPA 7+",
                    "required_skills": "Python, AWS", "allowed_departments": ["Computer Science"],
                    "max_backlogs": "0", "min_cgpa": "7", "application_deadline": "2099-01-01",
                    "job_description_file": (BytesIO(b"docx bytes"), "backend.docx"),
                },
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 302)
        create_job.assert_called_once()
        args, kwargs = create_job.call_args
        saved = dict(title=args[1], role=args[2], jd_text=kwargs["jd_text"], required_skills=args[6],
                     eligibility_criteria=args[5], allowed_departments=args[7])
        self.assertEqual(saved["jd_text"], "Build distributed Python services.")
        self.assertTrue(kwargs["jd_file_url"].startswith("/static/uploads/jd_"))
        self.assertTrue(embedding_matches_source(kwargs["precomputed_embedding"], build_job_text(saved)))

    def test_existing_job_jd_replacement_preserves_record_fields_and_updates_embedding(self):
        job = _job(id=25, jd_text=None, jd_file_url=None)
        app = Flask(__name__)
        app.secret_key = "unit-test-secret"
        app.register_blueprint(admin_routes.admin_bp)
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 1
            session["role"] = "admin"
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(admin_routes.Config, "UPLOAD_FOLDER", directory), \
             patch.object(admin_routes, "get_job_by_id", return_value=job), \
             patch.object(admin_routes, "extract_resume_text", return_value="Python services and AWS deployment."), \
             patch.object(admin_routes, "generate_embedding", return_value=[0.5] + [0.0] * 383), \
             patch.object(admin_routes, "update_job_description") as update_description:
            response = client.post(
                "/admin/job/25/description",
                data={"job_description_file": (BytesIO(b"docx bytes"), "replacement.docx")},
                content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 302)
        update_description.assert_called_once()
        args = update_description.call_args.args
        self.assertEqual(args[0], 25)
        self.assertEqual(args[1], "Python services and AWS deployment.")
        self.assertTrue(embedding_matches_source(args[3], build_job_text({**job, "jd_text": args[1]})))

    def test_admin_job_requires_a_job_description_file(self):
        app = Flask(__name__)
        app.secret_key = "unit-test-secret"
        app.register_blueprint(admin_routes.admin_bp)
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 1
            session["role"] = "admin"
        response = client.post("/admin/jobs", data={"title": "Backend Engineer"})
        self.assertEqual(response.status_code, 302)

    def test_admin_rejects_unsupported_job_description_file_type(self):
        app = Flask(__name__)
        app.secret_key = "unit-test-secret"
        app.register_blueprint(admin_routes.admin_bp)
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 1
            session["role"] = "admin"
        with patch.object(admin_routes, "create_job") as create_job:
            response = client.post(
                "/admin/jobs",
                data={"title": "Backend Engineer", "job_description_file": (BytesIO(b"bad"), "jd.txt")},
                content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 302)
        create_job.assert_not_called()

    def test_admin_job_embedding_failure_does_not_create_job_or_keep_jd_file(self):
        app = Flask(__name__)
        app.secret_key = "unit-test-secret"
        app.register_blueprint(admin_routes.admin_bp)
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 1
            session["role"] = "admin"
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(admin_routes.Config, "UPLOAD_FOLDER", directory), \
             patch.object(admin_routes, "extract_resume_text", return_value="Python backend job description"), \
             patch.object(admin_routes, "generate_embedding", side_effect=RuntimeError("model offline")), \
             patch.object(admin_routes, "create_job") as create_job:
            response = client.post(
                "/admin/jobs",
                data={
                    "company_id": "4", "title": "Backend Engineer", "role": "Platform team",
                    "allowed_departments": ["All"], "application_deadline": "2099-01-01",
                    "job_description_file": (BytesIO(b"docx bytes"), "backend.docx"),
                },
                content_type="multipart/form-data",
            )
            self.assertEqual(list(Path(directory).iterdir()), [])
        self.assertEqual(response.status_code, 302)
        create_job.assert_not_called()

    def test_resume_text_is_saved_when_embedding_generation_fails(self):
        app = Flask(__name__)
        app.secret_key = "unit-test-secret"
        app.register_blueprint(student_routes.student_bp)
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 99
            session["role"] = "student"
        xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
               '<w:body><w:p><w:r><w:t>Python backend developer resume</w:t></w:r></w:p></w:body></w:document>')
        document = BytesIO()
        with ZipFile(document, "w") as archive:
            archive.writestr("word/document.xml", xml)
        document.seek(0)
        student = {"id": 77, "user_id": 99, "register_number": "TEST077", "department": "Computer Science"}
        profile = {"skills": "Python", "projects": "", "certifications": "", "department": "Computer Science"}
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(student_routes.Config, "UPLOAD_FOLDER", directory), \
             patch.object(student_routes, "get_student_by_user_id", return_value=student), \
             patch.object(student_routes, "get_student_profile", return_value=profile), \
             patch.object(student_routes, "upload_document"), \
             patch.object(student_routes, "update_resume_data") as update_resume, \
             patch.object(student_routes, "generate_embedding", side_effect=RuntimeError("model offline")):
            response = client.post(
                "/student/upload_document",
                data={"doc_type": "Resume", "document_file": (document, "resume.docx")},
                content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 302)
        args = update_resume.call_args.args
        self.assertIn("Python backend developer resume", args[1])
        self.assertIsNone(args[2])

    def test_invalid_resume_document_is_rejected_without_saving(self):
        app = Flask(__name__)
        app.secret_key = "unit-test-secret"
        app.register_blueprint(student_routes.student_bp)
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 99
            session["role"] = "student"
        student = {"id": 77, "user_id": 99, "register_number": "TEST077", "department": "Computer Science"}
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(student_routes.Config, "UPLOAD_FOLDER", directory), \
             patch.object(student_routes, "get_student_by_user_id", return_value=student), \
             patch.object(student_routes, "upload_document") as save_document:
            response = client.post(
                "/student/upload_document",
                data={"doc_type": "Resume", "document_file": (BytesIO(b"not a pdf"), "resume.pdf")},
                content_type="multipart/form-data",
            )
            save_document.assert_not_called()
            self.assertEqual(list(Path(directory).iterdir()), [])
        self.assertEqual(response.status_code, 302)

    def test_resume_upload_to_review_fallback_flow(self):
        app = Flask(
            __name__,
            template_folder=str(Path(__file__).resolve().parents[1] / "templates"),
            static_folder=str(Path(__file__).resolve().parents[1] / "static"),
        )
        app.secret_key = "unit-test-secret"
        app.context_processor(lambda: {"review_notification_count": 0, "review_notifications": []})
        app.register_blueprint(student_routes.student_bp)
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 99
            session["role"] = "student"

        xml = (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>Summary: Python developer. Projects: Flask placement portal. '
            'Education: Computer Science.</w:t></w:r></w:p></w:body></w:document>'
        )
        document = BytesIO()
        with ZipFile(document, "w") as archive:
            archive.writestr("word/document.xml", xml)
        document.seek(0)
        persisted = {}
        student = {"id": 77, "user_id": 99, "register_number": "TEST077", "department": "Computer Science"}
        student_profile = {
            "skills": "Python, Flask",
            "projects": "Flask placement portal",
            "certifications": "",
            "department": "Computer Science",
        }

        def save_resume(student_id, resume_text, embedding_json):
            persisted.update(
                student_id=student_id,
                resume_text=resume_text,
                embedding_json=embedding_json,
            )

        with tempfile.TemporaryDirectory() as directory, \
             patch.object(student_routes.Config, "UPLOAD_FOLDER", directory), \
             patch.object(student_routes, "get_student_by_user_id", return_value=student), \
             patch.object(student_routes, "get_student_profile", return_value=student_profile), \
             patch.object(student_routes, "upload_document"), \
             patch.object(student_routes, "update_resume_data", side_effect=save_resume), \
             patch.object(student_routes, "generate_embedding", return_value=[1.0] + [0.0] * 383):
            upload_response = client.post(
                "/student/upload_document",
                data={"doc_type": "resume", "document_file": (document, "synthetic.docx")},
                content_type="multipart/form-data",
            )

        self.assertEqual(upload_response.status_code, 302)
        self.assertIn("Python developer", persisted["resume_text"])
        self.assertEqual(persisted["student_id"], student["id"])
        self.assertTrue(embedding_matches_source(
            persisted["embedding_json"],
            build_profile_text({**student_profile, "resume_text": persisted["resume_text"]}),
        ))
        self.assertEqual(len(json_to_embedding(persisted["embedding_json"])), 384)

        profile = {
            "resume_text": persisted["resume_text"],
            "skills": "Python, Flask",
            "projects": "Flask placement portal",
            "certifications": "",
            "cgpa": 8.0,
        }
        with patch.object(student_routes, "get_student_by_user_id", return_value=student), \
             patch.object(student_routes, "get_student_profile", return_value=profile), \
             patch.object(student_routes, "get_top_recommended_jobs", return_value=[]), \
             patch.object(student_routes, "calculate_readiness", return_value={"score": 60, "status": "Ready", "breakdown": {}}), \
             patch("services.resume_review.ask_placement_agent", side_effect=__import__("requests").exceptions.Timeout):
            review_response = client.get("/student/resume-review")

        self.assertEqual(review_response.status_code, 200)
        self.assertIn(b"Local heuristic analysis shown", review_response.data)
        self.assertIn(b"Skills", review_response.data)
        self.assertIn(b"Projects", review_response.data)
        self.assertIn(b"Experience", review_response.data)

    @patch("services.placement_llm.requests.post")
    def test_chat_timeout_returns_controlled_message(self, post):
        post.side_effect = __import__("requests").exceptions.Timeout()
        self.assertIn("taking longer", placement_llm.ask_placement_agent({}, [], "Question"))

    @patch("services.placement_llm.requests.post")
    def test_chat_connection_failure_returns_controlled_message(self, post):
        post.side_effect = __import__("requests").exceptions.ConnectionError()
        self.assertIn("unavailable", placement_llm.ask_placement_agent({}, [], "Question"))

    @patch("services.placement_llm.requests.post", side_effect=RuntimeError("private service detail"))
    def test_unexpected_chat_service_error_is_not_exposed(self, _post):
        response = placement_llm.ask_placement_agent({}, [], "Question")
        self.assertIn("could not complete", response)
        self.assertNotIn("private service detail", response)

    @patch("services.placement_llm.requests.post")
    def test_small_talk_omits_context_and_history_from_prompt(self, post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"response": "Hello."}
        post.return_value = response
        placement_llm.ask_placement_agent(
            {"top_jobs": [{"company": "PrivateCo"}]},
            [{"role": "user", "content": "private prior question"}],
            "hello",
        )
        prompt = post.call_args.kwargs["json"]["prompt"]
        self.assertNotIn("PrivateCo", prompt)
        self.assertNotIn("private prior question", prompt)

    @patch("services.placement_llm.requests.post")
    def test_resume_review_context_is_kept_in_compact_prompt(self, post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"response": "{}"}
        post.return_value = response
        placement_llm.ask_placement_agent(
            {"resume_text": "Specific resume evidence", "profile": {"skills": "Python"}},
            [],
            "Review this resume",
        )
        prompt = post.call_args.kwargs["json"]["prompt"]
        self.assertIn("Specific resume evidence", prompt)
        self.assertIn("Python", prompt)

    @patch("services.placement_llm.requests.post")
    def test_substantive_followup_keeps_recent_history(self, post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"response": "Use the earlier project example."}
        post.return_value = response
        placement_llm.ask_placement_agent(
            {},
            [{"role": "user", "content": "My project used a graph database."}],
            "How should I describe it?",
        )
        self.assertIn("My project used a graph database", post.call_args.kwargs["json"]["prompt"])

    @patch("services.resume_review.ask_placement_agent", return_value="not valid JSON")
    def test_invalid_resume_review_output_is_labeled_local_fallback(self, _ask):
        resume_review.resume_review_cache.clear()
        result = resume_review.review_resume("Resume with Python experience", _profile())
        self.assertEqual(result["analysis_source"], "local_fallback")
        self.assertIn("heuristic", result["service_warning"])
        self.assertTrue(result["skills_feedback"])
        self.assertTrue(result["experience"])
        self.assertTrue(result["projects_feedback"])
        resume_review.resume_review_cache.clear()

    def test_demo_job_seed_is_repeatable_and_does_not_overwrite_existing_job(self):
        backend = _SeedBackend()
        created_jobs = []

        def create_job(*args, **_kwargs):
            job_id = len(created_jobs) + 100
            created_jobs.append(args)
            backend.jobs[job_id] = (args[0], args[1], args[5])
            return job_id

        first_count = seed_demo_jobs(
            connection_factory=backend.connect,
            job_creator=create_job,
            today=date(2026, 10, 29),
            embedding_factory=lambda jobs: [None] * len(jobs),
        )
        second_count = seed_demo_jobs(
            connection_factory=backend.connect,
            job_creator=create_job,
            today=date(2026, 10, 29),
            embedding_factory=lambda jobs: [None] * len(jobs),
        )

        self.assertEqual(first_count, len(DEMO_JOBS))
        self.assertEqual(second_count, 0)
        self.assertEqual(len(created_jobs), len(DEMO_JOBS))
        self.assertEqual(backend.jobs[1][2], "Existing employer posting")
        self.assertTrue(all(DEMO_MARKER in args[5] for args in created_jobs))

    def test_docx_resume_text_extraction(self):
        xml = (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>Python and Machine Learning</w:t></w:r></w:p></w:body>'
            '</w:document>'
        )
        with tempfile.TemporaryDirectory() as directory:
            docx_path = Path(directory) / "resume.docx"
            with ZipFile(docx_path, "w") as document:
                document.writestr("word/document.xml", xml)
            self.assertEqual(extract_resume_text(docx_path), "Python and Machine Learning")

    def test_pdf_resume_text_extraction(self):
        stream = b"BT /F1 12 Tf 50 750 Td (Synthetic resume: Python SQL Flask.) Tj ET"
        objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        ]
        pdf = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for index, item in enumerate(objects, 1):
            offsets.append(len(pdf))
            pdf.extend(f"{index} 0 obj\n".encode() + item + b"\nendobj\n")
        xref_offset = len(pdf)
        pdf.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
        for offset in offsets[1:]:
            pdf.extend(f"{offset:010d} 00000 n \n".encode())
        pdf.extend(
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n".encode()
        )

        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "resume.pdf"
            pdf_path.write_bytes(pdf)
            self.assertIn("Synthetic resume: Python SQL Flask", extract_resume_text(pdf_path))

    def test_resume_skill_extraction_keeps_known_multiword_skills(self):
        self.assertIn("Machine Learning", extract_skills("Built a Machine Learning model with Python"))

    def test_student_route_requires_login_and_renders_dashboard(self):
        app = Flask(
            __name__,
            template_folder=str(Path(__file__).resolve().parents[1] / "templates"),
            static_folder=str(Path(__file__).resolve().parents[1] / "static"),
        )
        app.secret_key = "unit-test-secret"
        app.context_processor(lambda: {"review_notification_count": 0, "review_notifications": []})
        app.register_blueprint(student_routes.student_bp)
        client = app.test_client()
        self.assertEqual(client.get("/student/placement-agent").status_code, 302)
        with client.session_transaction() as session:
            session["user_id"] = 1
            session["role"] = "mentor"
        self.assertEqual(client.get("/student/placement-agent").status_code, 302)
        with client.session_transaction() as session:
            session["role"] = "student"
        with patch.object(student_routes, "get_student_by_user_id", return_value={"id": 1}), \
             patch.object(student_routes, "get_top_recommended_jobs", return_value=[]), \
             patch.object(student_routes, "calculate_readiness", return_value={"score": 0, "status": "Needs Improvement", "breakdown": {}}):
            response = client.get("/student/placement-agent")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Placement Match Dashboard", response.data)


if __name__ == "__main__":
    unittest.main()
