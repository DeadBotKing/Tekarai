"""Django configuration package for the Tekarai backend."""

# Celery discovers this conventional symbol when workers start with
# ``celery -A config worker``. Import is side-effect free (no network access).
from config.celery import app as celeryApp

__all__ = ["celeryApp"]
