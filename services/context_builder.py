from models.job_model import get_all_active_jobs_with_match
from services.placement_agent import (
    get_closest_companies,
    get_learning_recommendations,
    get_missing_skills_analysis,
    get_top_recommended_jobs,
    what_if_analysis,
)

context_cache = {}


def _job_context(job):
    explainability = job.get("explainability") or {}
    return {
        "company": job.get("company_name"),
        "role": job.get("title"),
        "match_score": job.get("match_score", 0),
        "rule_score": job.get("rule_score", 0),
        "semantic_score": job.get("semantic_score", 0),
        "matched_skills": explainability.get("matched_skills") or [],
        "missing_skills": explainability.get("missing_skills") or [],
        "match_reasons": job.get("match_reasons") or {},
    }


def build_student_context(student_id):
    if student_id in context_cache:
        return context_cache[student_id]

    jobs = get_all_active_jobs_with_match(student_id) or []
    closest_companies = get_closest_companies(student_id, jobs=jobs)
    top_jobs = get_top_recommended_jobs(student_id, jobs=jobs)
    context = {
        "missing_skills": get_missing_skills_analysis(student_id, jobs=jobs),
        "learning": get_learning_recommendations(student_id, jobs=jobs),
        "companies": [_job_context(job) for job in closest_companies],
        "what_if": what_if_analysis(student_id, jobs=jobs),
        "top_jobs": [_job_context(job) for job in top_jobs],
    }
    context_cache[student_id] = context
    return context


def clear_student_context(student_id):
    context_cache.pop(student_id, None)


def clear_all_student_context():
    context_cache.clear()
