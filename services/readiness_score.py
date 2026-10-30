from models.profile_model import get_student_profile
from services.placement_agent import get_top_recommended_jobs
import math


def _profile_items(value):
    return [item for item in (value or "").split(",") if item.strip()]


def calculate_readiness(student_id, recommended_jobs=None):

    profile = get_student_profile(student_id) or {}

    score = 0
    breakdown = {}

    # Resume (20)
    if profile.get("resume_text"):
        breakdown["Resume"] = 20
        score += 20
    else:
        breakdown["Resume"] = 0

    # Skills (25)
    skills = profile.get("skills") or ""
    skill_count = len(_profile_items(skills))

    skill_score = min(skill_count * 2.5, 25)

    breakdown["Skills"] = round(skill_score)
    score += skill_score

    # Projects (20)
    projects = profile.get("projects") or ""
    project_count = len(_profile_items(projects))

    project_score = min(project_count * 10, 20)

    breakdown["Projects"] = round(project_score)
    score += project_score

    # Certifications (10)
    certs = profile.get("certifications") or ""
    cert_count = len(_profile_items(certs))

    cert_score = min(cert_count * 5, 10)

    breakdown["Certifications"] = round(cert_score)
    score += cert_score

    # Top Job Match (15)
    jobs = recommended_jobs if recommended_jobs is not None else get_top_recommended_jobs(student_id)

    if jobs:
        try:
            match_score = float(jobs[0].get("match_score") or 0)
            if not math.isfinite(match_score):
                match_score = 0
        except (TypeError, ValueError):
            match_score = 0
        match_score = max(0, min(100, match_score)) * 0.15
    else:
        match_score = 0

    breakdown["Job Match"] = round(match_score)
    score += match_score

    # Profile completion (10)
    profile_fields = [
        "department",
        "cgpa",
        "skills",
        "projects",
        "resume_text"
    ]

    completed = sum(
        1 for field in profile_fields
        if profile.get(field)
    )

    profile_score = completed / len(profile_fields) * 10

    breakdown["Profile"] = round(profile_score)

    score += profile_score

    score = round(score)

    if score >= 80:
        status = "Placement Ready"
    elif score >= 60:
        status = "Almost Ready"
    else:
        status = "Needs Improvement"

    return {
        "score": score,
        "status": status,
        "breakdown": breakdown
    }
