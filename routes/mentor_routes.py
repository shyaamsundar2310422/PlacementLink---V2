from flask import Blueprint, render_template, request, redirect, flash, session
import json
from utils.decorators import role_required
from models.user_model import get_mentor_by_user_id, get_students_by_mentor, get_student_by_id_for_mentor
from models.profile_model import get_pending_requests, get_request, update_request_status, apply_profile_update

mentor_bp = Blueprint('mentor', __name__, url_prefix='/mentor')

@mentor_bp.route('/dashboard')
@role_required('mentor')
def dashboard():
    mentor = get_mentor_by_user_id(session['user_id'])
    if not mentor:
        flash("Mentor record not found.", "danger")
        return redirect('/auth/login')
    
    students = get_students_by_mentor(mentor['id'])
    requests = get_pending_requests(mentor['id'])
    return render_template('mentor/dashboard.html', mentor=mentor, student_count=len(students), request_count=len(requests))

@mentor_bp.route('/students')
@role_required('mentor')
def students():
    mentor = get_mentor_by_user_id(session['user_id'])
    students = get_students_by_mentor(mentor['id'])
    return render_template('mentor/students.html', students=students)

@mentor_bp.route('/student/<int:student_id>')
@role_required('mentor')
def student_profile(student_id):
    mentor = get_mentor_by_user_id(session['user_id'])
    if not mentor:
        flash("Mentor record not found.", "danger")
        return redirect('/auth/login')

    student = get_student_by_id_for_mentor(mentor['id'], student_id)
    if not student:
        flash("Student not found or not assigned to you.", "danger")
        return redirect('/mentor/students')

    return render_template('mentor/student_profile.html', student=student)

@mentor_bp.route('/requests')
@role_required('mentor')
def requests_view():
    mentor = get_mentor_by_user_id(session['user_id'])
    requests = get_pending_requests(mentor['id'])
    
    # Parse JSON changes for template
    for r in requests:
        if r['requested_changes']:
            r['changes_dict'] = json.loads(r['requested_changes'])
            
    return render_template('mentor/requests.html', requests=requests)

@mentor_bp.route('/request/<int:req_id>', methods=['POST'])
@role_required('mentor')
def handle_request(req_id):
    mentor = get_mentor_by_user_id(session['user_id'])
    if not mentor:
        flash("Mentor record not found.", "danger")
        return redirect('/auth/login')

    req = get_request(req_id)
    if not req:
        flash("Request not found.", "danger")
        return redirect('/mentor/requests')

    if req['mentor_id'] != mentor['id']:
        flash("Unauthorized request action.", "danger")
        return redirect('/mentor/requests')

    action = request.form.get('action')
    rejection_reason = (request.form.get('rejection_reason') or '').strip()
        
    if action == 'approve':
        changes = json.loads(req['requested_changes'])
        apply_profile_update(req['student_id'], changes)
        update_request_status(req_id, 'approved', None)
        flash("Profile update approved and applied successfully.", "success")
    elif action == 'reject':
        update_request_status(req_id, 'rejected', rejection_reason if rejection_reason else None)
        flash("Profile update request rejected.", "warning")
    else:
        flash("Invalid action.", "danger")
        
    return redirect('/mentor/requests')
