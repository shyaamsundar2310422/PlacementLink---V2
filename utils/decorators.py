from functools import wraps
from flask import session, redirect, flash

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please login to access this page.", "warning")
            return redirect('/auth/login')
        return f(*args, **kwargs)
    return decorated_function

def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash("Please login to access this page.", "warning")
                return redirect('/auth/login')
            if session.get('role') != role:
                flash("Unauthorized access. You do not have permission to view this page.", "danger")
                return redirect('/')
            return f(*args, **kwargs)
        return decorated_function
    return decorator
