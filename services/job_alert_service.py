import logging

from database.db import get_db_connection

from models.job_model import (
    calculate_student_job_match
)

from utils.email_service import send_job_alert

MATCH_THRESHOLD = 40
logger = logging.getLogger(__name__)

def notify_matching_students(job):

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:

            cursor.execute("""
                SELECT
                    s.id,
                    s.first_name,
                    s.last_name,
                    u.email,

                    sp.cgpa,
                    sp.skills,
                    sp.projects,
                    sp.certifications,
                    sp.backlog_count,
                    sp.resume_text,
                    sp.resume_embedding,

                    s.department

                FROM students s
                JOIN users u
                    ON u.id = s.user_id
                LEFT JOIN student_profiles sp
                    ON sp.student_id = s.id
            """)

            students = cursor.fetchall()

        for student in students:
            if not student.get("email"):
                continue

            result = calculate_student_job_match(
                student,
                job
            )

            score = result["match_score"]
            if score < MATCH_THRESHOLD:
                continue
            try:
                
                send_job_alert(
                    recipient_email=student["email"],
                    student_name=f"{student['first_name']} {student['last_name']}",
                    company=job["company_name"],
                    role=job["title"],
                    score=score,
                    matched_skills=result["explainability"]["matched_skills"],
                    missing_skills=result["explainability"]["missing_skills"]
                )

            except Exception as e:
                logger.warning("job_alert_send_failed category=%s", type(e).__name__)

    finally:
        connection.close()
