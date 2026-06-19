from flask import Blueprint, render_template, request, redirect, flash, session
from werkzeug.security import check_password_hash
from models.user_model import get_user_by_login, get_student_by_user_id, register_student_account

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_value = request.form['email'].strip()
        password = request.form['password']
        
        user = get_user_by_login(login_value)
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['username'] = user['username']
            
            if user['role'] == 'student':
                student = get_student_by_user_id(user['id'])
                if student:
                    session['student_id'] = student['id']
                    return redirect('/student/dashboard')
                session.clear()
                flash('Your student profile is incomplete. Please contact admin to fix your account.', 'error')
                return redirect('/auth/login')
            elif user['role'] == 'mentor':
                return redirect('/mentor/dashboard')
            elif user['role'] == 'admin':
                return redirect('/admin/dashboard')
        else:
            flash('Invalid email/username or password', 'error')
            
    return render_template('auth/login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # common fields
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        email = request.form['email']
        username = request.form['username']
        password = request.form['password']
        
        # student fields
        register_number = request.form['register_number']
        department = request.form['department']
        
        try:
            register_student_account(username, email, password, register_number, first_name, last_name, department)
            flash('Registration successful! Please login.', 'success')
            return redirect('/auth/login')
        except ValueError as e:
            flash(str(e), 'error')
        except Exception:
            flash('Error during registration. Please try again.', 'error')
            
    return render_template('auth/register.html')

@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect('/auth/login')
