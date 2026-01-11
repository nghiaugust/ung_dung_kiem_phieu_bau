"""
Import Celery app so Django loads it when starting
"""
from .celery import app as celery_app

__all__ = ('celery_app',)
