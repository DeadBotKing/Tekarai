"""Settings package for Tekarai.

Default environment is development. Select another environment with:

    DJANGO_SETTINGS_MODULE=config.settings.testing
    DJANGO_SETTINGS_MODULE=config.settings.production
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
