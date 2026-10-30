import logging
import os
import time

import requests

_APP_ENV = os.getenv("APP_ENV", "development").lower()
OLLAMA_URL = os.getenv("OLLAMA_URL")
if OLLAMA_URL is None:
    OLLAMA_URL = "" if _APP_ENV == "production" else "http://localhost:11434/api/generate"
MODEL = os.getenv("OLLAMA_MODEL", "gemma3:4b")
logger = logging.getLogger(__name__)


def is_small_talk(question):
    return question.strip().casefold() in {
        "hi", "hello", "hey", "thanks", "thank you", "ok", "okay"
    }


def _compact_history(history, max_chars=6000, max_message_chars=1200):
    if not isinstance(history, (list, tuple)):
        return ""
    kept = []
    remaining = max_chars
    for item in reversed(history[-10:]):
        if not isinstance(item, dict) or remaining <= 0:
            continue
        role = item.get("role", "user")
        role = role if isinstance(role, str) and role in {"user", "assistant"} else "user"
        content = str(item.get("content", ""))[-max_message_chars:]
        content = content[-remaining:]
        if content:
            kept.append(f"{role}: {content}")
            remaining -= len(content)
    return "\n".join(reversed(kept))


def ask_placement_agent(context, history, question):
    question = question.strip() if isinstance(question, str) else ""
    if not question:
        return "Please enter a question so I can help."

    if not OLLAMA_URL.strip():
        logger.info("placement_llm_unavailable category=not_configured")
        return "The Placement AI service is not configured for this deployment. Resume feedback remains available through the local review."

    if is_small_talk(question):
        context = {}
        history = []

    conversation = _compact_history(history)
    context = context if isinstance(context, dict) else {}
    missing_skills = context.get("missing_skills") or []
    top_jobs = context.get("top_jobs") or []
    if not isinstance(missing_skills, (list, tuple)):
        missing_skills = []
    if not isinstance(top_jobs, (list, tuple)):
        top_jobs = []
    compact_context = {
        "missing_skills": missing_skills[:5],
        "top_jobs": [
            {
                "company": job.get("company"),
                "role": job.get("role"),
                "match_score": job.get("match_score"),
            }
            for job in top_jobs[:3]
            if isinstance(job, dict)
        ],
    }
    question_lower = question.casefold()
    if "what if" in question_lower or "if i learn" in question_lower or "add this skill" in question_lower:
        compact_context["what_if"] = context.get("what_if")
    if "company" in question_lower or "employer" in question_lower:
        companies = context.get("companies") or []
        if isinstance(companies, (list, tuple)):
            compact_context["companies"] = companies[:3]
    if context.get("resume_text"):
        compact_context["resume_text"] = str(context["resume_text"])[:2500]
        profile = context.get("profile") or {}
        if not isinstance(profile, dict):
            profile = {}
        compact_context["profile"] = {
            key: profile.get(key)
            for key in ("department", "cgpa", "skills", "projects", "certifications")
            if profile.get(key) is not None
        }

    prompt = f"""You are Placement Intelligence Agent, an AI career advisor.
Use only the student context and conversation history provided. Do not invent facts.
If the question refers to earlier messages, use the conversation history.
Keep the answer professional and under 200 words.

Student Context:
{compact_context}

Conversation History:
{conversation}

Current Question:
{question}
"""
    started = time.monotonic()
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 256},
            },
            timeout=120,
        )
        response.raise_for_status()
        payload = response.json()
        answer = payload.get("response") if isinstance(payload, dict) else None
        if not isinstance(answer, str) or not answer.strip():
            logger.warning(
                "placement_llm_invalid_response elapsed_seconds=%.2f",
                time.monotonic() - started,
            )
            return "The Placement AI returned an unreadable response. Please try again."
        logger.info("placement_llm_success elapsed_seconds=%.2f", time.monotonic() - started)
        return answer.strip()
    except requests.exceptions.Timeout:
        logger.warning("placement_llm_failure category=timeout elapsed_seconds=%.2f", time.monotonic() - started)
        return "The Placement AI is taking longer than expected. Please try again in a moment."
    except requests.exceptions.ConnectionError:
        logger.warning("placement_llm_failure category=connection elapsed_seconds=%.2f", time.monotonic() - started)
        return "The Placement AI is unavailable right now. Please try again later."
    except requests.exceptions.RequestException as error:
        logger.warning(
            "placement_llm_failure category=%s elapsed_seconds=%.2f",
            type(error).__name__,
            time.monotonic() - started,
        )
        return "The Placement AI could not complete that request. Please try again later."
    except (TypeError, ValueError):
        logger.warning("placement_llm_failure category=invalid_payload elapsed_seconds=%.2f", time.monotonic() - started)
        return "The Placement AI returned an unreadable response. Please try again."
    except Exception as error:
        logger.warning(
            "placement_llm_failure category=%s elapsed_seconds=%.2f",
            type(error).__name__,
            time.monotonic() - started,
        )
        return "The Placement AI could not complete that request. Please try again later."
