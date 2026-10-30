from flask import Blueprint, render_template, request, redirect, flash, session
from werkzeug.utils import secure_filename
from markupsafe import escape
import os
import re
import logging
from uuid import uuid4
from config import Config
from utils.decorators import role_required
from models.user_model import get_student_by_user_id

from models.job_model import get_jobs_matching_profile, get_all_active_jobs_with_match, get_student_applications, apply_job
from models.utility_model import get_notifications_for_student, upload_document, get_student_documents, get_all_training_resources, submit_feedback
from ml.resume_parser import extract_resume_text
from ml.semantic_matcher import build_profile_text
from models.profile_model import (
    get_student_profile,
    create_update_request,
    update_resume_data
)
from ml.embedding_service import (
    generate_embedding,
    embedding_to_json,
    json_to_embedding,
)
from flask import jsonify, request

from services.placement_chat import get_chat_response, is_small_talk
student_bp = Blueprint('student', __name__, url_prefix='/student')
logger = logging.getLogger(__name__)

ALLOWED_DOCUMENT_EXTENSIONS = {'pdf', 'doc', 'docx', 'png', 'jpg', 'jpeg'}


def _ctc_to_number(ctc_value):
    text = (ctc_value or '').lower()
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return 0.0
    try:
        return float(match.group())
    except ValueError:
        return 0.0


def _sort_jobs(jobs_list, selected_sort):
    jobs = list(jobs_list or [])
    if selected_sort == 'deadline':
        jobs.sort(key=lambda job: (job.get('application_deadline') is None, job.get('application_deadline')))
    elif selected_sort == 'ctc':
        jobs.sort(key=lambda job: _ctc_to_number(job.get('ctc')), reverse=True)
    elif selected_sort == 'company':
        jobs.sort(key=lambda job: (job.get('company_name') or '').lower())
    else:
        jobs.sort(
            key=lambda job: (job.get('semantic_available', False), job.get('semantic_score') or -1),
            reverse=True,
        )
    return jobs


def _get_selected_sort():
    allowed = {'match', 'deadline', 'ctc', 'company'}
    selected_sort = request.args.get('sort', 'match').strip().lower()
    return selected_sort if selected_sort in allowed else 'match'


def _get_file_extension(filename):
    return filename.rsplit('.', 1)[1].lower() if '.' in filename else ''


def _is_allowed_document(filename):
    return _get_file_extension(filename) in ALLOWED_DOCUMENT_EXTENSIONS


def _build_upload_filename(student, original_filename):
    extension = _get_file_extension(original_filename)
    base_name = secure_filename(
        f"{student['register_number']}_{uuid4().hex}"
    )
    return f"{base_name}.{extension}"

def get_upcoming_drive_calendar():
    return [
        {
            "company": "Google",
            "date": "2026-04-08",
            "day": "Wed",
            "location": "Main Auditorium",
            "event": "Pre-placement talk and online assessment",
        },
        {
            "company": "Goldman Sachs",
            "date": "2026-04-15",
            "day": "Wed",
            "location": "Seminar Hall A",
            "event": "Aptitude test and technical screening",
        },
    ]

@student_bp.route('/dashboard')
@role_required('student')
def dashboard():
    student = get_student_by_user_id(session['user_id'])
    if not student:
        flash("Student record not found.", "danger")
        return redirect('/auth/login')

    profile = get_student_profile(student['id'])
    matched_jobs = get_jobs_matching_profile(student['id'])
    notifications = get_notifications_for_student(student['department'])[:5]
    upcoming_drives = get_upcoming_drive_calendar()
    return render_template('student/dashboard.html', student=student, profile=profile, open_opportunity_count=len(matched_jobs), notifications=notifications, upcoming_drives=upcoming_drives)

@student_bp.route('/profile', methods=['GET', 'POST'])
@role_required('student')
def profile():
    student = get_student_by_user_id(session['user_id'])
    profile = get_student_profile(student['id'])

    if request.method == 'POST':
        changes = {
            'cgpa': request.form.get('cgpa'),
            'skills': request.form.get('skills'),
            'projects': request.form.get('projects'),
            'certifications': request.form.get('certifications'),
            'backlog_count': request.form.get('backlog_count'),
            'contact_number': request.form.get('contact_number')
        }

        if student['mentor_id']:
            create_update_request(student['id'], student['mentor_id'], changes)
            flash('Profile update request sent to your mentor for approval.', 'success')
        else:
            flash('No mentor assigned to you yet. Please contact admin.', 'warning')

        return redirect('/student/profile')

    resume_filename = os.path.basename(profile.get('resume_url') or '') if profile else ''
    return render_template('student/profile.html', student=student, profile=profile, resume_filename=resume_filename)

