import json
import math

from ml.embedding_service import embedding_matches_source, generate_embedding, json_to_embedding

EXPECTED_EMBEDDING_DIMENSION = 384


def build_job_text(job):
    """Convert a job record into a semantic document."""
    document = f"""
    Job Title: {job.get('title', '')}

    Role:
    {job.get('role', '')}

    Required Skills:
    {job.get('required_skills', '')}

    Eligibility Criteria:
    {job.get('eligibility_criteria', '')}

    Allowed Departments:
    {job.get('allowed_departments', '')}
    """
    jd_text = (job.get('jd_text') or '').strip()
    if jd_text:
        document += f"\n\nJob Description:\n{jd_text}"
    return document


def build_profile_text(profile):
    """Build semantic text from the student's resume and saved profile fields."""
    profile = profile or {}
    parts = [
        ("Resume", profile.get("resume_text")),
        ("Skills", profile.get("skills")),
        ("Projects", profile.get("projects")),
        ("Certifications", profile.get("certifications")),
        ("Department", profile.get("department")),
    ]
    return "\n\n".join(
        f"{label}: {value.strip()}" for label, value in parts
        if isinstance(value, str) and value.strip()
    )


def _vector(value):
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, (list, tuple)) or not value:
        return None
    try:
        vector = [float(item) for item in value]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(item) for item in vector):
        return None
    return vector


def has_compatible_resume_job_embeddings(profile, job):
    """Return whether semantic similarity can be computed from stored vectors."""
    profile = profile or {}
    job = job or {}
    profile_text = build_profile_text(profile).strip()
    resume_vector = _vector(json_to_embedding(profile.get("resume_embedding")))
    job_vector = _vector(json_to_embedding(job.get("job_embedding")))
    return bool(
        profile_text
        and bool((profile.get("resume_text") or "").strip())
        and bool(profile.get("resume_url"))
        and bool((job.get("jd_text") or "").strip())
        and bool(job.get("jd_file_url"))
        and embedding_matches_source(profile.get("resume_embedding"), profile_text)
        and embedding_matches_source(job.get("job_embedding"), build_job_text(job))
        and _has_valid_norm(resume_vector)
        and _has_valid_norm(job_vector)
    )


def _has_valid_norm(vector):
    return bool(
        vector
        and len(vector) == EXPECTED_EMBEDDING_DIMENSION
        and sum(value * value for value in vector) > 0
    )


def _cosine_score(left, right):
    """Map valid 384-D cosine similarity from [-1, 1] linearly to [0, 100]."""
    left = _vector(left)
    right = _vector(right)
    if (
        left is None
        or right is None
        or len(left) != len(right)
        or len(left) != EXPECTED_EMBEDDING_DIMENSION
    ):
        return None
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return None
    similarity = sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)
    if not math.isfinite(similarity):
        return None
    # Convert cosine's [-1, 1] range linearly to a 0-100 score.
    return round((max(-1.0, min(1.0, similarity)) + 1.0) * 50.0, 2)


def calculate_semantic_score(resume_text, job_text):
    if not resume_text or not job_text:
        return None
    try:
        resume_embedding = generate_embedding(resume_text)
        job_embedding = generate_embedding(job_text)
        return _cosine_score(resume_embedding, job_embedding)
    except Exception:
        return None


def calculate_resume_job_score(profile, job):
    try:
        resume_embedding = json_to_embedding((profile or {}).get("resume_embedding"))
        job_embedding = json_to_embedding((job or {}).get("job_embedding"))
        if not has_compatible_resume_job_embeddings(profile, job):
            return None
        return _cosine_score(resume_embedding, job_embedding)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
