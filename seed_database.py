import pymysql
import os
import sys
from werkzeug.security import generate_password_hash
from datetime import date, timedelta

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import Config

def seed_db():
    connection = pymysql.connect(
        host=Config.DB_HOST,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        database=Config.DB_NAME
    )
    
    try:
        with connection.cursor() as cursor:
            # Admin
            cursor.execute("SELECT id FROM users WHERE email='admin@college.edu'")
            if not cursor.fetchone():
                admin_pw = generate_password_hash("admin123")
                cursor.execute("INSERT INTO users (username, email, password_hash, role) VALUES ('admin', 'admin@college.edu', %s, 'admin')", (admin_pw,))
                admin_user_id = cursor.lastrowid
                cursor.execute("INSERT INTO admins (user_id, admin_id, first_name, last_name) VALUES (%s, 'A001', 'System', 'Admin')", (admin_user_id,))
                print("Admin created: admin@college.edu / admin123")
                
            # Mentor
            cursor.execute("SELECT id FROM users WHERE email='mentor@college.edu'")
            if not cursor.fetchone():
                mentor_pw = generate_password_hash("mentor123")
                cursor.execute("INSERT INTO users (username, email, password_hash, role) VALUES ('mentor', 'mentor@college.edu', %s, 'mentor')", (mentor_pw,))
                mentor_user_id = cursor.lastrowid
                cursor.execute("INSERT INTO mentors (user_id, faculty_id, first_name, last_name, department) VALUES (%s, 'F001', 'Alan', 'Turing', 'Computer Science')", (mentor_user_id,))
                print("Mentor created: mentor@college.edu / mentor123")

            # Link existing students without mentors to F001 for demo purposes
            cursor.execute("SELECT id FROM mentors WHERE faculty_id='F001'")
            mentor_row = cursor.fetchone()
            if mentor_row:
                mentor_id = mentor_row[0]
                cursor.execute("UPDATE students SET mentor_id = %s WHERE mentor_id IS NULL", (mentor_id,))

            students = [
                ("Aarav", "Sharma", "aarav.sharma", "aarav@college.edu", "student123", "CSE001", "Computer Science", 8.9, 0, "Python, Java, DSA, SQL, Flask", "Placement portal, expense tracker", "AWS Cloud Practitioner", "9876500011"),
                ("Diya", "Patel", "diya.patel", "diya@college.edu", "student123", "IT002", "Information Technology", 8.4, 0, "React, Node.js, MongoDB, REST APIs", "E-commerce UI, event booking app", "Meta Front-End Developer", "9876500012"),
                ("Rahul", "Verma", "rahul.verma", "rahul@college.edu", "student123", "ECE003", "Electronics", 7.8, 1, "Python, Embedded C, SQL, Power BI", "IoT monitoring system, attendance tracker", "Google Data Analytics", "9876500013"),
                ("Sneha", "Iyer", "sneha.iyer", "sneha@college.edu", "student123", "EEE004", "Electrical", 7.5, 1, "Java, OOP, DBMS, Excel, Tableau", "Power usage dashboard, grievance portal", "Oracle Java Foundations", "9876500014"),
                ("Karthik", "Rao", "karthik.rao", "karthik@college.edu", "student123", "ME005", "Mechanical", 7.1, 0, "Python, AutoCAD, Excel, Problem Solving", "Inventory optimizer, workshop scheduler", "Six Sigma Yellow Belt", "9876500015"),
                ("Meera", "Nair", "meera.nair", "meera@college.edu", "student123", "CIV006", "Civil", 6.9, 1, "Excel, SQL basics, Communication, Documentation", "Site report dashboard, cost estimator", "Project Management Fundamentals", "9876500016"),
                ("Arjun", "Menon", "arjun.menon", "arjun@college.edu", "student123", "CSE007", "Computer Science", 9.1, 0, "C++, Python, System Design, AWS, Docker", "Microservices app, code judge platform", "AWS Solutions Architect Associate", "9876500017"),
                ("Nisha", "Reddy", "nisha.reddy", "nisha@college.edu", "student123", "IT008", "Information Technology", 8.0, 0, "SQL, Python, Statistics, Power BI, Excel", "Sales dashboard, student predictor", "Microsoft Power BI Data Analyst", "9876500018"),
            ]

            student_ids = {}

            for first_name, last_name, username, email, password, register_number, department, cgpa, backlog_count, skills, projects, certifications, contact_number in students:
                cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
                user_row = cursor.fetchone()
                if user_row:
                    user_id = user_row[0]
                    cursor.execute("UPDATE users SET username = %s WHERE id = %s", (username, user_id))
                else:
                    student_pw = generate_password_hash(password)
                    cursor.execute(
                        "INSERT INTO users (username, email, password_hash, role) VALUES (%s, %s, %s, 'student')",
                        (username, email, student_pw),
                    )
                    user_id = cursor.lastrowid
                    print(f"Student created: {email} / {password}")

                cursor.execute("SELECT id FROM students WHERE user_id = %s", (user_id,))
                student_row = cursor.fetchone()
                if student_row:
                    student_id = student_row[0]
                    cursor.execute(
                        """
                        UPDATE students
                        SET register_number = %s, first_name = %s, last_name = %s, department = %s, mentor_id = %s
                        WHERE id = %s
                        """,
                        (register_number, first_name, last_name, department, mentor_id, student_id),
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO students (user_id, register_number, first_name, last_name, department, mentor_id)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (user_id, register_number, first_name, last_name, department, mentor_id),
                    )
                    student_id = cursor.lastrowid

                student_ids[register_number] = student_id

                cursor.execute("SELECT id FROM student_profiles WHERE student_id = %s", (student_id,))
                profile_row = cursor.fetchone()
                if profile_row:
                    cursor.execute(
                        """
                        UPDATE student_profiles
                        SET cgpa = %s, skills = %s, projects = %s, certifications = %s, backlog_count = %s, contact_number = %s
                        WHERE student_id = %s
                        """,
                        (cgpa, skills, projects, certifications, backlog_count, contact_number, student_id),
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO student_profiles (student_id, cgpa, skills, projects, certifications, backlog_count, contact_number)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (student_id, cgpa, skills, projects, certifications, backlog_count, contact_number),
                    )

            companies = [
                (
                    "Google",
                    "https://about.google/",
                    "Global technology company focused on search, cloud, AI, mobile platforms, and large-scale software systems.",
                    "Visited campus previously for software engineering and product roles with strong internship conversion."
                ),
                (
                    "Goldman Sachs",
                    "https://www.goldmansachs.com/",
                    "Leading global investment banking, securities, and asset management firm with strong engineering teams.",
                    "Known to hire analysts and engineering graduates for technology and operations roles."
                ),
                (
                    "JPMorgan Chase",
                    "https://www.jpmorganchase.com/",
                    "Global financial services firm with major hiring across software engineering, data, and cybersecurity.",
                    "Regular recruiter for technology analyst and software developer programs."
                ),
                (
                    "Microsoft",
                    "https://www.microsoft.com/",
                    "Technology company spanning cloud, productivity, AI, operating systems, and enterprise platforms.",
                    "Popular recruiter for software engineering, support engineering, and cloud roles."
                ),
                (
                    "Amazon",
                    "https://www.amazon.jobs/",
                    "Global ecommerce and cloud company hiring across SDE, operations tech, and analytics functions.",
                    "Regular campus recruiter for SDE and business analyst roles."
                ),
                (
                    "Adobe",
                    "https://www.adobe.com/",
                    "Digital media and experience company known for creative tools, analytics, and cloud services.",
                    "Recruited for frontend engineering, QA, and product analytics roles."
                ),
                (
                    "Oracle",
                    "https://www.oracle.com/",
                    "Enterprise software and cloud infrastructure provider with strong database and backend teams.",
                    "Frequently hires for database, backend, and cloud operations roles."
                ),
                (
                    "IBM",
                    "https://www.ibm.com/",
                    "Technology and consulting company with roles across software, automation, hybrid cloud, and data.",
                    "Known for associate system engineer and data engineering hiring."
                ),
                (
                    "Accenture",
                    "https://www.accenture.com/",
                    "Global consulting and technology services company with software, analytics, and operations tracks.",
                    "Large-volume recruiter for software and analytics associate roles."
                ),
                (
                    "Deloitte",
                    "https://www.deloitte.com/",
                    "Professional services firm with consulting, risk, analytics, and technology implementation practices.",
                    "Regular recruiter for consulting analysts and enterprise application developers."
                ),
                (
                    "Infosys",
                    "https://www.infosys.com/",
                    "Global digital services and consulting company with engineering, systems, and analytics roles.",
                    "Consistent recruiter across engineering departments."
                ),
                (
                    "TCS",
                    "https://www.tcs.com/",
                    "IT services and consulting company recruiting for engineering, digital, and support tracks.",
                    "High-volume recruiter across multiple departments and roles."
                ),
                (
                    "Flipkart",
                    "https://www.flipkartcareers.com/",
                    "Indian ecommerce platform hiring for product engineering, analytics, and marketplace operations.",
                    "Selective recruiter for product engineering and data roles."
                ),
            ]

            company_ids = {}
            for name, website_url, profile, past_history in companies:
                cursor.execute("SELECT id FROM companies WHERE name = %s", (name,))
                row = cursor.fetchone()
                if row:
                    company_ids[name] = row[0]
                    cursor.execute(
                        "UPDATE companies SET website_url = %s, profile = %s, past_history = %s WHERE id = %s",
                        (website_url, profile, past_history, row[0]),
                    )
                else:
                    cursor.execute(
                        "INSERT INTO companies (name, website_url, profile, past_history) VALUES (%s, %s, %s, %s)",
                        (name, website_url, profile, past_history),
                    )
                    company_ids[name] = cursor.lastrowid
                    print(f"Company created: {name}")

            today = date.today()
            job_postings = [
                {"company": "Google", "title": "Software Engineer", "role": "Backend Developer", "location": "Bengaluru", "ctc": "28 LPA", "eligibility_criteria": "Strong DSA, OOP, database fundamentals, and no active backlogs.", "required_skills": "Python, Java, Data Structures, Algorithms, SQL, Distributed Systems", "allowed_departments": "Computer Science,Information Technology,Electronics", "max_backlogs": 0, "min_cgpa": 8.0, "application_deadline": today + timedelta(days=20)},
                {"company": "Google", "title": "Data Analyst", "role": "Business Intelligence Analyst", "location": "Hyderabad", "ctc": "18 LPA", "eligibility_criteria": "Comfort with analytics, SQL, dashboards, and structured problem solving.", "required_skills": "SQL, Python, Data Visualization, Statistics, Spreadsheets", "allowed_departments": "All", "max_backlogs": 1, "min_cgpa": 7.2, "application_deadline": today + timedelta(days=15)},
                {"company": "Goldman Sachs", "title": "Analyst - Engineering", "role": "Full Stack Developer", "location": "Bengaluru", "ctc": "22 LPA", "eligibility_criteria": "Strong coding, DBMS, OS, and networking fundamentals.", "required_skills": "Java, Spring Boot, React, SQL, REST APIs, Problem Solving", "allowed_departments": "Computer Science,Information Technology,Electronics", "max_backlogs": 0, "min_cgpa": 7.5, "application_deadline": today + timedelta(days=18)},
                {"company": "JPMorgan Chase", "title": "Software Engineer Program", "role": "Application Developer", "location": "Mumbai", "ctc": "20 LPA", "eligibility_criteria": "Good coding proficiency and SDLC understanding.", "required_skills": "Python, Java, Git, SQL, OOP, Debugging", "allowed_departments": "Computer Science,Information Technology,Electronics,Electrical", "max_backlogs": 1, "min_cgpa": 7.0, "application_deadline": today + timedelta(days=25)},
                {"company": "Microsoft", "title": "Software Engineer I", "role": "Cloud Platform Developer", "location": "Hyderabad", "ctc": "24 LPA", "eligibility_criteria": "Strong coding round performance and understanding of cloud-native development.", "required_skills": "C#, Java, Azure, APIs, DSA, OOP", "allowed_departments": "Computer Science,Information Technology", "max_backlogs": 0, "min_cgpa": 8.2, "application_deadline": today + timedelta(days=22)},
                {"company": "Microsoft", "title": "Support Engineer", "role": "Azure Support Associate", "location": "Bengaluru", "ctc": "14 LPA", "eligibility_criteria": "Strong communication and troubleshooting mindset.", "required_skills": "Networking, Linux, Azure basics, SQL, Customer Support", "allowed_departments": "Computer Science,Information Technology,Electronics,Electrical", "max_backlogs": 1, "min_cgpa": 7.0, "application_deadline": today + timedelta(days=19)},
                {"company": "Amazon", "title": "SDE I", "role": "Software Development Engineer", "location": "Bengaluru", "ctc": "26 LPA", "eligibility_criteria": "Excellent coding and low-latency systems interest.", "required_skills": "Java, C++, DSA, Low Level Design, SQL", "allowed_departments": "Computer Science,Information Technology", "max_backlogs": 0, "min_cgpa": 8.0, "application_deadline": today + timedelta(days=17)},
                {"company": "Amazon", "title": "Business Analyst", "role": "Operations Analytics", "location": "Hyderabad", "ctc": "13 LPA", "eligibility_criteria": "Comfort with business metrics and structured thinking.", "required_skills": "SQL, Excel, Python, Data Analysis, Visualization", "allowed_departments": "All", "max_backlogs": 1, "min_cgpa": 7.0, "application_deadline": today + timedelta(days=21)},
                {"company": "Adobe", "title": "Frontend Engineer", "role": "UI Developer", "location": "Noida", "ctc": "21 LPA", "eligibility_criteria": "Strong frontend fundamentals and product sense.", "required_skills": "JavaScript, React, CSS, Accessibility, APIs", "allowed_departments": "Computer Science,Information Technology", "max_backlogs": 0, "min_cgpa": 7.8, "application_deadline": today + timedelta(days=24)},
                {"company": "Adobe", "title": "Quality Engineer", "role": "Automation QA", "location": "Bengaluru", "ctc": "15 LPA", "eligibility_criteria": "Testing mindset with automation interest.", "required_skills": "Java, Selenium, API Testing, SQL, Test Design", "allowed_departments": "Computer Science,Information Technology,Electronics", "max_backlogs": 1, "min_cgpa": 7.0, "application_deadline": today + timedelta(days=16)},
                {"company": "Oracle", "title": "Associate Software Engineer", "role": "Database Platform Engineer", "location": "Bengaluru", "ctc": "17 LPA", "eligibility_criteria": "Strong SQL and CS fundamentals.", "required_skills": "Java, SQL, PL/SQL, DBMS, OOP", "allowed_departments": "Computer Science,Information Technology", "max_backlogs": 0, "min_cgpa": 7.4, "application_deadline": today + timedelta(days=26)},
                {"company": "Oracle", "title": "Cloud Analyst", "role": "OCI Operations Analyst", "location": "Hyderabad", "ctc": "12 LPA", "eligibility_criteria": "Interest in cloud operations and monitoring.", "required_skills": "Linux, SQL, Cloud Basics, Scripting, Monitoring", "allowed_departments": "Computer Science,Information Technology,Electronics,Electrical", "max_backlogs": 1, "min_cgpa": 6.8, "application_deadline": today + timedelta(days=20)},
                {"company": "IBM", "title": "Associate System Engineer", "role": "Application Support Engineer", "location": "Pune", "ctc": "10 LPA", "eligibility_criteria": "Good analytical skills and willingness to work on enterprise systems.", "required_skills": "Java, SQL, Linux, Communication, Debugging", "allowed_departments": "All", "max_backlogs": 1, "min_cgpa": 6.5, "application_deadline": today + timedelta(days=28)},
                {"company": "IBM", "title": "Data Engineer", "role": "ETL Developer", "location": "Bengaluru", "ctc": "14 LPA", "eligibility_criteria": "Good data processing and scripting ability.", "required_skills": "Python, SQL, ETL, Data Warehousing, Linux", "allowed_departments": "Computer Science,Information Technology,Electronics", "max_backlogs": 1, "min_cgpa": 7.0, "application_deadline": today + timedelta(days=23)},
                {"company": "Accenture", "title": "Application Development Associate", "role": "Software Engineering Associate", "location": "Chennai", "ctc": "9.5 LPA", "eligibility_criteria": "Strong communication and coding basics.", "required_skills": "Java, Python, SQL, OOP, Communication", "allowed_departments": "All", "max_backlogs": 1, "min_cgpa": 6.5, "application_deadline": today + timedelta(days=30)},
                {"company": "Accenture", "title": "Analytics Associate", "role": "Data Reporting Analyst", "location": "Bengaluru", "ctc": "11 LPA", "eligibility_criteria": "Comfort with reporting, dashboards, and business metrics.", "required_skills": "Excel, SQL, Power BI, Python, Communication", "allowed_departments": "All", "max_backlogs": 1, "min_cgpa": 6.8, "application_deadline": today + timedelta(days=18)},
                {"company": "Deloitte", "title": "Analyst", "role": "Technology Consulting Analyst", "location": "Hyderabad", "ctc": "12 LPA", "eligibility_criteria": "Strong communication and consulting aptitude.", "required_skills": "SQL, Excel, Problem Solving, Presentation, SDLC", "allowed_departments": "All", "max_backlogs": 1, "min_cgpa": 7.0, "application_deadline": today + timedelta(days=19)},
                {"company": "Deloitte", "title": "Associate Developer", "role": "Enterprise Application Developer", "location": "Bengaluru", "ctc": "13.5 LPA", "eligibility_criteria": "Strong fundamentals in coding and business applications.", "required_skills": "Java, APIs, SQL, OOP, Git", "allowed_departments": "Computer Science,Information Technology,Electronics", "max_backlogs": 1, "min_cgpa": 7.1, "application_deadline": today + timedelta(days=25)},
                {"company": "Infosys", "title": "Systems Engineer", "role": "Digital Specialist Engineer", "location": "Mysuru", "ctc": "8.5 LPA", "eligibility_criteria": "Strong analytical and coding aptitude.", "required_skills": "Java, Python, SQL, DSA, Communication", "allowed_departments": "All", "max_backlogs": 1, "min_cgpa": 6.5, "application_deadline": today + timedelta(days=27)},
                {"company": "Infosys", "title": "Data Process Associate", "role": "MIS Analyst", "location": "Pune", "ctc": "7.2 LPA", "eligibility_criteria": "Strong Excel and reporting capability.", "required_skills": "Excel, SQL, Documentation, Reporting, Power BI", "allowed_departments": "All", "max_backlogs": 2, "min_cgpa": 6.0, "application_deadline": today + timedelta(days=22)},
                {"company": "TCS", "title": "Assistant System Engineer", "role": "Software Trainee", "location": "Chennai", "ctc": "7.0 LPA", "eligibility_criteria": "Basic coding proficiency and communication skills.", "required_skills": "C, Java, SQL, Communication, Aptitude", "allowed_departments": "All", "max_backlogs": 1, "min_cgpa": 6.0, "application_deadline": today + timedelta(days=29)},
                {"company": "TCS", "title": "Business Process Analyst", "role": "Operations Analyst", "location": "Mumbai", "ctc": "6.8 LPA", "eligibility_criteria": "Strong communication and process orientation.", "required_skills": "Excel, Documentation, SQL basics, Communication", "allowed_departments": "All", "max_backlogs": 2, "min_cgpa": 6.0, "application_deadline": today + timedelta(days=21)},
                {"company": "Flipkart", "title": "Product Support Engineer", "role": "Marketplace Operations Engineer", "location": "Bengaluru", "ctc": "12.5 LPA", "eligibility_criteria": "Interest in ecommerce operations and tooling.", "required_skills": "SQL, Python, Excel, Debugging, Communication", "allowed_departments": "Computer Science,Information Technology,Electronics", "max_backlogs": 1, "min_cgpa": 7.0, "application_deadline": today + timedelta(days=17)},
                {"company": "Flipkart", "title": "Data Analyst", "role": "Supply Chain Analyst", "location": "Bengaluru", "ctc": "14 LPA", "eligibility_criteria": "Strong data analysis and dashboarding capability.", "required_skills": "SQL, Python, Excel, Tableau, Statistics", "allowed_departments": "All", "max_backlogs": 1, "min_cgpa": 7.2, "application_deadline": today + timedelta(days=24)},
            ]

            for job in job_postings:
                company_id = company_ids[job["company"]]
                cursor.execute(
                    """
                    SELECT id FROM jobs
                    WHERE company_id = %s AND title = %s AND role = %s
                    """,
                    (company_id, job["title"], job["role"]),
                )
                if cursor.fetchone():
                    cursor.execute(
                        """
                        UPDATE jobs
                        SET location = %s,
                            ctc = %s,
                            eligibility_criteria = %s,
                            required_skills = %s,
                            allowed_departments = %s,
                            max_backlogs = %s,
                            min_cgpa = %s,
                            application_deadline = %s
                        WHERE company_id = %s AND title = %s AND role = %s
                        """,
                        (
                            job["location"],
                            job["ctc"],
                            job["eligibility_criteria"],
                            job["required_skills"],
                            job["allowed_departments"],
                            job["max_backlogs"],
                            job["min_cgpa"],
                            job["application_deadline"],
                            company_id,
                            job["title"],
                            job["role"],
                        ),
                    )
                    cursor.execute(
                        "SELECT id FROM jobs WHERE company_id = %s AND title = %s AND role = %s",
                        (company_id, job["title"], job["role"]),
                    )
                    existing_job = cursor.fetchone()
                    if existing_job:
                        job["id"] = existing_job[0]
                    continue

                cursor.execute(
                    """
                    INSERT INTO jobs (
                        company_id, title, role, location, ctc, eligibility_criteria,
                        required_skills, allowed_departments, max_backlogs,
                        min_cgpa, application_deadline
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        company_id,
                        job["title"],
                        job["role"],
                        job["location"],
                        job["ctc"],
                        job["eligibility_criteria"],
                        job["required_skills"],
                        job["allowed_departments"],
                        job["max_backlogs"],
                        job["min_cgpa"],
                        job["application_deadline"],
                    ),
                )
                print(f"Job created: {job['company']} - {job['title']}")
                job["id"] = cursor.lastrowid

            # Seed a few placed outcomes so admin dashboards and reports have demo data.
            job_lookup = {(job["company"], job["title"], job["role"]): job.get("id") for job in job_postings}
            fake_placements = [
                ("CSE001", "Google", "Software Engineer", "Backend Developer"),
                ("CSE007", "Amazon", "SDE I", "Software Development Engineer"),
                ("IT002", "Adobe", "Frontend Engineer", "UI Developer"),
                ("IT008", "JPMorgan Chase", "Software Engineer Program", "Application Developer"),
            ]

            for register_number, company, title, role in fake_placements:
                student_id = student_ids.get(register_number)
                job_id = job_lookup.get((company, title, role))
                if not student_id or not job_id:
                    continue

                cursor.execute(
                    "SELECT id FROM applications WHERE student_id = %s AND job_id = %s",
                    (student_id, job_id),
                )
                app_row = cursor.fetchone()
                if app_row:
                    application_id = app_row[0]
                else:
                    cursor.execute(
                        "INSERT INTO applications (student_id, job_id) VALUES (%s, %s)",
                        (student_id, job_id),
                    )
                    application_id = cursor.lastrowid

                cursor.execute("SELECT id FROM application_status WHERE application_id = %s", (application_id,))
                status_row = cursor.fetchone()
                if status_row:
                    cursor.execute(
                        "UPDATE application_status SET stage = 'Selected', updated_at = CURRENT_TIMESTAMP WHERE application_id = %s",
                        (application_id,),
                    )
                else:
                    cursor.execute(
                        "INSERT INTO application_status (application_id, stage) VALUES (%s, 'Selected')",
                        (application_id,),
                    )

        connection.commit()
    finally:
        connection.close()

if __name__ == "__main__":
    seed_db()
