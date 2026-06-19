import pymysql
import os
import sys
import random
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta

# Add current directory to path to import Config
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import Config

def seed_historical_data():
    connection = pymysql.connect(
        host=Config.DB_HOST,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        database=Config.DB_NAME,
        cursorclass=pymysql.cursors.DictCursor
    )
    
    try:
        with connection.cursor() as cursor:
            print("Cleaning up old historical data (to ensure idempotency)...")
            # We identify historical data by specific username patterns like 'hist_2021_...'
            cursor.execute("SELECT id FROM users WHERE username LIKE 'hist_%'")
            hist_user_ids = [row['id'] for row in cursor.fetchall()]
            if hist_user_ids:
                format_strings = ','.join(['%s'] * len(hist_user_ids))
                cursor.execute(f"DELETE FROM users WHERE id IN ({format_strings})", tuple(hist_user_ids))
            
            years = [2021, 2022, 2023, 2024, 2025]
            depts = ["Computer Science", "Information Technology", "Electronics", "Electrical", "Mechanical", "Civil"]
            
            # 1. Get or create a Few Companies
            cursor.execute("SELECT id, name FROM companies")
            existing_companies = cursor.fetchall()
            if not existing_companies:
                print("No companies found. Please run seed_database.py first.")
                return
            
            # 2. Generate Historical Data
            for year in years:
                print(f"Generating data for {year}...")
                
                # Targets for this year
                student_count = random.randint(15, 20)
                placement_rate = 0.6 + (year - 2021) * 0.07  # 60%, 67%, 74%, 81%, 88% approximately
                placed_count = int(student_count * placement_rate)
                avg_ctc_base = 5.5 + (year - 2021) * 0.8  # 5.5, 6.3, 7.1, 7.9, 8.7
                
                placed_students_indices = random.sample(range(student_count), placed_count)
                
                # Create Job Postings for this year
                jobs_for_year = []
                for i in range(5):
                    comp = random.choice(existing_companies)
                    ctc_val = round(avg_ctc_base + random.uniform(-1.5, 3.5), 1)
                    title = random.choice(["Software Engineer", "Systems Analyst", "Graduate Trainee", "Developer", "Data Analyst"])
                    
                    cursor.execute(
                        "INSERT INTO jobs (company_id, title, role, location, ctc, eligibility_criteria, required_skills, allowed_departments, application_deadline, created_at) "
                        "VALUES (%s, %s, %s, 'Bengaluru', %s, 'No backlogs', 'Python, SQL', 'All', %s, %s)",
                        (comp['id'], title, title, f"{ctc_val} LPA", f"{year}-06-30", f"{year}-01-15 10:00:00")
                    )
                    jobs_for_year.append(cursor.lastrowid)
                
                # Create Students and Placements
                for i in range(student_count):
                    username = f"hist_{year}_{i}"
                    email = f"{username}@college.edu"
                    pw = generate_password_hash("student123")
                    
                    # Create User
                    cursor.execute(
                        "INSERT INTO users (username, email, password_hash, role, created_at) VALUES (%s, %s, %s, 'student', %s)",
                        (username, email, pw, f"{year}-01-01 09:00:00")
                    )
                    user_id = cursor.lastrowid
                    
                    # Create Student
                    reg_num = f"HIST{year}{i:03d}"
                    dept = random.choice(depts)
                    cursor.execute(
                        "INSERT INTO students (user_id, register_number, first_name, last_name, department) VALUES (%s, %s, %s, %s, %s)",
                        (user_id, reg_num, f"Student_{year}", f"Last_{i}", dept)
                    )
                    student_id = cursor.lastrowid
                    
                    # Create Profile
                    cgpa = round(random.uniform(7.0, 9.5), 2)
                    cursor.execute(
                        "INSERT INTO student_profiles (student_id, cgpa, skills) VALUES (%s, %s, 'Historical Skills')",
                        (student_id, cgpa)
                    )
                    
                    # If this student is in the "placed" sample
                    if i in placed_students_indices:
                        job_id = random.choice(jobs_for_year)
                        # Create Application
                        cursor.execute(
                            "INSERT INTO applications (job_id, student_id, applied_at) VALUES (%s, %s, %s)",
                            (job_id, student_id, f"{year}-02-10 14:00:00")
                        )
                        app_id = cursor.lastrowid
                        
                        # Set as placed with historical timestamp
                        # We use a direct UPDATE to set updated_at because schema has ON UPDATE CURRENT_TIMESTAMP
                        cursor.execute(
                            "INSERT INTO application_status (application_id, stage, updated_at) VALUES (%s, 'Selected', %s)",
                            (app_id, f"{year}-04-15 11:30:00")
                        )
            
            connection.commit()
            print("Successfully seeded historical data for 2021-2025.")
            
    finally:
        connection.close()

if __name__ == "__main__":
    seed_historical_data()
