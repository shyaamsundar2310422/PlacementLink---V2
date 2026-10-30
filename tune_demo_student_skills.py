"""Add narrowly scoped demo skills to selected demo profiles and refresh vectors.

Run with: python tune_demo_student_skills.py
The operation is additive and idempotent; it does not change eligibility fields.
"""
import logging
import re

from database.db import get_db_connection
from ml.embedding_service import embedding_to_json, generate_embedding, json_to_embedding
from ml.semantic_matcher import build_profile_text
from models.job_model import _calculate_profile_job_match

logger = logging.getLogger(__name__)

# Additions are grounded in the existing resume, project, certification, or stack.
SKILL_ADDITIONS = {
    "aarav.sharma": ["Git", "JavaScript", "React", "MySQL", "HTML", "CSS", "Data Structures", "Algorithms"],
    "diya.patel": ["SQL", "Git", "JavaScript", "React", "HTML", "CSS"],
    "rahul.verma": ["Excel", "Statistics", "Data Visualization"],
}


def _append_missing_skills(current, additions):
    existing = [part.strip() for part in (current or "").split(",") if part.strip()]
    normalized = {re.sub(r"\s+", " ", item).casefold() for item in existing}
    for skill in additions:
        key = re.sub(r"\s+", " ", skill).casefold()
        if key not in normalized:
            existing.append(skill)
            normalized.add(key)
    return ", ".join(existing)


def tune_demo_student_skills():
    logging.getLogger("models.job_model").setLevel(logging.ERROR)
    connection = get_db_connection()
    results = []
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT s.id AS student_id,s.department,sp.cgpa,sp.skills,sp.projects,
                          sp.certifications,sp.backlog_count,sp.resume_text,sp.resume_url,
                          sp.resume_embedding,u.username
                   FROM students s
                   JOIN users u ON u.id=s.user_id
                   JOIN student_profiles sp ON sp.student_id=s.id
                   WHERE u.username IN (%s,%s,%s)
                   FOR UPDATE""",
                tuple(SKILL_ADDITIONS),
            )
            profiles = cursor.fetchall() or []
            missing = set(SKILL_ADDITIONS) - {profile["username"] for profile in profiles}
            if missing:
                raise RuntimeError(f"Could not find requested demo profiles: {', '.join(sorted(missing))}")

            cursor.execute(
                """SELECT j.*,c.name AS company_name FROM jobs j
                   JOIN companies c ON c.id=j.company_id
                   WHERE j.application_deadline>=CURDATE()"""
            )
            jobs = cursor.fetchall() or []

            pending = []
            for profile in profiles:
                updated_skills = _append_missing_skills(
                    profile.get("skills"), SKILL_ADDITIONS[profile["username"]]
                )
                if updated_skills == (profile.get("skills") or ""):
                    continue
                before = sum(bool(_calculate_profile_job_match(profile, job)["is_match"]) for job in jobs)
                updated_profile = {**profile, "skills": updated_skills}
                profile_text = build_profile_text(updated_profile).strip()
                vector = generate_embedding(profile_text)
                if vector is None or len(vector) != 384:
                    raise RuntimeError(f"Embedding generation failed for {profile['username']}")
                vector_json = embedding_to_json(vector, source_text=profile_text)
                if json_to_embedding(vector_json) is None:
                    raise RuntimeError(f"Invalid profile embedding generated for {profile['username']}")
                after = sum(bool(_calculate_profile_job_match(updated_profile, job)["is_match"]) for job in jobs)
                prior_skills = {
                    re.sub(r"\s+", " ", item).casefold()
                    for item in (profile.get("skills") or "").split(",") if item.strip()
                }
                added = [skill for skill in SKILL_ADDITIONS[profile["username"]]
                         if re.sub(r"\s+", " ", skill).casefold() not in prior_skills]
                pending.append((profile, updated_skills, vector_json, before, after, added))

            for profile, updated_skills, vector_json, before, after, added in pending:
                cursor.execute(
                    """UPDATE student_profiles
                       SET skills=%s,resume_embedding=%s,embedding_generated=TRUE
                       WHERE student_id=%s""",
                    (updated_skills, vector_json, profile["student_id"]),
                )
                results.append({
                    "username": profile["username"],
                    "student_id": profile["student_id"],
                    "added_skills": added,
                    "strict_matches_before": before,
                    "strict_matches_after": after,
                })

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    try:
        from services.context_builder import clear_student_context
        for result in results:
            clear_student_context(result["student_id"])
    except ImportError:
        pass
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for result in tune_demo_student_skills():
        print(
            f"{result['username']}: strict matches {result['strict_matches_before']} -> "
            f"{result['strict_matches_after']} of current active jobs"
        )
