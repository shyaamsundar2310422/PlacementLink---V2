from flask import Blueprint, render_template, request, redirect, flash, session, Response
import json
import csv
import io
import logging
import tempfile
import os
import shutil
from uuid import uuid4
from pathlib import Path
from werkzeug.utils import secure_filename
from utils.decorators import role_required
from models.job_model import create_company, get_all_companies, create_job, get_all_jobs, get_placement_stats, get_recent_placements, get_placement_filter_options, get_applications_by_job, get_job_by_id, update_job_description, update_application_stage, get_placement_trend, get_department_performance, get_company_selection_ratios, get_status_audit_history, get_placement_report_rows
from models.utility_model import create_notification, add_training_resource, get_all_notifications, get_all_training_resources, get_all_feedback
from ml.resume_parser import extract_resume_text
from ml.embedding_service import generate_embedding, embedding_to_json, json_to_embedding
from ml.semantic_matcher import build_job_text
from config import Config

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')
logger = logging.getLogger(__name__)

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

@admin_bp.route('/dashboard')
@role_required('admin')
def dashboard():
    selected_year = request.args.get('year', '').strip()
    selected_department = request.args.get('department', '').strip()

    selected_year = selected_year if selected_year.isdigit() else ''
    selected_department = selected_department or ''

    stats = get_placement_stats(year=selected_year or None, department=selected_department or None)
    recent_placements = get_recent_placements(year=selected_year or None, department=selected_department or None)
    filter_options = get_placement_filter_options()
    placement_trend = get_placement_trend(year=selected_year or None, department=selected_department or None)
    department_performance = get_department_performance(year=selected_year or None)
    company_ratios = get_company_selection_ratios(year=selected_year or None, department=selected_department or None)
    audit_history = get_status_audit_history(12)
    upcoming_drives = get_upcoming_drive_calendar()
    return render_template(
        'admin/dashboard.html',
        stats=stats,
        recent_placements=recent_placements,
        upcoming_drives=upcoming_drives,
        dept_data_json=json.dumps(stats['dept_data']),
        company_data_json=json.dumps(stats['company_data']),
        trend_data_json=json.dumps({row['month_label']: row['placed_count'] for row in placement_trend}),
        department_performance=department_performance,
        company_ratios=company_ratios,
        audit_history=audit_history,
        available_years=filter_options['years'],
        available_departments=filter_options['departments'],
        selected_year=selected_year,
        selected_department=selected_department,
    )

@admin_bp.route('/dashboard/export')
@role_required('admin')
def export_dashboard_report():
    selected_year = request.args.get('year', '').strip()
    selected_department = request.args.get('department', '').strip()
    selected_year = selected_year if selected_year.isdigit() else ''
    selected_department = selected_department or ''

    rows = get_placement_report_rows(year=selected_year or None, department=selected_department or None)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Register Number',
        'First Name',
        'Last Name',
        'Department',
        'Company',
        'Role',
        'CTC',
        'Status',
        'Applied At',
        'Last Updated',
    ])
    for row in rows:
        writer.writerow([
            row.get('register_number'),
            row.get('first_name'),
            row.get('last_name'),
            row.get('department'),
            row.get('company_name'),
            row.get('title'),
            row.get('ctc'),
            row.get('stage'),
            row.get('applied_at'),
            row.get('updated_at'),
        ])

    filename_parts = ['placement-report']
    if selected_year:
        filename_parts.append(selected_year)
    if selected_department:
        filename_parts.append(selected_department.replace(' ', '-').lower())
    filename = '-'.join(filename_parts) + '.csv'

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'},
    )

@admin_bp.route('/companies', methods=['GET', 'POST'])
@role_required('admin')
def companies():
    if request.method == 'POST':
        name = request.form.get('name')
        website_url = request.form.get('website_url')
        profile = request.form.get('profile')
        past_history = request.form.get('past_history')
        create_company(name, website_url, profile, past_history)
        flash('Company added successfully!', 'success')
        return redirect('/admin/companies')
        
    companies_list = get_all_companies()
    return render_template('admin/companies.html', companies=companies_list)

