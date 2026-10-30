from flask import Flask, render_template, session, redirect, jsonify, send_from_directory, abort, Response
import os
from extensions import mail
from werkzeug.middleware.proxy_fix import ProxyFix

def create_app():
    app = Flask(__name__)
    app.config.from_object('config.Config')
    if app.config.get('APP_ENV') == 'production' and app.config.get('SECRET_KEY') == 'default-secret-key':
        raise RuntimeError('Set a unique SECRET_KEY before starting PlacementLink in production.')
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # Flask-Mail uses the same environment-based values as utils.email_utils.
    app.config['MAIL_SERVER'] = app.config.get('SMTP_HOST')
    app.config['MAIL_PORT'] = app.config.get('SMTP_PORT', 587)
    app.config['MAIL_USE_TLS'] = app.config.get('SMTP_USE_TLS', True)
    app.config['MAIL_USERNAME'] = app.config.get('SMTP_USER')
    app.config['MAIL_PASSWORD'] = app.config.get('SMTP_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = app.config.get('MAIL_FROM')

    mail.init_app(app)

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    from routes.auth_routes import auth_bp
    from routes.student_routes import student_bp
    from routes.mentor_routes import mentor_bp
    from routes.admin_routes import admin_bp
    from models.profile_model import (
        ensure_profile_request_review_columns,
        ensure_profile_resume_columns,
        get_student_profile_review_notifications
    )
    from models.job_model import (
        ensure_application_status_audit_table,
        ensure_job_embedding_column,
        ensure_job_description_columns,
    )
    from models.user_model import get_student_by_user_id

    ensure_profile_request_review_columns()
    ensure_profile_resume_columns()
    ensure_application_status_audit_table()
    ensure_job_embedding_column()
    ensure_job_description_columns()

    app.register_blueprint(auth_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(mentor_bp)
    app.register_blueprint(admin_bp)

    @app.context_processor
    def inject_student_review_notifications():
        review_notifications = []
        review_notification_count = 0

        if session.get('user_id') and session.get('role') == 'student':
            student = get_student_by_user_id(session['user_id'])
            if student:
                review_notifications = get_student_profile_review_notifications(
                    student['id'], 10
                )
                review_notification_count = len(review_notifications)

        return {
            'review_notifications': review_notifications,
            'review_notification_count': review_notification_count,
        }

    @app.route('/')
    def index():
        if 'user_id' in session:
            role = session.get('role')

            if role == 'student':
                return redirect('/student/dashboard')
            elif role == 'mentor':
                return redirect('/mentor/dashboard')
            elif role == 'admin':
                return redirect('/admin/dashboard')

        return redirect('/auth/login')

    @app.get('/healthz')
    def health_check():
        return jsonify(status='ok'), 200

    @app.get('/readyz')
    def readiness_check():
        from database.db import get_db_connection
        connection = None
        try:
            connection = get_db_connection()
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
                cursor.fetchone()
            return jsonify(status='ready', database='ok'), 200
        except Exception:
            app.logger.exception('readiness_check_failed')
            return jsonify(status='not_ready', database='unavailable'), 503
        finally:
            if connection is not None:
                connection.close()

    @app.get('/static/uploads/<path:filename>')
    def uploaded_file(filename):
        user_id = session.get('user_id')
        role = session.get('role')
        if not user_id or role not in {'student', 'mentor', 'admin'}:
            return redirect('/auth/login')

        if role != 'admin':
            from database.db import get_db_connection
            file_url = f'/static/uploads/{filename}'
            connection = get_db_connection()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT s.user_id AS student_user_id, m.user_id AS mentor_user_id
                        FROM documents d
                        JOIN students s ON d.student_id = s.id
                        LEFT JOIN mentors m ON s.mentor_id = m.id
                        WHERE d.file_path = %s
                        UNION
                        SELECT s.user_id AS student_user_id, m.user_id AS mentor_user_id
                        FROM student_profiles p
                        JOIN students s ON p.student_id = s.id
                        LEFT JOIN mentors m ON s.mentor_id = m.id
                        WHERE p.resume_url = %s
                        """,
                        (file_url, file_url),
                    )
                    student_documents = cursor.fetchall()
                    is_job_description = False
                    if not student_documents:
                        cursor.execute('SELECT id FROM jobs WHERE jd_file_url = %s', (file_url,))
                        is_job_description = bool(cursor.fetchone())
            finally:
                connection.close()

            if is_job_description:
                pass
            elif role == 'student' and any(
                int(document['student_user_id']) == int(user_id)
                for document in (student_documents or [])
            ):
                pass
            elif role == 'mentor' and any(
                document.get('mentor_user_id') is not None
                and int(document['mentor_user_id']) == int(user_id)
                for document in (student_documents or [])
            ):
                pass
            else:
                abort(404)
        from services.file_storage import FileStorageError, retrieve_file, uses_remote_storage
        if uses_remote_storage():
            try:
                stored_file = retrieve_file(filename)
            except ValueError:
                abort(404)
            except FileStorageError:
                app.logger.exception('uploaded_file_storage_unavailable')
                abort(503)
            if stored_file is None:
                abort(404)
            contents, content_type = stored_file
            response = Response(contents, mimetype=content_type)
            response.headers['Cache-Control'] = 'private, no-store'
            return response
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(
        debug=app.config.get('APP_ENV') != 'production',
        use_reloader=False
    )