@student_bp.route('/jobs')
@role_required('student')
def jobs():
    student = get_student_by_user_id(session['user_id'])
    profile = get_student_profile(student['id'])
    selected_sort = _get_selected_sort()

    profile_ready = bool(
        profile and any([
            profile.get('skills'),
            profile.get('projects'),
            profile.get('certifications'),
            profile.get('resume_text'),
        ])
    )

    jobs_list = get_jobs_matching_profile(student['id']) if profile_ready else []
    jobs_list = _sort_jobs(jobs_list, selected_sort)

    applications = get_student_applications(student['id'])
    applied_job_ids = [app['job_id'] for app in applications] if applications else []

    return render_template(
        'student/jobs.html',
        jobs=jobs_list,
        applied_job_ids=applied_job_ids,
        profile_ready=profile_ready,
        selected_sort=selected_sort,
    )


@student_bp.route('/all-jobs')
@role_required('student')
def all_jobs():
    student = get_student_by_user_id(session['user_id'])
    selected_sort = _get_selected_sort()
    jobs_list = get_all_active_jobs_with_match(student['id'])
    jobs_list = _sort_jobs(jobs_list, selected_sort)
    logger.info(
        "semantic_pipeline stage=all_jobs_template_context student_id=%s jobs=%d scored=%d",
        student['id'], len(jobs_list), sum(bool(job.get('semantic_available')) for job in jobs_list),
    )
    applications = get_student_applications(student['id'])
    applied_job_ids = [app['job_id'] for app in applications] if applications else []
    return render_template(
        'student/all_jobs.html',
        jobs=jobs_list,
        applied_job_ids=applied_job_ids,
        selected_sort=selected_sort,
    )

@student_bp.route('/jobs/apply/<int:job_id>', methods=['POST'])
@role_required('student')
def apply_for_job(job_id):
    student = get_student_by_user_id(session['user_id'])

    success, msg = apply_job(student['id'], job_id)
    if success:
        flash("Successfully applied for the job!", "success")
    else:
        flash(f"Application failed: {msg}", "danger")

    return redirect('/student/jobs')

@student_bp.route('/applications')
@role_required('student')
def applications():
    student = get_student_by_user_id(session['user_id'])
    apps = get_student_applications(student['id'])
    return render_template('student/applications.html', applications=apps)

@student_bp.route('/resources')
@role_required('student')
def resources():
    student = get_student_by_user_id(session['user_id'])
    notifications = get_notifications_for_student(student['department'])
    training = get_all_training_resources()
    documents = get_student_documents(student['id'])

    return render_template('student/resources.html', 
                           notifications=notifications, 
                           training=training, 
                           documents=documents)