@admin_bp.route('/jobs', methods=['GET', 'POST'])
@role_required('admin')
def jobs():
    if request.method == 'POST':
        company_id = request.form.get('company_id')
        title = request.form.get('title')
        role = request.form.get('role')
        location = request.form.get('location')
        ctc = request.form.get('ctc')
        eligibility_criteria = request.form.get('eligibility_criteria')
        required_skills = request.form.get('required_skills')
        allowed_departments = ",".join(request.form.getlist('allowed_departments'))
        max_backlogs = request.form.get('max_backlogs', 0)
        min_cgpa = request.form.get('min_cgpa', 0.0)
        deadline = request.form.get('application_deadline')

        jd_file = request.files.get('job_description_file')
        if not jd_file or not jd_file.filename:
            flash('Upload a job description PDF or DOCX before publishing this job.', 'danger')
            return redirect('/admin/jobs')
        if jd_file and jd_file.filename:
            extension = Path(jd_file.filename).suffix.lower()
            if extension not in {'.pdf', '.docx'}:
                flash('Upload the job description as a PDF or DOCX file.', 'danger')
                return redirect('/admin/jobs')
            try:
                with tempfile.TemporaryDirectory(prefix='placementlink-jd-') as temp_dir:
                    jd_path = Path(temp_dir) / (secure_filename(jd_file.filename) or f'job-description{extension}')
                    jd_file.save(jd_path)
                    extracted_jd = extract_resume_text(jd_path).strip()
                    jd_bytes = jd_path.read_bytes()
                logger.info(
                    "semantic_pipeline stage=jd_extraction extension=%s chars=%d",
                    extension.lstrip('.'), len(extracted_jd),
                )
                if not extracted_jd:
                    flash('No selectable text was found in the job description. Upload a text-based PDF or DOCX.', 'danger')
                    return redirect('/admin/jobs')
                os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
                saved_filename = f"jd_{uuid4().hex}{extension}"
                saved_path = Path(Config.UPLOAD_FOLDER) / saved_filename
                saved_path.write_bytes(jd_bytes)
                jd_file_url = f"/static/uploads/{saved_filename}"
                jd_text = extracted_jd
            except Exception as error:
                flash(f'Job description could not be processed ({type(error).__name__}). No job was posted.', 'danger')
                return redirect('/admin/jobs')

        job_details = {
            'title': title,
            'role': role,
            'jd_text': jd_text,
            'required_skills': required_skills,
            'eligibility_criteria': eligibility_criteria,
            'allowed_departments': allowed_departments,
        }
        job_text = build_job_text(job_details)
        try:
            vector = generate_embedding(job_text)
            if vector is None or len(vector) != 384:
                raise ValueError('The embedding model did not return a 384-dimensional vector.')
            job_embedding = embedding_to_json(vector, source_text=job_text)
            if not json_to_embedding(job_embedding):
                raise ValueError('The generated job description embedding is invalid.')
            logger.info(
                "semantic_pipeline stage=jd_embedding_generated dimensions=%d source_chars=%d",
                len(vector), len(job_text),
            )
        except Exception as error:
            try:
                os.remove(saved_path)
            except OSError:
                pass
            flash(f'Job embedding could not be generated ({type(error).__name__}). No job was posted.', 'danger')
            return redirect('/admin/jobs')

        try:
            job_id = create_job(
                company_id, title, role, location, ctc, eligibility_criteria,
                required_skills, allowed_departments, max_backlogs, min_cgpa,
                deadline, precomputed_embedding=job_embedding,
                jd_text=jd_text, jd_file_url=jd_file_url,
            )
        except Exception as error:
            logger.exception("semantic_pipeline stage=jd_database_storage_failed")
            try:
                os.remove(saved_path)
            except OSError:
                pass
            flash(f'Job description could not be saved ({type(error).__name__}). No job was posted.', 'danger')
            return redirect('/admin/jobs')
        flash(f'Job {job_id} posted with its JD file, extracted text, and semantic embedding.', 'success')
        return redirect('/admin/jobs')
        
    jobs_list = get_all_jobs()
    companies_list = get_all_companies()
    return render_template('admin/jobs.html', jobs=jobs_list, companies=companies_list)


