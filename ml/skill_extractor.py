import re

KNOWN_SKILLS = [
    "Python",
    "Java",
    "C++",
    "JavaScript",
    "HTML",
    "CSS",
    "Flask",
    "Django",
    "React",
    "Node.js",
    "MySQL",
    "MongoDB",
    "Git",
    "Docker",
    "Kubernetes",
    "AWS",
    "GCP",
    "TensorFlow",
    "PyTorch",
    "Pandas",
    "NumPy",
    "Machine Learning",
    "DSA",
    "OOPS",
    "SQL",
    "REST API",
    "REST APIs",
    "Google Cloud Platform"
]


def extract_skills(text):
    """
    Extract known skills from resume text.
    Returns a sorted list of unique skills.
    """

    text_lower = text.lower()

    extracted_skills = []

    for skill in KNOWN_SKILLS:
        pattern = r"\b" + re.escape(skill.lower()) + r"\b"

        if re.search(pattern, text_lower):
            extracted_skills.append(skill)

    return sorted(list(set(extracted_skills)))