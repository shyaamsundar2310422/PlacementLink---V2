import pymysql
import json
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db import get_db_connection


def ensure_profile_request_review_columns():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SHOW COLUMNS FROM profile_update_requests LIKE 'rejection_reason'")
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE profile_update_requests ADD COLUMN rejection_reason TEXT NULL")

            cursor.execute("SHOW COLUMNS FROM profile_update_requests LIKE 'reviewed_at'")
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE profile_update_requests ADD COLUMN reviewed_at TIMESTAMP NULL")
        connection.commit()
    finally:
        connection.close()

def get_student_profile(student_id):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = """
            SELECT sp.*, s.first_name, s.last_name, s.register_number, s.department, s.mentor_id
            FROM student_profiles sp
            JOIN students s ON sp.student_id = s.id
            WHERE sp.student_id = %s
            """
            cursor.execute(sql, (student_id,))
            return cursor.fetchone()
    finally:
        connection.close()

def create_update_request(student_id, mentor_id, changes_dict):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            changes_json = json.dumps(changes_dict)
            sql = "INSERT INTO profile_update_requests (student_id, mentor_id, requested_changes) VALUES (%s, %s, %s)"
            cursor.execute(sql, (student_id, mentor_id, changes_json))
        connection.commit()
    finally:
        connection.close()

def get_pending_requests(mentor_id):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = """
            SELECT r.*, s.first_name, s.last_name, s.register_number
            FROM profile_update_requests r
            JOIN students s ON r.student_id = s.id
            WHERE r.mentor_id = %s AND r.status = 'pending'
            ORDER BY r.request_date DESC
            """
            cursor.execute(sql, (mentor_id,))
            return cursor.fetchall()
    finally:
        connection.close()

def get_request(request_id):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM profile_update_requests WHERE id = %s", (request_id,))
            return cursor.fetchone()
    finally:
        connection.close()

def update_request_status(request_id, status, rejection_reason=None):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE profile_update_requests
                SET status = %s,
                    rejection_reason = %s,
                    reviewed_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (status, rejection_reason, request_id),
            )
        connection.commit()
    finally:
        connection.close()


def get_student_profile_review_notifications(student_id, limit=10):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, status, rejection_reason, reviewed_at
                FROM profile_update_requests
                WHERE student_id = %s
                  AND status IN ('approved', 'rejected')
                ORDER BY COALESCE(reviewed_at, request_date) DESC
                LIMIT %s
                """,
                (student_id, limit),
            )
            return cursor.fetchall()
    finally:
        connection.close()

def apply_profile_update(student_id, changes_dict):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = """
            UPDATE student_profiles 
            SET cgpa = %s, skills = %s, projects = %s, certifications = %s, backlog_count = %s, contact_number = %s
            WHERE student_id = %s
            """
            cursor.execute(sql, (
                changes_dict.get('cgpa'), changes_dict.get('skills'),
                changes_dict.get('projects'), changes_dict.get('certifications'),
                changes_dict.get('backlog_count'), changes_dict.get('contact_number'),
                student_id
            ))
        connection.commit()
    finally:
        connection.close()
