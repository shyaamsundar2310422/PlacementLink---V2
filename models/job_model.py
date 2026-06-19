import pymysql
import sys
import os
import re

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db import get_db_connection
from utils.email_utils import send_application_status_email

_STOPWORDS = {
    "and", "or", "the", "a", "an", "to", "for", "of", "in", "on", "with", "by",
    "is", "are", "as", "at", "from", "be", "strong", "good", "skills", "skill",
    "knowledge", "understanding", "experience", "ability", "basic", "advanced"
}

_MATCH_WEIGHTS = {
    "skills": 35,
    "role": 15,
    "academics": 20,
    "department": 15,
    "projects": 10,
    "certifications": 5,
}

_MATCH_THRESHOLD = 60


def _normalize_text(value):
    text = (value or "").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokenize(value):
    normalized = _normalize_text(value)
    return [token for token in normalized.split() if len(token) > 1 and token not in _STOPWORDS]


def _extract_required_skill_phrases(required_skills):
    if not required_skills:
        return []
    chunks = [chunk.strip() for chunk in re.split(r"[,;/]", required_skills) if chunk.strip()]
    return [_normalize_text(chunk) for chunk in chunks if _normalize_text(chunk)]


def _to_float(value, default=0.0):
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


def _parse_ctc_amount(ctc_value):
    text = (ctc_value or "").lower()
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return 0.0
    return _to_float(match.group())


def _to_int(value, default=0):
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def _split_departments(value):
    if not value:
        return []
    return [_normalize_text(item) for item in re.split(r"[,;/]", value) if item.strip()]


def _coverage(candidate_tokens, target_tokens):
    if not target_tokens:
        return 0
    return len(set(candidate_tokens).intersection(set(target_tokens))) / len(set(target_tokens))


def _score_academics(profile, job):
    student_cgpa = _to_float(profile.get("cgpa"))
    min_cgpa = _to_float(job.get("min_cgpa"))
    student_backlogs = _to_int(profile.get("backlog_count"))
    max_backlogs = _to_int(job.get("max_backlogs"))

    cgpa_score = 1 if min_cgpa <= 0 else min(student_cgpa / min_cgpa, 1)
    backlog_score = 1 if student_backlogs <= max_backlogs else 0
    return (cgpa_score * 0.65) + (backlog_score * 0.35)


def _score_department(profile, job):
    allowed_departments = _split_departments(job.get("allowed_departments"))
    if not allowed_departments:
        return 1

    student_department = _normalize_text(profile.get("department"))
    if "all" in allowed_departments:
        return 1
    return 1 if student_department in allowed_departments else 0


def _build_profile_tokens(profile):
    skills_tokens = set(_tokenize(profile.get("skills")))
    project_tokens = set(_tokenize(profile.get("projects")))
    certification_tokens = set(_tokenize(profile.get("certifications")))
    department_tokens = set(_tokenize(profile.get("department")))
    all_tokens = skills_tokens | project_tokens | certification_tokens | department_tokens
    return {
        "skills": skills_tokens,
        "projects": project_tokens,
        "certifications": certification_tokens,
        "department": department_tokens,
        "all": all_tokens,
    }


