"""Celery application (broker and backend come from the environment)."""

from celery import Celery

from .config import Settings

_settings = Settings.from_env()

celery = Celery(
    "disruption_api",
    broker=_settings.celery_broker_url,
    backend=_settings.celery_result_backend,
    include=["disruption_api.tasks"],
)
celery.conf.task_acks_late = True
celery.conf.task_default_retry_delay = 5
# Never accept pickled messages: only JSON can be deserialised from the broker.
celery.conf.task_serializer = "json"
celery.conf.result_serializer = "json"
celery.conf.accept_content = ["json"]
