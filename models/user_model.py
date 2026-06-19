import pymysql
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db import get_db_connection
from werkzeug.security import generate_password_hash, check_password_hash

def get_user_by_email(email):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
            return cursor.fetchone()
    finally:
        connection.close()

def get_user_by_login(login_value):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM users WHERE email = %s OR username = %s",
                (login_value, login_value),
            )
            return cursor.fetchone()
    finally:
        connection.close()

def get_user_by_id(user_id):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            return cursor.fetchone()
    finally:
        connection.close()

def create_user(username, email, password, role):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            password_hash = generate_password_hash(password)
            sql = "INSERT INTO users (username, email, password_hash, role) VALUES (%s, %s, %s, %s)"
            cursor.execute(sql, (username, email, password_hash, role))
            user_id = cursor.lastrowid
        connection.commit()
        return user_id
    finally:
        connection.close()

def create_student(user_id, register_number, first_name, last_name, department):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "INSERT INTO students (user_id, register_number, first_name, last_name, department) VALUES (%s, %s, %s, %s, %s)"
            cursor.execute(sql, (user_id, register_number, first_name, last_name, department))
            student_id = cursor.lastrowid
            
            # create empty profile
            profile_sql = "INSERT INTO student_profiles (student_id) VALUES (%s)"
            cursor.execute(profile_sql, (student_id,))
        connection.commit()
    finally:
        connection.close()

def register_student_account(username, email, password, register_number, first_name, last_name, department):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cursor.fetchone():
                raise ValueError("Email already registered.")

            cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            if cursor.fetchone():
                raise ValueError("Username already taken.")

            cursor.execute("SELECT id FROM students WHERE register_number = %s", (register_number,))
            if cursor.fetchone():
                raise ValueError("Register number already exists.")

            password_hash = generate_password_hash(password)
            cursor.execute(
                "INSERT INTO users (username, email, password_hash, role) VALUES (%s, %s, %s, 'student')",
                (username, email, password_hash),
            )
            user_id = cursor.lastrowid

            cursor.execute(
                "SELECT id FROM mentors ORDER BY id ASC LIMIT 1"
            )
            mentor_row = cursor.fetchone()
            mentor_id = mentor_row["id"] if mentor_row else None

            cursor.execute(
                "INSERT INTO students (user_id, register_number, first_name, last_name, department, mentor_id) VALUES (%s, %s, %s, %s, %s, %s)",
                (user_id, register_number, first_name, last_name, department, mentor_id),
            )
            student_id = cursor.lastrowid

            cursor.execute("INSERT INTO student_profiles (student_id) VALUES (%s)", (student_id,))

        connection.commit()
        return user_id
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

def get_student_by_user_id(user_id):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM students WHERE user_id = %s", (user_id,))
            return cursor.fetchone()
    finally:
        connection.close()

def get_mentor_by_user_id(user_id):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM mentors WHERE user_id = %s", (user_id,))
            return cursor.fetchone()
    finally:
        connection.close()

def get_students_by_mentor(mentor_id):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = """
            SELECT s.*, p.cgpa, p.backlog_count 
            FROM students s 
            LEFT JOIN student_profiles p ON s.id = p.student_id 
            WHERE s.mentor_id = %s
            """
            cursor.execute(sql, (mentor_id,))
            return cursor.fetchall()
    finally:
        connection.close()

def get_student_by_id_for_mentor(mentor_id, student_id):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = """
            SELECT s.*, p.cgpa, p.skills, p.projects, p.certifications, p.resume_url, p.backlog_count, p.contact_number
            FROM students s
            LEFT JOIN student_profiles p ON s.id = p.student_id
            WHERE s.mentor_id = %s AND s.id = %s
            """
            cursor.execute(sql, (mentor_id, student_id))
            return cursor.fetchone()
    finally:
        connection.close()