def _calculate_profile_job_match(profile, job):
    profile_tokens = _build_profile_tokens(profile)
    required_skill_phrases = _extract_required_skill_phrases(job.get("required_skills"))
    required_skill_tokens = set(_tokenize(" ".join(required_skill_phrases)))

    jd_text = " ".join([
        job.get("required_skills") or "",
        job.get("eligibility_criteria") or "",
        job.get("title") or "",
        job.get("role") or "",
    ])
    jd_tokens = set(_tokenize(jd_text))
    role_tokens = set(_tokenize(" ".join([job.get("title") or "", job.get("role") or ""])))

    skills_score = _coverage(profile_tokens["all"], required_skill_tokens)
    role_score = _coverage(profile_tokens["all"], role_tokens)
    academics_score = _score_academics(profile, job)
    department_score = _score_department(profile, job)
    project_score = _coverage(profile_tokens["projects"], jd_tokens)
    certification_score = _coverage(profile_tokens["certifications"], required_skill_tokens)

    weighted_score = (
        skills_score * _MATCH_WEIGHTS["skills"]
        + role_score * _MATCH_WEIGHTS["role"]
        + academics_score * _MATCH_WEIGHTS["academics"]
        + department_score * _MATCH_WEIGHTS["department"]
        + project_score * _MATCH_WEIGHTS["projects"]
        + certification_score * _MATCH_WEIGHTS["certifications"]
    )

    required_skill_gate = not required_skill_tokens or skills_score >= 0.35
    academic_gate = academics_score >= 0.65
    department_gate = department_score == 1
    is_match = weighted_score >= _MATCH_THRESHOLD and required_skill_gate and academic_gate and department_gate

    return {
        "is_match": is_match,
        "match_score": round(weighted_score),
        "match_breakdown": {
            "skills": round(skills_score * 100),
            "role": round(role_score * 100),
            "academics": round(academics_score * 100),
            "department": round(department_score * 100),
            "projects": round(project_score * 100),
            "certifications": round(certification_score * 100),
        },
        "match_reasons": {
            "skills": "Strong enough required-skill overlap" if required_skill_gate else "Add more required skills to your profile",
            "academics": "Meets CGPA/backlog expectations" if academic_gate else "Does not meet CGPA/backlog expectations",
            "department": "Department is eligible" if department_gate else "Department is not eligible for this role",
        },
    }


def ensure_application_status_audit_table():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS application_status_audit (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    application_id INT NOT NULL,
                    changed_by INT,
                    previous_stage VARCHAR(50),
                    new_stage VARCHAR(50) NOT NULL,
                    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE CASCADE,
                    FOREIGN KEY (changed_by) REFERENCES users(id) ON DELETE SET NULL
                )
                """
            )
        connection.commit()
    finally:
        connection.close()


def get_jobs_matching_profile(student_id):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT s.department, sp.cgpa, sp.skills, sp.projects, sp.certifications, sp.backlog_count
                FROM students s
                LEFT JOIN student_profiles sp ON sp.student_id = s.id
                WHERE s.id = %s
                """,
                (student_id,),
            )
            student_profile = cursor.fetchone()

            if not student_profile:
                return []

            profile_tokens = _build_profile_tokens(student_profile)
            if not profile_tokens["all"]:
                return []

            cursor.execute(
                """
                SELECT j.*, c.name as company_name, c.website_url
                FROM jobs j
                JOIN companies c ON j.company_id = c.id
                WHERE j.application_deadline >= CURDATE()
                ORDER BY j.created_at DESC
                """
            )
            jobs = cursor.fetchall()

        matched_jobs = []
        for job in jobs:
            match_result = _calculate_profile_job_match(student_profile, job)
            if match_result["is_match"]:
                job.update(match_result)
                matched_jobs.append(job)

        matched_jobs.sort(key=lambda item: item.get("match_score", 0), reverse=True)
        return matched_jobs
    finally:
        connection.close()


