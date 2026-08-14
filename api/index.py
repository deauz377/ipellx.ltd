"""Vercel serverless entrypoint.

Vercel requires the WSGI callable to live under api/, but the Django project
sits one directory down in 14xlERP_System/, so its parent has to go on the
path before the settings module can be imported.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT_DIR = ROOT / '14xlERP_System'

# Vercel bundles a function from the files it can statically discover, and a
# path inserted at runtime is invisible to that analysis. If vercel.json's
# includeFiles is missing or wrong the directory simply is not there, and the
# resulting ImportError says only "no module named realkukuERP_System", which
# does not point at the cause. Fail with something that does.
if not (PROJECT_DIR / 'realkukuERP_System' / 'settings.py').is_file():
    raise RuntimeError(
        f'Django project not found at {PROJECT_DIR}. '
        f'ROOT contains: {sorted(p.name for p in ROOT.iterdir())!r}. '
        'Check the includeFiles setting in vercel.json.'
    )

sys.path.insert(0, str(PROJECT_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'realkukuERP_System.settings')

from django.core.wsgi import get_wsgi_application  # noqa: E402

# Vercel's Python runtime looks for a module-level `app`.
app = get_wsgi_application()
application = app
