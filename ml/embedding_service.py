import json
import math
import os
import hashlib
from threading import Lock

_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_model = None
_model_lock = Lock()
_model_load_error = None


def _get_model():
    global _model, _model_load_error

    if _model is None:
        with _model_lock:
            if _model_load_error is not None:
                raise RuntimeError("SentenceTransformer model is unavailable") from _model_load_error
            if _model is None:
                try:
                    # Prefer the installed model; do not retry Hub downloads per job.
                    os.environ.setdefault("HF_HUB_OFFLINE", "1")
                    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
                    from sentence_transformers import SentenceTransformer

                    _model = SentenceTransformer(_MODEL_NAME)
                except Exception as error:
                    _model_load_error = error
                    raise

    return _model


def generate_embedding(text):
    if not text:
        return None

    return _get_model().encode(
        text,
        normalize_embeddings=True,
    )


def embedding_to_json(embedding, source_text=None):
    if embedding is None:
        return None

    values = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
    if source_text is None:
        return json.dumps(values)
    return json.dumps({
        "model": _MODEL_NAME,
        "source_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        "vector": values,
    })


def embedding_matches_source(embedding_json, source_text):
    if not embedding_json or not source_text:
        return False
    try:
        payload = json.loads(embedding_json) if isinstance(embedding_json, (str, bytes)) else embedding_json
        return bool(
            isinstance(payload, dict)
            and payload.get("model") == _MODEL_NAME
            and payload.get("source_sha256") == hashlib.sha256(source_text.encode("utf-8")).hexdigest()
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        return False


def json_to_embedding(embedding_json):
    if not embedding_json:
        return None
    try:
        embedding = json.loads(embedding_json) if isinstance(embedding_json, str) else embedding_json
        if isinstance(embedding, dict):
            embedding = embedding.get("vector")
        if not isinstance(embedding, list) or not embedding:
            return None
        values = [float(value) for value in embedding]
        if not all(math.isfinite(value) for value in values):
            return None
        return values
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
