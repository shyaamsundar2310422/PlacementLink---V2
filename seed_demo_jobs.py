"""Idempotently add clearly labeled demo placement openings to the current DB."""

from datetime import date, timedelta
import os
from pathlib import Path

from database.db import get_db_connection
from ml.embedding_service import embedding_to_json, generate_embedding
from ml.semantic_matcher import build_job_text
from models.job_model import create_job


DEMO_MARKER = "[PlacementLink demo seed v1]"
DEMO_JOBS = (
    {
        "company": "TCS",
        "website": "https://www.tcs.com/",
        "title": "Graduate Software Engineer — Demo",
        "role": "Build and maintain enterprise web services; collaborate with product teams and write automated tests.",
        "location": "Chennai, India",
        "ctc": "₹7.0 LPA",
        "eligibility": "Minimum CGPA 7.0; up to 1 backlog. " + DEMO_MARKER,
        "skills": "Java, Python, SQL, Data Structures, REST APIs",
        "departments": "Computer Science, Information Technology, Electronics",
        "max_backlogs": 1,
        "min_cgpa": 7.0,
    },
    {
        "company": "Infosys",
        "website": "https://www.infosys.com/",
        "title": "Systems Engineer — Demo",
        "role": "Develop and support business applications, participate in code reviews, and troubleshoot production issues.",
        "location": "Bengaluru, India",
        "ctc": "₹6.5 LPA",
        "eligibility": "Minimum CGPA 6.5; no active backlogs. " + DEMO_MARKER,
        "skills": "Java, Python, SQL, Git, Problem Solving",
        "departments": "All",
        "max_backlogs": 0,
        "min_cgpa": 6.5,
    },
    {
        "company": "Zoho",
        "website": "https://www.zoho.com/",
        "title": "Product Software Developer — Demo",
        "role": "Design product features, build reliable backend components, and improve application performance.",
        "location": "Chennai, India",
        "ctc": "₹10.0 LPA",
        "eligibility": "Minimum CGPA 7.0; no active backlogs. " + DEMO_MARKER,
        "skills": "Java, C++, Data Structures, Object Oriented Programming, SQL",
        "departments": "Computer Science, Information Technology",
        "max_backlogs": 0,
        "min_cgpa": 7.0,
    },
    {
        "company": "Freshworks",
        "website": "https://www.freshworks.com/",
        "title": "Associate Backend Engineer — Demo",
        "role": "Implement APIs and service integrations, add automated tests, and monitor service reliability.",
        "location": "Chennai, India",
        "ctc": "₹12.0 LPA",
        "eligibility": "Minimum CGPA 7.5; no active backlogs. " + DEMO_MARKER,
        "skills": "Python, Node.js, REST APIs, PostgreSQL, Docker",
        "departments": "Computer Science, Information Technology",
        "max_backlogs": 0,
        "min_cgpa": 7.5,
    },
    {
        "company": "Accenture",
        "website": "https://www.accenture.com/",
        "title": "Data Analyst Associate — Demo",
        "role": "Prepare datasets, build dashboards, and explain analysis findings to client delivery teams.",
        "location": "Hyderabad, India",
        "ctc": "₹6.0 LPA",
        "eligibility": "Minimum CGPA 6.5; up to 2 backlogs. " + DEMO_MARKER,
        "skills": "SQL, Python, Excel, Power BI, Statistics",
        "departments": "All",
        "max_backlogs": 2,
        "min_cgpa": 6.5,
    },
    {
        "company": "Deloitte",
        "website": "https://www.deloitte.com/",
        "title": "Technology Analyst — Demo",
        "role": "Support cloud application delivery, document technical findings, and automate repeatable operations.",
        "location": "Bengaluru, India",
        "ctc": "₹8.0 LPA",
        "eligibility": "Minimum CGPA 7.0; no active backlogs. " + DEMO_MARKER,
        "skills": "Python, SQL, AWS, Linux, Git",
        "departments": "Computer Science, Information Technology, Electronics",
        "max_backlogs": 0,
        "min_cgpa": 7.0,
    },
    {
        "company": "Amazon",
        "website": "https://www.amazon.jobs/",
        "title": "Software Development Engineer I — Demo",
        "role": "Build scalable services, write maintainable code, and participate in design and operational reviews.",
        "location": "Bengaluru, India",
        "ctc": "₹18.0 LPA",
        "eligibility": "Minimum CGPA 8.0; no active backlogs. " + DEMO_MARKER,
        "skills": "Java, C++, Data Structures, Algorithms, Distributed Systems",
        "departments": "Computer Science, Information Technology",
        "max_backlogs": 0,
        "min_cgpa": 8.0,
    },
    {
        "company": "Microsoft",
        "website": "https://careers.microsoft.com/",
        "title": "Cloud Support Engineer — Demo",
        "role": "Investigate cloud platform issues, communicate technical guidance, and improve support documentation.",
        "location": "Hyderabad, India",
        "ctc": "₹14.0 LPA",
        "eligibility": "Minimum CGPA 7.5; no active backlogs. " + DEMO_MARKER,
        "skills": "Azure, C#, Networking, Linux, Troubleshooting",
        "departments": "Computer Science, Information Technology, Electronics",
        "max_backlogs": 0,
        "min_cgpa": 7.5,
    },
    {
        "company": "Wipro",
        "website": "https://www.wipro.com/",
        "title": "Project Engineer — Demo",
        "role": "Contribute to application delivery, write unit tests, and support integration and release activities.",
        "location": "Pune, India",
        "ctc": "₹5.5 LPA",
        "eligibility": "Minimum CGPA 6.0; up to 2 backlogs. " + DEMO_MARKER,
        "skills": "Java, Python, SQL, Git, Software Testing",
        "departments": "All",
        "max_backlogs": 2,
        "min_cgpa": 6.0,
    },
    {
        "company": "TCS",
        "website": "https://www.tcs.com/",
        "title": "Business Intelligence Analyst — Demo",
        "role": "Create data models and dashboards, validate reporting quality, and summarize operational trends.",
        "location": "Pune, India",
        "ctc": "₹6.5 LPA",
        "eligibility": "Minimum CGPA 6.5; up to 1 backlog. " + DEMO_MARKER,
        "skills": "SQL, Excel, Power BI, Python, Data Visualization",
        "departments": "All",
        "max_backlogs": 1,
        "min_cgpa": 6.5,
    },
    {
        "company": "Infosys",
        "website": "https://www.infosys.com/",
        "title": "Cloud Operations Associate — Demo",
        "role": "Automate cloud environment checks, monitor service health, and support secure deployments.",
        "location": "Mysuru, India",
        "ctc": "₹7.5 LPA",
        "eligibility": "Minimum CGPA 7.0; no active backlogs. " + DEMO_MARKER,
        "skills": "AWS, Linux, Python, Docker, CI/CD",
        "departments": "Computer Science, Information Technology, Electronics",
        "max_backlogs": 0,
        "min_cgpa": 7.0,
    },
    {
        "company": "Zoho",
        "website": "https://www.zoho.com/",
        "title": "Quality Automation Engineer — Demo",
        "role": "Build browser and API automation, triage defects, and work with engineers on release readiness.",
        "location": "Chennai, India",
        "ctc": "₹8.5 LPA",
        "eligibility": "Minimum CGPA 7.0; up to 1 backlog. " + DEMO_MARKER,
        "skills": "Java, Selenium, API Testing, SQL, Test Automation",
        "departments": "Computer Science, Information Technology",
        "max_backlogs": 1,
        "min_cgpa": 7.0,
    },
    {
        "company": "Freshworks",
        "website": "https://www.freshworks.com/",
        "title": "Product Support Engineer — Demo",
        "role": "Reproduce customer issues, diagnose web application behavior, and share clear technical resolutions.",
        "location": "Chennai, India",
        "ctc": "₹7.0 LPA",
        "eligibility": "Minimum CGPA 6.5; up to 2 backlogs. " + DEMO_MARKER,
        "skills": "SQL, REST APIs, Linux, Troubleshooting, Communication",
        "departments": "All",
        "max_backlogs": 2,
        "min_cgpa": 6.5,
    },
    {
        "company": "Wipro",
        "website": "https://www.wipro.com/",
        "title": "Cloud Automation Engineer — Demo",
        "role": "Automate cloud deployment and service checks using small Python tools and container workflows.",
        "location": "Bengaluru, India",
        "ctc": "₹8.0 LPA",
        "eligibility": "Minimum CGPA 6.5; up to 1 backlog. " + DEMO_MARKER,
        "skills": "Python, AWS, Docker",
        "departments": "All",
        "max_backlogs": 1,
        "min_cgpa": 6.5,
    },
    {
        "company": "Wipro",
        "website": "https://www.wipro.com/",
        "title": "Cloud Platform Engineer — Demo",
        "role": "Support cloud platform automation, improve container deployments, and document operational practices.",
        "location": "Hyderabad, India",
        "ctc": "₹9.0 LPA",
        "eligibility": "Minimum CGPA 6.5; up to 1 backlog. " + DEMO_MARKER,
        "skills": "Python, AWS, Docker, Kubernetes",
        "departments": "All",
        "max_backlogs": 1,
        "min_cgpa": 6.5,
    },
)


