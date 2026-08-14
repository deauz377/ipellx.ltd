"""Vercel serverless entrypoint.

Vercel requires the WSGI callable to live under api/, but the Django project
sits one directory down in 14xlERP_System/, so its parent has to go on the
path before the settings module can be imported.
"""

import os
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent / '14xlERP_System'
sys.path.insert(0, str(PROJECT_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'realkukuERP_System.settings')

from django.core.wsgi import get_wsgi_application  # noqa: E402

# Vercel's Python runtime looks for a module-level `app`.
app = get_wsgi_application()
application = app
