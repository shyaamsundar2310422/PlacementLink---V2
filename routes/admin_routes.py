from flask import Blueprint, render_template, request, redirect, flash, session, Response
import json
import csv
import io
from utils.decorators import role_required
from models.job_model import create_company, get_all_companies, create_job, get_all_jobs, get_placement_stats, get_recent_placements, get_placement_filter_options, get_applications_by_job, get_job_by_id, update_application_stage, get_placement_trend, get_department_performance, get_company_selection_ratios, get_status_audit_history, get_placement_report_rows
from models.utility_model import create_notification, add_training_resource, get_all_notifications, get_all_training_resources, get_all_feedback

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

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
        
        create_job(company_id, title, role, location, ctc, eligibility_criteria, required_skills, allowed_departments, max_backlogs, min_cgpa, deadline)
        flash('Job posted successfully!', 'success')
        return redirect('/admin/jobs')
        
    jobs_list = get_all_jobs()
    companies_list = get_all_companies()
    return render_template('admin/jobs.html', jobs=jobs_list, companies=companies_list)

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