@admin_bp.route('/job/<int:job_id>/description', methods=['POST'])
@role_required('admin')
def replace_job_description(job_id):
    job = get_job_by_id(job_id)
    if not job:
        flash('Job posting was not found.', 'danger')
        return redirect('/admin/jobs')
    jd_file = request.files.get('job_description_file')
    if not jd_file or not jd_file.filename:
        flash('Choose a PDF or DOCX job description to upload.', 'danger')
        return redirect('/admin/jobs')
    extension = Path(jd_file.filename).suffix.lower()
    if extension not in {'.pdf', '.docx'}:
        flash('Upload the job description as a PDF or DOCX file.', 'danger')
        return redirect('/admin/jobs')

    try:
        with tempfile.TemporaryDirectory(prefix='placementlink-jd-') as temp_dir:
            temp_path = Path(temp_dir) / (secure_filename(jd_file.filename) or f'job-description{extension}')
            jd_file.save(temp_path)
            extracted_jd = extract_resume_text(temp_path).strip()
            jd_bytes = temp_path.read_bytes()
        if not extracted_jd:
            flash('No selectable text was found in the job description. Upload a text-based PDF or DOCX.', 'danger')
            return redirect('/admin/jobs')
        job_text = build_job_text({**job, 'jd_text': extracted_jd})
        vector = generate_embedding(job_text)
        if vector is None or len(vector) != 384:
            raise ValueError('The embedding model did not return a 384-dimensional vector.')
        embedding_json = embedding_to_json(vector, source_text=job_text)
        if json_to_embedding(embedding_json) is None:
            raise ValueError('The generated job description embedding is invalid.')
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        saved_filename = f"jd_{uuid4().hex}{extension}"
        saved_path = Path(Config.UPLOAD_FOLDER) / saved_filename
        saved_path.write_bytes(jd_bytes)
        file_url = f"/static/uploads/{saved_filename}"
        update_job_description(job_id, extracted_jd, file_url, embedding_json)
        logger.info(
            "semantic_pipeline stage=jd_replacement_stored job_id=%s text_chars=%d dimensions=%d",
            job_id, len(extracted_jd), len(vector),
        )
        flash(f'Job description and semantic embedding updated for job {job_id}.', 'success')
    except Exception as error:
        logger.exception("semantic_pipeline stage=jd_replacement_failed job_id=%s", job_id)
        try:
            if 'saved_path' in locals():
                os.remove(saved_path)
        except OSError:
            pass
        flash(f'Job description could not be processed ({type(error).__name__}). The existing posting was not changed.', 'danger')
    return redirect('/admin/jobs')

@admin_bp.route('/job/<int:job_id>/applications')
@role_required('admin')
def job_applications(job_id):
    job = get_job_by_id(job_id)
    applications = get_applications_by_job(job_id)
    return render_template('admin/applications.html', job=job, applications=applications)

@admin_bp.route('/application/<int:app_id>/status', methods=['POST'])
@role_required('admin')
def update_application_status_route(app_id):
    new_stage = request.form.get('new_stage')
    job_id = request.form.get('job_id')
    if new_stage == 'Placed':
        new_stage = 'Selected'
    result = update_application_stage(app_id, new_stage, changed_by=session.get('user_id'))
    if result.get("email_sent"):
        flash("Application status updated and email sent to the student.", "success")
    elif result.get("email_configured"):
        flash("Application status updated, but the email could not be sent.", "warning")
    else:
        flash("Application status updated successfully.", "success")
    return redirect(f'/admin/job/{job_id}/applications')

@admin_bp.route('/utilities', methods=['GET', 'POST'])
@role_required('admin')
def utilities():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'notification':
            title = request.form.get('title')
            message = request.form.get('message')
            ntype = request.form.get('type')
            target_role = request.form.get('target_role')
            target_dept = request.form.get('target_dept')
            create_notification(title, message, ntype, target_role, target_dept)
            flash("Notification published", "success")
            
        elif action == 'training':
            title = request.form.get('title')
            desc = request.form.get('description')
            res_type = request.form.get('resource_type')
            url = request.form.get('url')
            add_training_resource(title, desc, res_type, url, session['user_id'])
            flash("Training resource added", "success")
            
        return redirect('/admin/utilities')
        
    training_list = get_all_training_resources()
    feedback_list = get_all_feedback()
    notifications_list = get_all_notifications(12)
    
    return render_template('admin/utilities.html', training=training_list, feedback=feedback_list, notifications=notifications_list)

