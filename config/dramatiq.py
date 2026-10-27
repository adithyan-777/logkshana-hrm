"""Worker entry module for the dramatiq CLI.

Run with:  dramatiq config.dramatiq --processes N --threads M

``config.broker`` has already configured the global broker (imported
through settings); this module only sets Django up and imports every
tasks module so its actors register with the broker.
"""

import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import attendance.tasks  # noqa: E402,F401  registers attendance cron actors
import employees.tasks  # noqa: E402,F401  registers device-user actors
