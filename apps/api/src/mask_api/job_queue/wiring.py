from functools import lru_cache

from mask_api.database import get_session_factory
from mask_api.job_queue.repository import SQLAlchemyJobQueue


@lru_cache
def get_job_queue() -> SQLAlchemyJobQueue:
    return SQLAlchemyJobQueue(get_session_factory())
