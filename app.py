from flask import Flask, render_template, session, redirect
import os

def create_app():
    app = Flask(__name__)
    app.config.from_object('config.Config')

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    from routes.auth_routes import auth_bp
    from routes.student_routes import student_bp
    from routes.mentor_routes import mentor_bp
    from routes.admin_routes import admin_bp
    from models.profile_model import ensure_profile_request_review_columns, get_student_profile_review_notifications
    from models.job_model import ensure_application_status_audit_table
    from models.user_model import get_student_by_user_id

    ensure_profile_request_review_columns()
    ensure_application_status_audit_table()
    
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
                review_notifications = get_student_profile_review_notifications(student['id'], 10)
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

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=5000)