def get_all_active_jobs_with_match(student_id):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT s.department, sp.cgpa, sp.skills, sp.projects, sp.certifications, sp.backlog_count
                FROM students s
                LEFT JOIN student_profiles sp ON sp.student_id = s.id
                WHERE s.id = %s
                """,
                (student_id,),
            )
            student_profile = cursor.fetchone()

            cursor.execute(
                """
                SELECT j.*, c.name as company_name, c.website_url
                FROM jobs j
                JOIN companies c ON j.company_id = c.id
                WHERE j.application_deadline >= CURDATE()
                ORDER BY j.created_at DESC
                """
            )
            jobs = cursor.fetchall()

        for job in jobs:
            match_result = _calculate_profile_job_match(student_profile or {}, job)
            job.update(match_result)

        jobs.sort(key=lambda item: item.get("match_score", 0), reverse=True)
        return jobs
    finally:
        connection.close()

def create_company(name, website_url, profile, past_history):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "INSERT INTO companies (name, website_url, profile, past_history) VALUES (%s, %s, %s, %s)"
            cursor.execute(sql, (name, website_url, profile, past_history))
        connection.commit()
    finally:
        connection.close()

def get_all_companies():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM companies ORDER BY name ASC")
            return cursor.fetchall()
    finally:
        connection.close()

def create_job(company_id, title, role, location, ctc, eligibility_criteria, required_skills, allowed_departments, max_backlogs, min_cgpa, application_deadline):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = """
            INSERT INTO jobs (company_id, title, role, location, ctc, eligibility_criteria, required_skills, allowed_departments, max_backlogs, min_cgpa, application_deadline) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (company_id, title, role, location, ctc, eligibility_criteria, required_skills, allowed_departments, max_backlogs, min_cgpa, application_deadline))
        connection.commit()
    finally:
        connection.close()

def get_all_jobs():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = """
            SELECT j.*, c.name as company_name, c.website_url
            FROM jobs j
            JOIN companies c ON j.company_id = c.id
            ORDER BY j.created_at DESC
            """
            cursor.execute(sql)
            return cursor.fetchall()
    finally:
        connection.close()

def get_active_jobs():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = """
            SELECT j.*, c.name as company_name, c.website_url
            FROM jobs j
            JOIN companies c ON j.company_id = c.id
            WHERE j.application_deadline >= CURDATE()
            ORDER BY j.created_at DESC
            """
            cursor.execute(sql)
            return cursor.fetchall()
    finally:
        connection.close()

def get_eligible_jobs(student_cgpa, student_backlogs, student_department):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = """
            SELECT j.*, c.name as company_name, c.website_url
            FROM jobs j
            JOIN companies c ON j.company_id = c.id
            WHERE j.min_cgpa <= %s 
              AND j.max_backlogs >= %s
              AND (j.allowed_departments LIKE %s OR j.allowed_departments LIKE '%%All%%')
              AND j.application_deadline >= CURDATE()
            ORDER BY j.created_at DESC
            """
            dept_pattern = f"%{student_department}%"
            cursor.execute(sql, (student_cgpa, student_backlogs, dept_pattern))
            return cursor.fetchall()
    finally:
        connection.close()

def apply_job(student_id, job_id):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            matched_jobs = get_jobs_matching_profile(student_id)
            matched_job_ids = {job["id"] for job in matched_jobs}
            if job_id not in matched_job_ids:
                return False, "Your profile does not strictly match this job description."

            cursor.execute("SELECT id FROM applications WHERE student_id = %s AND job_id = %s", (student_id, job_id))
            if cursor.fetchone():
                return False, "Already applied to this job."
                
            sql = "INSERT INTO applications (student_id, job_id) VALUES (%s, %s)"
            cursor.execute(sql, (student_id, job_id))
            application_id = cursor.lastrowid
            
            status_sql = "INSERT INTO application_status (application_id, stage) VALUES (%s, 'Applied')"
            cursor.execute(status_sql, (application_id,))
            
        connection.commit()
        return True, "Successfully applied"
    except pymysql.MySQLError as e:
        return False, str(e)
    finally:
        connection.close()

def get_student_applications(student_id):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = """
            SELECT a.id as application_id, a.job_id, a.applied_at, j.title, j.ctc, c.name as company_name, s.stage
            FROM applications a
            JOIN jobs j ON a.job_id = j.id
            JOIN companies c ON j.company_id = c.id
            JOIN application_status s ON s.application_id = a.id
            WHERE a.student_id = %s
            ORDER BY a.applied_at DESC
            """
            cursor.execute(sql, (student_id,))
            return cursor.fetchall()
    finally:
        connection.close()

