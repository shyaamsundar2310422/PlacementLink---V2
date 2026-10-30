from collections import Counter
import math

from models.job_model import get_all_active_jobs_with_match

MATCH_THRESHOLD = 60


def _safe_score(value):
    try:
        score = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(100.0, score)) if math.isfinite(score) else 0.0


def _skill_list(value):
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    return [" ".join(str(item).split()) for item in value if str(item).strip()]


def get_top_recommended_jobs(student_id, limit=5, jobs=None):
    jobs = get_all_active_jobs_with_match(student_id) if jobs is None else jobs
    if not isinstance(jobs, (list, tuple)):
        return []
    eligible_jobs = (job for job in jobs if isinstance(job, dict) and job.get("is_match"))
    return sorted(
        eligible_jobs,
        key=lambda job: (
            bool(job.get("semantic_available")),
            _safe_score(job.get("semantic_score")) if job.get("semantic_available") else -1,
        ),
        reverse=True,
    )[:limit]


def get_missing_skills_analysis(student_id, limit=10, jobs=None):
    jobs = get_all_active_jobs_with_match(student_id) if jobs is None else jobs
    counter = Counter()
    display_names = {}

    for job in jobs or []:
        if not isinstance(job, dict):
            continue
        explainability = job.get("explainability") or {}
        if not isinstance(explainability, dict):
            continue
        for skill in _skill_list(explainability.get("missing_skills")):
            normalized = skill.casefold()
            if normalized:
                display_names.setdefault(normalized, skill)
                counter[normalized] += 1

    return [(display_names[name], count) for name, count in counter.most_common(limit)]


def get_learning_recommendations(student_id, limit=10, jobs=None):
    return get_missing_skills_analysis(student_id, limit=limit, jobs=jobs)


def what_if_analysis(student_id, jobs=None):
    jobs = get_all_active_jobs_with_match(student_id) if jobs is None else jobs
    jobs = jobs if isinstance(jobs, (list, tuple)) else []
    recommendations = get_learning_recommendations(student_id, limit=1, jobs=jobs)

    if not jobs or not recommendations:
        return None

    skill, affected_jobs = recommendations[0]
    skill_key = skill.casefold()
    current_score = max(
        (_safe_score(job.get("match_score")) for job in jobs if isinstance(job, dict)),
        default=0,
    )
    projected_scores = []
    jobs_unlocked = 0

    for job in jobs:
        if not isinstance(job, dict):
            continue
        explainability = job.get("explainability") or {}
        if not isinstance(explainability, dict):
            explainability = {}
        missing_skills = [name.casefold() for name in _skill_list(explainability.get("missing_skills"))]
        if skill_key not in missing_skills:
            continue

        rule_score = _safe_score(job.get("rule_score"))
        semantic_score = _safe_score(job.get("semantic_score"))
        skill_gain = 35 / max(
            1,
            len(_skill_list(explainability.get("matched_skills"))) + len(missing_skills),
        )
        projected_rule_score = min(100, rule_score + skill_gain)
        projected_match = round(0.7 * projected_rule_score + 0.3 * semantic_score)
        projected_scores.append(projected_match)

        gates = job.get("match_gates") or {}
        if not isinstance(gates, dict):
            gates = {}
        non_skill_gates_pass = gates.get("academic_gate", True) and gates.get("department_gate", True)
        if non_skill_gates_pass and _safe_score(job.get("match_score")) < MATCH_THRESHOLD <= projected_match:
            jobs_unlocked += 1

    predicted_score = max([current_score, *projected_scores], default=current_score)
    return {
        "skill": skill,
        "current_score": round(current_score),
        "predicted_score": round(predicted_score),
        "threshold": MATCH_THRESHOLD,
        "unlocks": jobs_unlocked,
        "affected_jobs": affected_jobs,
    }


def get_closest_companies(student_id, limit=10, jobs=None):
    jobs = get_all_active_jobs_with_match(student_id) if jobs is None else jobs
    companies = {}
    for job in jobs or []:
        if not isinstance(job, dict):
            continue
        key = job.get("company_id") or job.get("company_name")
        if key is None:
            continue
        entry = companies.setdefault(key, {
            "company_id": job.get("company_id"),
            "company_name": job.get("company_name"),
            "match_score": 0,
            "job_count": 0,
            "jobs": [],
        })
        entry["job_count"] += 1
        entry["jobs"].append(job)
        if entry["job_count"] == 1 or _safe_score(job.get("match_score")) > _safe_score(entry.get("match_score")):
            explainability = job.get("explainability") or {}
            entry.update({
                "title": job.get("title"),
                "role": job.get("role"),
                "match_score": _safe_score(job.get("match_score")),
                "rule_score": _safe_score(job.get("rule_score")),
                "semantic_score": _safe_score(job.get("semantic_score")),
                "match_reasons": job.get("match_reasons") or {},
                "explainability": explainability if isinstance(explainability, dict) else {},
            })

    ranked = sorted(companies.values(), key=lambda item: _safe_score(item["match_score"]), reverse=True)
    for company in ranked:
        company["jobs"].sort(key=lambda job: _safe_score(job.get("match_score")), reverse=True)
        company["jobs"] = company["jobs"][:3]
    return ranked[:limit]
