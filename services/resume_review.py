import json
import re
from collections import Counter
import hashlib
import math

from services.placement_llm import ask_placement_agent
from ml.skill_extractor import extract_skills
# Cache for AI resume reviews
resume_review_cache = {}

def _clamp(value, minimum, maximum, default):
    try:
        number = float(value)
        return max(minimum, min(number, maximum)) if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _finite_number(value):
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _as_list(value, fallback):
    if isinstance(value, list):
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        return cleaned or fallback
    if isinstance(value, str):
        cleaned = [
            item.strip(" -\t")
            for item in value.splitlines()
            if item.strip(" -\t")
        ]
        return cleaned or fallback
    return fallback


def _has_list_entries(value):
    if isinstance(value, list):
        return all(isinstance(item, str) for item in value) and any(item.strip() for item in value)
    if isinstance(value, str):
        return bool(value.strip())
    return False


def _extract_json(response_text):
    if not response_text:
        return None

    text = response_text.strip()
    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced_match:
        text = fenced_match.group(1)
    else:
        object_match = re.search(r"\{.*\}", text, re.DOTALL)
        if object_match:
            text = object_match.group(0)

    try:
        parsed = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None

    return parsed if isinstance(parsed, dict) else None


def _fallback_review(resume_text, profile):
    profile = profile or {}
    normalized_resume = resume_text.lower()
    skills = list(dict.fromkeys(
        [item.strip() for item in (profile.get("skills") or "").split(",") if item.strip()]
        + extract_skills(resume_text)
    ))
    skills_feedback = (
        [f"Recognized skills: {', '.join(skills[:8])}. Keep the skills section focused on tools used in your target roles."]
        if skills
        else ["No recognized technical skills were found. Add verified skills and give brief evidence of how you used them."]
    )
    projects = [item.strip() for item in (profile.get("projects") or "").split(",") if item.strip()]
    certifications = [
        item.strip()
        for item in (profile.get("certifications") or "").split(",")
        if item.strip()
    ]
    has_metrics = bool(re.search(r"\b\d+(?:\.\d+)?(?:%|\+|x)?\b", resume_text))
    has_contact = bool(re.search(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", normalized_resume))
    has_links = "github.com" in normalized_resume or "linkedin.com" in normalized_resume
    has_summary = any(term in normalized_resume for term in ("summary", "objective", "profile"))
    has_education = "education" in normalized_resume
    has_experience_section = bool(re.search(
        r"\b(experience|employment|internship|work history)\b", normalized_resume
    ))
    experience_feedback = (
        ["Experience section detected. Add dates, responsibilities, and measurable outcomes for each role or internship."]
        if has_experience_section
        else ["No experience or internship section detected. Add relevant work, internship, volunteer, or leadership experience, even if it is brief."]
    )
    project_feedback = (
        [f"Profile lists {len(projects)} project entr{'y' if len(projects) == 1 else 'ies'}. Describe your individual contribution and the result for each."]
        if projects
        else ["Add one or two relevant projects with your contribution, tools used, and a measurable result."]
    )

    score = 4.0
    score += min(len(skills), 8) * 0.25
    score += min(len(projects), 3) * 0.6
    score += min(len(certifications), 2) * 0.25
    score += 0.5 if has_metrics else 0
    score += 0.35 if has_contact else 0
    score += 0.35 if has_links else 0
    score += 0.3 if has_summary else 0
    score += 0.3 if has_education else 0
    score = round(_clamp(score, 1, 10, 6.0), 1)

    ats_score = round(_clamp(score * 9 + (5 if has_metrics else 0), 20, 98, 60))

    strengths = []
    if skills:
        strengths.append(f"Technical skill coverage includes {', '.join(skills[:5])}.")
    if projects:
        strengths.append(f"Includes {len(projects)} project entr{'y' if len(projects) == 1 else 'ies'}.")
    if has_metrics:
        strengths.append("Uses measurable details that help recruiters assess impact.")
    if has_links:
        strengths.append("Provides a professional or project portfolio link.")
    if not strengths:
        strengths.append("The uploaded resume provides a foundation that can be refined.")

    weaknesses = []
    suggestions = []
    if not has_metrics:
        weaknesses.append("Achievements are not consistently quantified.")
        suggestions.append("Add measurable impact such as percentages, scale, speed, or outcomes.")
    if not has_summary:
        weaknesses.append("A focused professional summary is missing or unclear.")
        suggestions.append("Add a concise summary tailored to the roles you are targeting.")
    if not has_experience_section:
        weaknesses.append("Work or internship experience is not clearly labeled.")
        suggestions.append("Add an Experience section; include internships, relevant volunteering, or leadership if you have no formal work history.")
    if not has_links:
        weaknesses.append("No GitHub or LinkedIn link was detected.")
        suggestions.append("Include relevant GitHub and LinkedIn links in the contact section.")
    if len(projects) < 2:
        weaknesses.append("Project evidence is limited for technical screening.")
        suggestions.append("Add one role-relevant project with technologies and measurable results.")
    if len(skills) < 5:
        weaknesses.append("The technical keyword coverage may be too narrow for ATS screening.")
        suggestions.append("Add verified role-specific skills that appear in target job descriptions.")

    impression = (
        "Strong candidate presentation with clear evidence for technical roles."
        if score >= 8
        else "Promising candidate profile that would benefit from clearer impact and role targeting."
        if score >= 6
        else "The resume needs stronger evidence, keywords, and structure before recruiter screening."
    )

    return {
        "overall_score": score,
        "ats_score": ats_score,
        "strengths": strengths,
        "skills_feedback": skills_feedback,
        "experience": experience_feedback,
        "projects_feedback": project_feedback,
        "weaknesses": weaknesses or ["No critical weaknesses were detected from the available profile data."],
        "suggestions": suggestions or ["Tailor the resume keywords and achievements for each target role."],
        "recruiter_impression": impression,
        "estimated_score": round(min(10, score + max(0.4, len(suggestions) * 0.2)), 1),
    }


def review_resume(resume_text, profile=None):
    if not resume_text or not resume_text.strip():
        return None
    profile = profile or {}
    cache_material = json.dumps(
        {"resume": resume_text, "profile": {
            key: profile.get(key) for key in ("department", "cgpa", "skills", "projects", "certifications")
        }},
        sort_keys=True,
        default=str,
    )
    resume_hash = hashlib.sha256(cache_material.encode("utf-8")).hexdigest()

    # Return cached review if available
    if resume_hash in resume_review_cache:
        return resume_review_cache[resume_hash]

    fallback = _fallback_review(resume_text, profile)

    # Limit resume size for faster LLM inference
    resume_text = resume_text[:2000]
    context = {
        "resume_text": resume_text,
        "profile": {
            "department": (profile or {}).get("department"),
            "cgpa": (profile or {}).get("cgpa"),
            "skills": (profile or {}).get("skills"),
            "projects": (profile or {}).get("projects"),
            "certifications": (profile or {}).get("certifications"),
        },
    }
    question = """
    Review this resume.

    Return ONLY valid JSON with:

    - overall_score (1-10)
    - ats_score (0-100)
    - strengths
    - skills_feedback
    - experience
    - projects_feedback
    - weaknesses
    - suggestions
    - recruiter_impression
    - estimated_score

    Keep strengths, weaknesses and suggestions concise (maximum 5 points each).

    Do not explain.

    Return JSON only.
    """

    parsed = None
    try:
        raw_response = ask_placement_agent(context, [], question)
        parsed = _extract_json(raw_response)
    except Exception as error:
        print(f"[ResumeReview] request_failed category={type(error).__name__}")

    required_fields = {
        "overall_score", "ats_score", "strengths", "skills_feedback", "experience", "projects_feedback", "weaknesses", "suggestions",
        "recruiter_impression", "estimated_score",
    }
    valid_scores = bool(parsed) and all(
        _finite_number(parsed.get(field))
        for field in ("overall_score", "ats_score", "estimated_score")
    )
    valid_lists = bool(parsed) and all(
        _has_list_entries(parsed.get(field))
        for field in ("strengths", "skills_feedback", "experience", "projects_feedback", "weaknesses", "suggestions")
    )
    valid_impression = bool(parsed) and isinstance(parsed.get("recruiter_impression"), str) and bool(parsed["recruiter_impression"].strip())
    if (
        not parsed
        or not required_fields.issubset(parsed)
        or not valid_scores
        or not valid_lists
        or not valid_impression
    ):
        result = dict(fallback)
        result["service_warning"] = (
            "Live AI analysis was unavailable or returned incomplete output; "
            "this is a local heuristic review."
        )
        result["analysis_source"] = "local_fallback"
        resume_review_cache[resume_hash] = result
        return result

    overall_score = round(
        _clamp(parsed.get("overall_score"), 1, 10, fallback["overall_score"]),
        1,
    )
    ats_score = round(_clamp(parsed.get("ats_score"), 0, 100, fallback["ats_score"]))
    estimated_score = round(
        _clamp(parsed.get("estimated_score"), overall_score, 10, fallback["estimated_score"]),
        1,
    )
    result = {
        "overall_score": overall_score,
        "ats_score": ats_score,
        "strengths": _as_list(parsed.get("strengths"), fallback["strengths"]),
        "skills_feedback": _as_list(parsed.get("skills_feedback"), fallback["skills_feedback"]),
        "experience": _as_list(parsed.get("experience"), fallback["experience"]),
        "projects_feedback": _as_list(parsed.get("projects_feedback"), fallback["projects_feedback"]),
        "weaknesses": _as_list(parsed.get("weaknesses"), fallback["weaknesses"]),
        "suggestions": _as_list(parsed.get("suggestions"), fallback["suggestions"]),
        "recruiter_impression": str(
            parsed.get("recruiter_impression") or fallback["recruiter_impression"]
        ).strip(),
        "estimated_score": estimated_score,
        "service_warning": "",
        "analysis_source": "live_ai",
    }

    resume_review_cache[resume_hash] = result

    return result


def build_career_plan(jobs, readiness):
    missing_counter = Counter()
    for job in jobs or []:
        explainability = job.get("explainability") or {}
        for skill in explainability.get("missing_skills") or []:
            normalized = str(skill).strip()
            if normalized:
                missing_counter[normalized] += 1

    priority_skills = [skill for skill, _ in missing_counter.most_common(8)]
    top_role = (jobs or [{}])[0].get("title") or "target role"
    fallback_tasks = [
        f"Build one portfolio project aligned with {top_role}",
        "Practice DSA and role-specific technical questions",
        "Improve ATS keywords and quantified resume achievements",
        "Complete two mock interviews and review feedback",
    ]
    tasks = priority_skills + fallback_tasks
    weeks = []
    for index in range(4):
        week_tasks = tasks[index * 2:(index + 1) * 2]
        if not week_tasks:
            week_tasks = [fallback_tasks[index]]
        weeks.append({"label": f"Week {index + 1}", "tasks": week_tasks})

    current_score = int((readiness or {}).get("score") or 0)
    improvement = min(15, 4 + len(priority_skills) * 2)
    return {
        "current_readiness": current_score,
        "estimated_readiness": min(100, current_score + improvement),
        "weeks": weeks,
        "priority_skills": priority_skills,
    }


def build_job_gap_analysis(job):
    explainability = job.get("explainability") or {}
    matched_skills = list(explainability.get("matched_skills") or [])
    missing_skills = list(explainability.get("missing_skills") or [])
    current_score = int(job.get("match_score") or 0)
    total_skills = max(1, len(matched_skills) + len(missing_skills))
    gain_per_skill = max(2, round(24.5 / total_skills))

    scenarios = []
    selected_skills = []
    for skill in missing_skills[:3]:
        selected_skills.append(skill)
        projected_score = min(100, current_score + gain_per_skill * len(selected_skills))
        scenarios.append({
            "skills": list(selected_skills),
            "score": projected_score,
        })

    if missing_skills:
        readable_skills = ", ".join(str(skill) for skill in missing_skills[:3])
        recommendation = (
            f"Prioritize {readable_skills}. Demonstrating these skills in projects and "
            f"your resume would improve alignment with this role's requirements."
        )
    else:
        recommendation = (
            "Your profile covers the detected required skills. Focus on stronger project "
            "evidence, quantified impact, and interview preparation."
        )

    return {
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "current_score": current_score,
        "scenarios": scenarios,
        "recommendation": recommendation,
    }

