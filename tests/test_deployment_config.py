import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import config
from database import db


class DeploymentConfigurationTests(unittest.TestCase):
    def test_database_url_decodes_credentials_and_reads_ssl_ca(self):
        with patch.dict(os.environ, {
            "DATABASE_URL": "mysql://deploy%40user:p%40ss@mysql.example:3307/placements?ssl_ca=%2Fetc%2Fmysql-ca.pem&ssl-mode=VERIFY_IDENTITY",
            "DB_SSL_CA": "",
        }, clear=False):
            settings = config._database_settings()

        self.assertEqual(settings, {
            "host": "mysql.example",
            "port": 3307,
            "user": "deploy@user",
            "password": "p@ss",
            "database": "placements",
            "ssl_ca": "/etc/mysql-ca.pem",
            "ssl_mode": "verify_identity",
        })

    def test_individual_database_environment_values_remain_supported(self):
        values = {
            "DATABASE_URL": "",
            "DB_HOST": "mysql.internal",
            "DB_PORT": "3308",
            "DB_USER": "placement",
            "DB_PASSWORD": "secret-value",
            "DB_NAME": "placement_db",
            "DB_SSL_CA": "/tmp/provider-ca.pem",
            "DB_SSL_MODE": "disabled",
        }
        with patch.dict(os.environ, values, clear=False):
            settings = config._database_settings()

        self.assertEqual(settings["host"], "mysql.internal")
        self.assertEqual(settings["port"], 3308)
        self.assertEqual(settings["database"], "placement_db")
        self.assertEqual(settings["ssl_ca"], "/tmp/provider-ca.pem")
        self.assertEqual(settings["ssl_mode"], "disabled")

    def test_database_connection_applies_port_timeout_and_tls_ca(self):
        with patch.object(db.Config, "DB_HOST", "mysql.example"), \
             patch.object(db.Config, "DB_PORT", 3307), \
             patch.object(db.Config, "DB_USER", "placement"), \
             patch.object(db.Config, "DB_PASSWORD", "db-secret"), \
             patch.object(db.Config, "DB_NAME", "placement_db"), \
             patch.object(db.Config, "DB_SSL_CA", "/etc/mysql-ca.pem"), \
             patch.object(db.Config, "DB_CONNECT_TIMEOUT", 13), \
             patch.object(db.pymysql, "connect") as connect:
            db.get_db_connection()

        kwargs = connect.call_args.kwargs
        self.assertEqual(kwargs["port"], 3307)
        self.assertEqual(kwargs["connect_timeout"], 13)
        self.assertEqual(kwargs["ssl"], {
            "ca": "/etc/mysql-ca.pem",
            "check_hostname": True,
            "verify_mode": "required",
        })

    def test_upload_route_serves_from_configured_persistent_directory(self):
        from app import create_app

        with tempfile.TemporaryDirectory() as upload_dir, \
             patch.object(config.Config, "UPLOAD_FOLDER", upload_dir), \
             patch("models.profile_model.ensure_profile_request_review_columns"), \
             patch("models.profile_model.ensure_profile_resume_columns"), \
             patch("models.job_model.ensure_application_status_audit_table"), \
             patch("models.job_model.ensure_job_embedding_column"), \
             patch("models.job_model.ensure_job_description_columns"), \
             patch("database.db.get_db_connection") as get_connection:
            (Path(upload_dir) / "resume.pdf").write_bytes(b"resume")
            (Path(upload_dir) / "job.pdf").write_bytes(b"job description")
            client = create_app().test_client()
            anonymous = client.get("/static/uploads/resume.pdf")
            cursor = MagicMock()
            cursor.fetchall.side_effect = [
                [{"student_user_id": 7, "mentor_user_id": None}],
                [],
                [],
            ]
            cursor.fetchone.return_value = {"id": 3}
            connection = MagicMock()
            connection.cursor.return_value.__enter__.return_value = cursor
            get_connection.return_value = connection
            with client.session_transaction() as session:
                session["user_id"] = 7
                session["role"] = "student"
            response = client.get("/static/uploads/resume.pdf")
            traversal = client.get("/static/uploads/../resume.pdf")
            job_description = client.get("/static/uploads/job.pdf")
            response_body = response.get_data()
            job_description_body = job_description.get_data()
            response.close()
            traversal.close()
            job_description.close()

        self.assertEqual(anonymous.status_code, 302)
        self.assertEqual(anonymous.location, "/auth/login")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response_body, b"resume")
        self.assertEqual(traversal.status_code, 404)
        self.assertEqual(job_description.status_code, 200)
        self.assertEqual(job_description_body, b"job description")
        self.assertEqual(get_connection.call_count, 3)

    def test_production_rejects_default_session_secret(self):
        from app import create_app

        with patch.object(config.Config, "APP_ENV", "production"), \
             patch.object(config.Config, "SECRET_KEY", "default-secret-key"):
            with self.assertRaisesRegex(RuntimeError, "unique SECRET_KEY"):
                create_app()

    def test_health_and_readiness_routes_report_service_and_database_status(self):
        from app import create_app

        connection = MagicMock()
        with tempfile.TemporaryDirectory() as upload_dir, \
             patch.object(config.Config, "UPLOAD_FOLDER", upload_dir), \
             patch("models.profile_model.ensure_profile_request_review_columns"), \
             patch("models.profile_model.ensure_profile_resume_columns"), \
             patch("models.job_model.ensure_application_status_audit_table"), \
             patch("models.job_model.ensure_job_embedding_column"), \
             patch("models.job_model.ensure_job_description_columns"), \
             patch("database.db.get_db_connection", return_value=connection):
            client = create_app().test_client()
            health = client.get("/healthz")
            readiness = client.get("/readyz")

        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json, {"status": "ok"})
        self.assertEqual(readiness.status_code, 200)
        self.assertEqual(readiness.json, {"status": "ready", "database": "ok"})
        connection.close.assert_called_once()

    def test_student_login_still_creates_session_and_redirects(self):
        from flask import Flask
        from routes import auth_routes

        app = Flask(__name__)
        app.secret_key = "unit-test-secret"
        app.register_blueprint(auth_routes.auth_bp)
        user = {"id": 7, "username": "student.test", "role": "student", "password_hash": "hash"}
        with patch.object(auth_routes, "get_user_by_login", return_value=user), \
             patch.object(auth_routes, "check_password_hash", return_value=True), \
             patch.object(auth_routes, "get_student_by_user_id", return_value={"id": 13}):
            client = app.test_client()
            response = client.post("/auth/login", data={"email": "student.test", "password": "test"})
            with client.session_transaction() as session:
                session_values = dict(session)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/student/dashboard")
        self.assertEqual(session_values["user_id"], 7)
        self.assertEqual(session_values["student_id"], 13)
        self.assertEqual(session_values["role"], "student")


if __name__ == "__main__":
    unittest.main()