@student_bp.route('/upload_document', methods=['POST'])
@role_required('student')
def upload_student_document():
    student = get_student_by_user_id(session['user_id'])
    if not student:
        flash("Student record not found.", "danger")
        return redirect('/auth/login')

    uploaded_file = request.files.get('document_file')
    doc_type = (request.form.get('doc_type') or '').strip()

    if not doc_type:
        flash("Please choose a document type.", "warning")
        return redirect('/student/resources')

    if not uploaded_file or not uploaded_file.filename:
        flash("Please select a file to upload.", "warning")
        return redirect('/student/resources')

    if doc_type.lower() == 'resume' and _get_file_extension(uploaded_file.filename) not in {'pdf', 'docx'}:
        flash("Resume upload supports PDF and DOCX files only.", "danger")
        return redirect('/student/profile' if request.referrer and request.referrer.endswith('/student/profile') else '/student/resources')

    if not _is_allowed_document(uploaded_file.filename):
        flash("Unsupported file type. Upload PDF, DOC, DOCX, PNG, JPG, or JPEG files.", "danger")
        return redirect('/student/resources')

    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    saved_filename = _build_upload_filename(student, uploaded_file.filename)
    saved_path = os.path.join(Config.UPLOAD_FOLDER, saved_filename)
    uploaded_file.save(saved_path)

    public_file_path = f"/static/uploads/{saved_filename}"
    if doc_type.lower() == 'resume':
        resume_text = ""
        resume_embedding_json = None

        if _get_file_extension(saved_filename) in {'pdf', 'docx'}:
            resume_text = extract_resume_text(saved_path)
            logger.info(
                "semantic_pipeline stage=resume_extraction student_id=%s extension=%s chars=%d",
                student['id'], _get_file_extension(saved_filename), len(resume_text.strip()),
            )

        if not resume_text.strip():
            try:
                os.remove(saved_path)
            except OSError:
                pass
            flash("The PDF/DOCX could not be read or contains no selectable text. No resume was saved.", "danger")
            return redirect('/student/profile' if request.referrer and request.referrer.endswith('/student/profile') else '/student/resources')

        upload_document(student['id'], doc_type, public_file_path)
        if resume_text:
            try:
                semantic_profile = dict(get_student_profile(student['id']) or {})
                semantic_profile['resume_text'] = resume_text
                semantic_profile.setdefault('department', student.get('department'))
                semantic_source = build_profile_text(semantic_profile).strip()
                vector = generate_embedding(semantic_source)
                if vector is None or len(vector) != 384:
                    raise ValueError("embedding model did not return a 384-dimensional vector")
                resume_embedding_json = embedding_to_json(
                    vector,
                    source_text=semantic_source,
                )
                if json_to_embedding(resume_embedding_json) is None:
                    raise ValueError("embedding model returned an invalid vector")
                logger.info(
                    "semantic_pipeline stage=resume_embedding_generated student_id=%s dimensions=%d",
                    student['id'], len(vector),
                )
            except Exception as error:
                print(f"[ResumeEmbedding] generation_failed category={type(error).__name__}")
                resume_embedding_json = None

            update_resume_data(
                student['id'],
                resume_text,
                resume_embedding_json,
            )
            logger.info(
                "semantic_pipeline stage=resume_database_storage student_id=%s text_chars=%d embedding_stored=%s",
                student['id'], len(resume_text.strip()), bool(resume_embedding_json),
            )
            if resume_embedding_json:
                flash("Resume uploaded, text extracted, and semantic embedding generated.", "success")
            else:
                flash("Resume text was extracted and saved, but semantic embedding generation failed. Semantic match scores will remain unavailable until you upload the resume again when the model is available.", "warning")
    else:
        upload_document(student['id'], doc_type, public_file_path)
        flash("Document uploaded successfully.", "success")

    return redirect('/student/profile' if request.referrer and request.referrer.endswith('/student/profile') else '/student/resources')

@student_bp.route('/feedback', methods=['GET', 'POST'])
@role_required('student')
def feedback():
    student = get_student_by_user_id(session['user_id'])
    applications = get_student_applications(student['id'])

    past_jobs = [app for app in applications if app['stage'] == 'Selected']

    if request.method == 'POST':
        app_id = int(request.form.get('application_id'))
        selected_app = next((a for a in applications if a['application_id'] == app_id), None)

        if not selected_app:
            flash("Invalid application selected for feedback", "danger")
            return redirect('/student/feedback')

        from models.job_model import get_job_by_id
        job = get_job_by_id(selected_app['job_id'])

        interview_rating = request.form.get('interview_rating')
        company_rating = request.form.get('company_rating')
        difficulty = request.form.get('difficulty')
        suggestions = request.form.get('suggestions')

        submit_feedback(student['id'], job['company_id'], job['id'], interview_rating, company_rating, difficulty, suggestions)
        flash("Thank you for submitting your feedback!", "success")
        return redirect('/student/dashboard')

    return render_template('student/feedback.html', past_jobs=past_jobs)


from services.placement_agent import (
    get_top_recommended_jobs
)




from services.placement_agent import (
    get_missing_skills_analysis
)

@student_bp.route("/missing-skills")
@role_required("student")
def missing_skills():

    student = get_student_by_user_id(
        session["user_id"]
    )

    missing_skills = get_missing_skills_analysis(
        student["id"]
    )

    return render_template(
        "student/missing_skills.html",
        missing_skills=missing_skills
    )

