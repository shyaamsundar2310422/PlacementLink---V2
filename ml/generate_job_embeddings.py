import sys
import os

sys.path.append(
    os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )
)

from models.job_model import get_all_jobs
from ml.embedding_service import generate_embedding, embedding_to_json, embedding_matches_source
from ml.semantic_matcher import build_job_text
from database.db import get_db_connection



jobs = get_all_jobs()

connection = get_db_connection()

with connection.cursor() as cursor:

    for job in jobs:

        job_text = build_job_text(job)
        if embedding_matches_source(job.get("job_embedding"), job_text):
            continue

        embedding = generate_embedding(job_text)

        cursor.execute(
            """
            UPDATE jobs
            SET job_embedding=%s
            WHERE id=%s
            """,
            (
                embedding_to_json(embedding, source_text=job_text),
                job["id"]
            )
        )

connection.commit()
connection.close()

print("Done")