def _precompute_local_embeddings(jobs):
    """Use MiniLM only when its snapshot is already cached; never download it."""
    if not jobs:
        return []
    # Hub/Transformers read these settings during import; set them first so
    # this seed script cannot trigger a model download.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    try:
        from huggingface_hub.constants import HF_HUB_CACHE

        snapshots = Path(HF_HUB_CACHE) / "models--sentence-transformers--all-MiniLM-L6-v2" / "snapshots"
        if not snapshots.is_dir() or not any(snapshots.iterdir()):
            return [None] * len(jobs)
    except Exception:
        return [None] * len(jobs)

    results = []
    for index, job in enumerate(jobs):
        try:
            semantic_job = {
                "title": job["title"],
                "role": job["role"],
                "required_skills": job["skills"],
                "eligibility_criteria": job["eligibility"],
                "allowed_departments": job["departments"],
            }
            job_text = build_job_text(semantic_job)
            results.append(embedding_to_json(generate_embedding(job_text), source_text=job_text))
        except Exception:
            results.append(None)
            results.extend([None] * (len(jobs) - index - 1))
            break
    return results


def seed_demo_jobs(connection_factory=None, job_creator=None, today=None, embedding_factory=None):
    """Insert missing demo companies and jobs without modifying existing rows.

    New openings use the existing job model, including its per-job embedding
    generation attempt. If that service is unavailable, create_job safely stores
    a null embedding and the normal matcher reports semantic score zero.
    """
    connection_factory = connection_factory or get_db_connection
    job_creator = job_creator or create_job
    embedding_factory = embedding_factory or _precompute_local_embeddings
    today = today or date.today()
    deadline = today + timedelta(days=180)
    pending_jobs = []
    connection = connection_factory()
    try:
        with connection.cursor() as cursor:
            company_ids = {}
            for job in DEMO_JOBS:
                name = job["company"]
                if name not in company_ids:
                    cursor.execute(
                        "SELECT id FROM companies WHERE name = %s ORDER BY id LIMIT 1",
                        (name,),
                    )
                    company = cursor.fetchone()
                    if company:
                        company_ids[name] = company["id"]
                    else:
                        cursor.execute(
                            "INSERT INTO companies (name, website_url, profile, past_history) "
                            "VALUES (%s, %s, %s, %s)",
                            (
                                name,
                                job["website"],
                                f"{name} demo placement company record.",
                                "Demo seed record; not an employer posting.",
                            ),
                        )
                        company_ids[name] = cursor.lastrowid

                company_id = company_ids[name]
                cursor.execute(
                    "SELECT id FROM jobs WHERE company_id = %s AND title = %s "
                    "AND eligibility_criteria LIKE %s ORDER BY id LIMIT 1",
                    (company_id, job["title"], f"%{DEMO_MARKER}%"),
                )
                if cursor.fetchone():
                    continue
                pending_jobs.append((company_id, job))
        connection.commit()
    finally:
        connection.close()

    inserted = 0
    embeddings = embedding_factory([job for _, job in pending_jobs])
    for (company_id, job), embedding in zip(pending_jobs, embeddings):
        job_id = job_creator(
            company_id,
            job["title"],
            job["role"],
            job["location"],
            job["ctc"],
            job["eligibility"],
            job["skills"],
            job["departments"],
            job["max_backlogs"],
            job["min_cgpa"],
            deadline,
            precomputed_embedding=embedding,
        )
        if job_id:
            inserted += 1
    return inserted


if __name__ == "__main__":
    count = seed_demo_jobs()
    print(f"Inserted {count} demo job(s); existing jobs were left unchanged.")
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS total, SUM(job_embedding IS NOT NULL) AS embedded "
                "FROM jobs WHERE eligibility_criteria LIKE %s",
                (f"%{DEMO_MARKER}%",),
            )
            result = cursor.fetchone()
        total = result["total"]
        embedded = result["embedded"] or 0
    finally:
        connection.close()
    print(f"Demo jobs present: {total}; jobs with semantic embeddings: {embedded}.")
    if embedded < total:
        print("Some semantic embeddings are unavailable; the UI will identify those scores as unavailable.")