def get_applications_by_job(job_id):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = """
            SELECT a.id as application_id, a.applied_at, st.first_name, st.last_name, st.register_number, st.department, p.cgpa, p.skills, p.resume_url, ast.stage
            FROM applications a
            JOIN students st ON a.student_id = st.id
            JOIN student_profiles p ON st.id = p.student_id
            JOIN application_status ast ON ast.application_id = a.id
            WHERE a.job_id = %s
            ORDER BY a.applied_at ASC
            """
            cursor.execute(sql, (job_id,))
            return cursor.fetchall()
    finally:
        connection.close()

def update_application_stage(application_id, stage, changed_by=None):
    connection = get_db_connection()
    email_sent = False
    email_configured = False
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT stage FROM application_status WHERE application_id = %s", (application_id,))
            existing = cursor.fetchone()
            previous_stage = existing['stage'] if existing else None

            sql = "UPDATE application_status SET stage = %s WHERE application_id = %s"
            cursor.execute(sql, (stage, application_id))

            if previous_stage != stage:
                cursor.execute(
                    """
                    INSERT INTO application_status_audit (application_id, changed_by, previous_stage, new_stage)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (application_id, changed_by, previous_stage, stage),
                )

            cursor.execute(
                """
                SELECT u.email, st.first_name, st.last_name, st.department,
                       c.name AS company_name, j.title
                FROM applications a
                JOIN students st ON a.student_id = st.id
                JOIN users u ON st.user_id = u.id
                JOIN jobs j ON a.job_id = j.id
                JOIN companies c ON j.company_id = c.id
                WHERE a.id = %s
                """,
                (application_id,)
            )
            application_details = cursor.fetchone()

            if application_details and previous_stage != stage:
                student_name = f"{application_details['first_name']} {application_details['last_name']}"
                from utils.email_utils import is_email_configured
                email_configured = is_email_configured()
                email_sent = send_application_status_email(
                    application_details["email"],
                    student_name,
                    application_details["company_name"],
                    application_details["title"],
                    stage,
                )

            if stage == 'Selected' and previous_stage != 'Selected':
                placement = application_details
                if placement:
                    from models.utility_model import create_notification
                    title = f"Placement Update: {placement['first_name']} placed at {placement['company_name']}"
                    message = (
                        f"{placement['first_name']} {placement['last_name']} has been selected for "
                        f"{placement['title']} at {placement['company_name']}."
                    )
                    create_notification(title, message, 'placement', 'all', placement['department'])
        connection.commit()
        return {
            "updated": True,
            "email_sent": email_sent,
            "email_configured": email_configured,
        }
    finally:
        connection.close()

def get_job_by_id(job_id):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = """
            SELECT j.*, c.name as company_name, c.website_url
            FROM jobs j
            JOIN companies c ON j.company_id = c.id
            WHERE j.id = %s
            """
            cursor.execute(sql, (job_id,))
            return cursor.fetchone()
    finally:
        connection.close()

def get_placement_stats(year=None, department=None):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            filters = ["ast.stage = 'Selected'"]
            params = []
            if year:
                filters.append("YEAR(ast.updated_at) = %s")
                params.append(int(year))
            if department:
                filters.append("st.department = %s")
                params.append(department)

            sql = f"""
            SELECT a.student_id, j.ctc, st.department, c.name as company_name
            FROM applications a
            JOIN jobs j ON a.job_id = j.id
            JOIN companies c ON j.company_id = c.id
            JOIN students st ON a.student_id = st.id
            JOIN application_status ast ON ast.application_id = a.id
            WHERE {' AND '.join(filters)}
            """
            cursor.execute(sql, tuple(params))
            placements = cursor.fetchall()

            if department:
                cursor.execute("SELECT count(*) as total FROM students WHERE department = %s", (department,))
            else:
                cursor.execute("SELECT count(*) as total FROM students")
            total_students_row = cursor.fetchone()
            total_students = total_students_row['total'] if total_students_row and total_students_row['total'] > 0 else 1
            
            stats = {
                'total_placed': len(placements),
                'placement_percentage': int((len(placements) / total_students) * 100),
                'highest_ctc': 0,
                'average_ctc': 0,
                'dept_data': {},
                'company_data': {}
            }
            
            total_ctc = 0
            valid_ctc_count = 0
            
            for p in placements:
                dept = p['department']
                stats['dept_data'][dept] = stats['dept_data'].get(dept, 0) + 1
                
                company = p['company_name']
                stats['company_data'][company] = stats['company_data'].get(company, 0) + 1
                
                try:
                    num = _parse_ctc_amount(p['ctc'])
                    if num <= 0:
                        continue
                    if num > stats['highest_ctc']:
                        stats['highest_ctc'] = num
                    total_ctc += num
                    valid_ctc_count += 1
                except:
                    pass
                    
            if valid_ctc_count > 0:
                stats['average_ctc'] = round(total_ctc / valid_ctc_count, 2)

            return stats
    finally:
        connection.close()

def get_recent_placements(limit=8, year=None, department=None):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            filters = ["ast.stage = 'Selected'"]
            params = []
            if year:
                filters.append("YEAR(ast.updated_at) = %s")
                params.append(int(year))
            if department:
                filters.append("st.department = %s")
                params.append(department)

            sql = f"""
            SELECT st.first_name, st.last_name, st.register_number, st.department,
                   c.name AS company_name, j.title, j.location, j.ctc, ast.updated_at
            FROM applications a
            JOIN students st ON a.student_id = st.id
            JOIN jobs j ON a.job_id = j.id
            JOIN companies c ON j.company_id = c.id
            JOIN application_status ast ON ast.application_id = a.id
            WHERE {' AND '.join(filters)}
            ORDER BY ast.updated_at DESC
            LIMIT %s
            """
            params.append(limit)
            cursor.execute(sql, tuple(params))
            return cursor.fetchall()
    finally:
        connection.close()


def get_placement_trend(year=None, department=None):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            filters = ["ast.stage = 'Selected'"]
            params = []
            if year:
                filters.append("YEAR(ast.updated_at) = %s")
                params.append(int(year))
            if department:
                filters.append("st.department = %s")
                params.append(department)

            sql = f"""
            SELECT DATE_FORMAT(ast.updated_at, '%%Y-%%m') AS month_label, COUNT(*) AS placed_count
            FROM applications a
            JOIN students st ON a.student_id = st.id
            JOIN application_status ast ON ast.application_id = a.id
            WHERE {' AND '.join(filters)}
            GROUP BY month_label
            ORDER BY month_label ASC
            """
            cursor.execute(sql, tuple(params))
            return cursor.fetchall()
    finally:
        connection.close()


def get_department_performance(year=None):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            selected_join_filter = ""
            selected_params = []
            if year:
                selected_join_filter = "AND YEAR(ast.updated_at) = %s"
                selected_params.append(int(year))

            sql = f"""
            SELECT st.department,
                   COUNT(DISTINCT st.id) AS total_students,
                   COUNT(DISTINCT CASE WHEN ast.stage = 'Selected' {selected_join_filter} THEN st.id END) AS placed_students,
                   MAX(CASE WHEN ast.stage = 'Selected' {selected_join_filter} THEN j.ctc END) AS sample_highest_ctc
            FROM students st
            LEFT JOIN applications a ON a.student_id = st.id
            LEFT JOIN jobs j ON j.id = a.job_id
            LEFT JOIN application_status ast ON ast.application_id = a.id
            GROUP BY st.department
            ORDER BY st.department ASC
            """
            cursor.execute(sql, tuple(selected_params * 2))
            rows = cursor.fetchall()

        for row in rows:
            total = row["total_students"] or 0
            placed = row["placed_students"] or 0
            row["placement_percentage"] = round((placed / total) * 100) if total else 0
            row["highest_ctc"] = _parse_ctc_amount(row.get("sample_highest_ctc"))
        return rows
    finally:
        connection.close()


def get_company_selection_ratios(year=None, department=None):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            filters = []
            params = []
            if year:
                filters.append("YEAR(a.applied_at) = %s")
                params.append(int(year))
            if department:
                filters.append("st.department = %s")
                params.append(department)

            where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
            sql = f"""
            SELECT c.name AS company_name,
                   COUNT(a.id) AS total_applications,
                   SUM(CASE WHEN ast.stage = 'Selected' THEN 1 ELSE 0 END) AS selected_count
            FROM applications a
            JOIN students st ON a.student_id = st.id
            JOIN jobs j ON a.job_id = j.id
            JOIN companies c ON j.company_id = c.id
            JOIN application_status ast ON ast.application_id = a.id
            {where_clause}
            GROUP BY c.id, c.name
            ORDER BY selected_count DESC, total_applications DESC, c.name ASC
            LIMIT 10
            """
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()

        for row in rows:
            total = row["total_applications"] or 0
            selected = row["selected_count"] or 0
            row["selection_ratio"] = round((selected / total) * 100) if total else 0
        return rows
    finally:
        connection.close()


def get_status_audit_history(limit=12, job_id=None):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            filters = []
            params = []
            if job_id:
                filters.append("a.job_id = %s")
                params.append(job_id)
            where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
            params.append(limit)

            sql = f"""
            SELECT audit.changed_at, audit.previous_stage, audit.new_stage,
                   st.first_name, st.last_name, st.register_number,
                   c.name AS company_name, j.title,
                   u.username AS changed_by_username
            FROM application_status_audit audit
            JOIN applications a ON audit.application_id = a.id
            JOIN students st ON a.student_id = st.id
            JOIN jobs j ON a.job_id = j.id
            JOIN companies c ON j.company_id = c.id
            LEFT JOIN users u ON audit.changed_by = u.id
            {where_clause}
            ORDER BY audit.changed_at DESC
            LIMIT %s
            """
            cursor.execute(sql, tuple(params))
            return cursor.fetchall()
    finally:
        connection.close()


def get_placement_report_rows(year=None, department=None):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            filters = []
            params = []
            if year:
                filters.append("YEAR(a.applied_at) = %s")
                params.append(int(year))
            if department:
                filters.append("st.department = %s")
                params.append(department)
            where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

            sql = f"""
            SELECT st.register_number, st.first_name, st.last_name, st.department,
                   c.name AS company_name, j.title, j.ctc, ast.stage,
                   a.applied_at, ast.updated_at
            FROM applications a
            JOIN students st ON a.student_id = st.id
            JOIN jobs j ON a.job_id = j.id
            JOIN companies c ON j.company_id = c.id
            JOIN application_status ast ON ast.application_id = a.id
            {where_clause}
            ORDER BY a.applied_at DESC
            """
            cursor.execute(sql, tuple(params))
            return cursor.fetchall()
    finally:
        connection.close()


def get_placement_filter_options():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT YEAR(ast.updated_at) AS placement_year
                FROM application_status ast
                WHERE ast.stage = 'Selected'
                ORDER BY placement_year DESC
                """
            )
            year_rows = cursor.fetchall()
            years = [row['placement_year'] for row in year_rows if row.get('placement_year')]

            cursor.execute(
                """
                SELECT DISTINCT department
                FROM students
                WHERE department IS NOT NULL AND department <> ''
                ORDER BY department ASC
                """
            )
            dept_rows = cursor.fetchall()
            departments = [row['department'] for row in dept_rows]

            return {
                'years': years,
                'departments': departments,
            }
    finally:
        connection.close()