from services.placement_agent import get_learning_recommendations
@student_bp.route("/learn-next")
@role_required("student")
def learn_next():

    student = get_student_by_user_id(
        session["user_id"]
    )

    recommendations = get_learning_recommendations(
        student["id"]
    )

    return render_template(
        "student/learn_next.html",
        recommendations=recommendations
    )

from services.placement_agent import (
    what_if_analysis
)

@student_bp.route("/what-if")

@role_required("student")

def what_if():

    student = get_student_by_user_id(
        session["user_id"]
    )

    result = what_if_analysis(
        student["id"]
    )

    return render_template(

        "student/what_if.html",

        result=result

    )

from services.placement_agent import get_closest_companies

@student_bp.route("/closest-companies")
@role_required("student")
def closest_companies():

    student = get_student_by_user_id(
        session["user_id"]
    )

    companies = get_closest_companies(
        student["id"]
    )

    return render_template(
        "student/closest_companies.html",
        companies=companies
    )
@student_bp.route("/chat", methods=["POST"])
@role_required("student")
def placement_chat():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Send a JSON object containing a message."}), 400
    message = data.get("message")
    if not isinstance(message, str) or not message.strip():
        return jsonify({"error": "Please enter a message."}), 400
    message = message.strip()
    if len(message) > 2000:
        return jsonify({"error": "Messages must be 2,000 characters or fewer."}), 400

    small_talk = is_small_talk(message)
    if small_talk:
        context, history = {}, []
    else:
        student = get_student_by_user_id(session["user_id"])
        if not student:
            return jsonify({"error": "Student account was not found."}), 404
        context = build_student_context(student["id"])
        history = session.get("chat_history", [])
        if not isinstance(history, list):
            history = []

    response = get_chat_response(context, history, message)
    if not small_talk:
        history = history[-10:] + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": response},
        ]
        session["chat_history"] = history[-10:]
    return jsonify({"response": response})

@student_bp.route("/test-chat")
@role_required("student")
def test_chat():

    student = get_student_by_user_id(
        session["user_id"]
    )

    context = build_student_context(
        student["id"]
    )

    if "placement_context" not in session:
        # Do not persist large AI context in the client session cookie.
        pass

    response = get_chat_response(
        context,
        [],
        "What should I learn next?"
    )

    return f"<pre>{escape(response)}</pre>"

from services.context_builder import build_student_context
from services.readiness_score import calculate_readiness
from services.resume_review import (
    build_career_plan,
    build_job_gap_analysis,
    review_resume,
)
@student_bp.route("/placement-agent")
@role_required("student")
def placement_agent():

    student = get_student_by_user_id(
        session["user_id"]
    )

    top_jobs = get_top_recommended_jobs(
        student["id"]
    )
    logger.info(
        "semantic_pipeline stage=placement_template_context student_id=%s jobs=%d scored=%d",
        student['id'], len(top_jobs), sum(bool(job.get('semantic_available')) for job in top_jobs),
    )

    for job in top_jobs:
        job["why_not_me"] = build_job_gap_analysis(job)



    readiness = calculate_readiness(
        student["id"],
        recommended_jobs=top_jobs,
    )

    return render_template(
        "student/placement_agent.html",
        top_jobs=top_jobs,
        readiness=readiness
    )


@student_bp.route("/new-chat", methods=["POST"])
@role_required("student")
def new_chat():

    session["chat_history"] = []

    return jsonify({

        "success": True

    })
@student_bp.route("/resume-review")
@role_required("student")
def resume_review():

    student = get_student_by_user_id(
        session["user_id"]
    )

    if not student:
        flash("Student record not found.", "danger")
        return redirect("/auth/login")

    profile = get_student_profile(
        student["id"]
    ) or {}

    resume_text = (profile.get("resume_text") or "").strip()
    top_jobs = get_top_recommended_jobs(student["id"])
    readiness = calculate_readiness(student["id"], recommended_jobs=top_jobs)
    career_plan = build_career_plan(top_jobs, readiness)

    if not resume_text:
        return render_template(
            "student/resume_review.html",
            review=None,
            readiness=readiness,
            career_plan=career_plan,
            warning="Please upload your resume before using AI Resume Review.",
        )

    review = review_resume(
        resume_text,
        profile,
    )

    return render_template(

        "student/resume_review.html",

        review=review,
        readiness=readiness,
        career_plan=career_plan,
        warning=None,

    )
