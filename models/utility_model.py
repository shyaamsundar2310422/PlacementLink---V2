import pymysql
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db import get_db_connection

# Notifications
def create_notification(title, message, type, target_role, target_department):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "INSERT INTO notifications (title, message, type, target_role, target_department) VALUES (%s, %s, %s, %s, %s)"
            cursor.execute(sql, (title, message, type, target_role, target_department))
        connection.commit()
    finally:
        connection.close()

def get_notifications_for_student(department):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT * FROM notifications WHERE (target_role = 'student' OR target_role = 'all') AND (target_department = 'all' OR target_department LIKE %s) ORDER BY created_at DESC"
            cursor.execute(sql, (f"%{department}%",))
            return cursor.fetchall()
    finally:
        connection.close()

def get_all_notifications(limit=None):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            if limit:
                cursor.execute("SELECT * FROM notifications ORDER BY created_at DESC LIMIT %s", (limit,))
            else:
                cursor.execute("SELECT * FROM notifications ORDER BY created_at DESC")
            return cursor.fetchall()
    finally:
        connection.close()

# Documents
def upload_document(student_id, doc_type, file_path):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "INSERT INTO documents (student_id, doc_type, file_path) VALUES (%s, %s, %s)"
            cursor.execute(sql, (student_id, doc_type, file_path))
            
            if doc_type.lower() == 'resume':
                cursor.execute("UPDATE student_profiles SET resume_url = %s WHERE student_id = %s", (file_path, student_id))
        connection.commit()
    finally:
        connection.close()

def get_student_documents(student_id):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM documents WHERE student_id = %s ORDER BY uploaded_at DESC", (student_id,))
            return cursor.fetchall()
    finally:
        connection.close()

# Training Resources
def add_training_resource(title, description, resource_type, url, uploader_id):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "INSERT INTO training_resources (title, description, resource_type, url, uploaded_by) VALUES (%s, %s, %s, %s, %s)"
            cursor.execute(sql, (title, description, resource_type, url, uploader_id))
        connection.commit()
    finally:
        connection.close()

def get_all_training_resources():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM training_resources ORDER BY created_at DESC")
            return cursor.fetchall()
    finally:
        connection.close()

# Feedback
def submit_feedback(student_id, company_id, job_id, interview_rating, company_rating, difficulty, suggestions):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = """
            INSERT INTO feedback (student_id, company_id, job_id, interview_process_rating, company_experience_rating, difficulty_level, suggestions) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (student_id, company_id, job_id, interview_rating, company_rating, difficulty, suggestions))
        connection.commit()
    finally:
        connection.close()

def get_all_feedback():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = """
            SELECT f.*, s.first_name, s.department, c.name as company_name, j.title as job_title
            FROM feedback f
            JOIN students s ON f.student_id = s.id
            JOIN companies c ON f.company_id = c.id
            JOIN jobs j ON f.job_id = j.id
            ORDER BY f.created_at DESC
            """
            cursor.execute(sql)
            return cursor.fetchall()
    finally:
        connection.close()
