"""Create clearly labeled demo JDs for active jobs that do not yet have one.

Run with: python seed_demo_job_descriptions.py
Existing job fields are preserved. Jobs with an existing JD are skipped.
"""
import os
import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from config import Config
from database.db import get_db_connection
from ml.embedding_service import embedding_to_json, json_to_embedding, generate_embedding
from ml.resume_parser import extract_resume_text
from ml.semantic_matcher import build_job_text
from models.job_model import ensure_job_description_columns, ensure_job_embedding_column


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def build_demo_description(job):
    """Build a role-specific illustrative JD from the existing job posting fields."""
    company = _clean(job.get("company_name"))
    title = _clean(job.get("title"))
    title = re.sub(r"\s*[—–-]\s*Demo\s*$", "", title, flags=re.IGNORECASE)
    role = _clean(job.get("role"))
    skills = [_clean(skill) for skill in re.split(r"[,;/]", job.get("required_skills") or "") if _clean(skill)]
    skills_text = ", ".join(skills) or "role-relevant software and analytical tools"
    role_lower = f"{title} {role}".lower()

    if any(word in role_lower for word in ("analyst", "business intelligence", "data")):
        responsibilities = [
            "Collect, validate, and analyze operational or product datasets to answer business questions.",
            "Build clear reports and dashboards, explain findings, and document assumptions and data quality checks.",
            "Work with delivery and stakeholder teams to refine metrics and improve recurring reporting workflows.",
        ]
    elif any(word in role_lower for word in ("quality", "automation", "testing")):
        responsibilities = [
            "Design and maintain automated checks for web applications, APIs, and critical user workflows.",
            "Reproduce defects, record useful test evidence, and work with engineers to verify fixes.",
            "Improve regression coverage and communicate release readiness and test risks.",
        ]
    elif any(word in role_lower for word in ("support", "troubleshoot")):
        responsibilities = [
            "Investigate application or platform issues using logs, networking fundamentals, and reproducible checks.",
            "Communicate accurate technical guidance and resolutions to customers and internal teams.",
            "Document recurring issues and contribute fixes or automation that improve service reliability.",
        ]
    elif any(word in role_lower for word in ("cloud", "operations", "platform")):
        responsibilities = [
            "Support cloud environments, deployment workflows, monitoring, and operational runbooks.",
            "Automate repeatable environment checks and deployment tasks using the listed programming and cloud tools.",
            "Help diagnose incidents, improve reliability, and document secure operational practices.",
        ]
    elif any(word in role_lower for word in ("product", "backend", "software", "engineer", "developer")):
        responsibilities = [
            "Implement and maintain application features or backend services that meet documented requirements.",
            "Write readable, tested code; participate in code reviews; and investigate defects and performance issues.",
            "Collaborate with product, QA, and engineering teammates through development and release activities.",
        ]
    else:
        responsibilities = [
            "Contribute to assigned technology delivery work and maintain clear implementation documentation.",
            "Use the listed tools to solve problems, validate results, and support reliable releases.",
            "Collaborate with project stakeholders and communicate progress, risks, and technical findings.",
        ]

    departments = _clean(job.get("allowed_departments")) or "As listed in the placement portal"
    eligibility = _clean(job.get("eligibility_criteria")) or "Meet the placement portal eligibility requirements."
    ctc = _clean(job.get("ctc")) or "As listed in the placement portal"
    location = _clean(job.get("location")) or "As listed in the placement portal"
    deadline = _clean(job.get("application_deadline")) or "As listed in the placement portal"
    lines = [
        "DEMO JOB DESCRIPTION — ILLUSTRATIVE CONTENT, NOT AN OFFICIAL EMPLOYER POSTING",
        f"Employer: {company}",
        f"Position: {title}",
        f"Location: {location}",
        "",
        "Role overview",
        f"This illustrative PlacementLink demo role is based on the existing posting summary: {role}",
        "",
        "Responsibilities",
        *[f"• {item}" for item in responsibilities],
        "",
        "Required skills",
        f"Candidates should be prepared to use or demonstrate: {skills_text}.",
        "",
        "Candidate profile and eligibility",
        f"Eligible departments: {departments}.",
        f"Placement criteria: {eligibility}",
        "Applicants should be able to explain relevant coursework, projects, and their own contributions.",
        "",
        "Compensation and deadline",
        f"Indicative package shown in the demo listing: {ctc}.",
        f"Demo application deadline shown in the listing: {deadline}.",
        "",
        "Demo notice",
        "This description was generated for demonstration and semantic-matching tests. It is not supplied, reviewed, or endorsed by the named employer. Confirm all real role details with the placement office.",
    ]
    return "\n".join(lines)


def write_docx(path, text):
    paragraphs = []
    for line in text.splitlines():
        if not line:
            paragraphs.append("<w:p/>")
        else:
            safe = escape(line)
            paragraphs.append(f'<w:p><w:r><w:t xml:space="preserve">{safe}</w:t></w:r></w:p>')
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body>' + "".join(paragraphs) + '<w:sectPr/></w:body></w:document>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '</Types>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '</Relationships>'
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document_xml)


def seed_demo_job_descriptions():
    ensure_job_embedding_column()
    ensure_job_description_columns()
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    connection = get_db_connection()
    inserted = []
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT j.*, c.name AS company_name
                   FROM jobs j JOIN companies c ON c.id=j.company_id
                   WHERE j.application_deadline >= CURDATE()
                   ORDER BY j.id"""
            )
            jobs = cursor.fetchall() or []

        for job in jobs:
            if (job.get("jd_text") or "").strip() or (job.get("jd_file_url") or "").strip():
                continue
            jd_text = build_demo_description(job)
            doc_path = Path(Config.UPLOAD_FOLDER) / f"demo_jd_job_{job['id']}.docx"
            write_docx(doc_path, jd_text)
            extracted_text = extract_resume_text(doc_path).strip()
            if not extracted_text:
                doc_path.unlink(missing_ok=True)
                raise RuntimeError(f"DOCX extraction verification failed for job {job['id']}")
            semantic_text = build_job_text({**job, "jd_text": extracted_text})
            vector = generate_embedding(semantic_text)
            if vector is None or len(vector) != 384:
                doc_path.unlink(missing_ok=True)
                raise RuntimeError(f"Embedding generation failed for job {job['id']}")
            embedding = embedding_to_json(vector, source_text=semantic_text)
            if json_to_embedding(embedding) is None:
                doc_path.unlink(missing_ok=True)
                raise RuntimeError(f"Invalid embedding generated for job {job['id']}")
            public_path = f"/static/uploads/{doc_path.name}"
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """UPDATE jobs SET jd_text=%s, jd_file_url=%s, job_embedding=%s
                           WHERE id=%s AND (jd_text IS NULL OR jd_text='')
                             AND (jd_file_url IS NULL OR jd_file_url='')""",
                        (extracted_text, public_path, embedding, job["id"]),
                    )
                    if cursor.rowcount:
                        connection.commit()
                        inserted.append(job["id"])
                    else:
                        connection.rollback()
                        doc_path.unlink(missing_ok=True)
            except Exception:
                connection.rollback()
                doc_path.unlink(missing_ok=True)
                raise
    finally:
        connection.close()

    try:
        from services.context_builder import clear_all_student_context
        clear_all_student_context()
    except ImportError:
        pass
    return inserted


if __name__ == "__main__":
    job_ids = seed_demo_job_descriptions()
    print(f"Created demo job descriptions for {len(job_ids)} active jobs: {', '.join(map(str, job_ids)) or 'none'}")
