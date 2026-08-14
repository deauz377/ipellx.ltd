"""Vercel serverless entrypoint.

Vercel requires the WSGI callable to live under api/, and the Django project
lives at the repository root, so the root needs to go on sys.path before the
settings module can be imported.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Vercel bundles a function from the files it can statically discover, and a
# path inserted at runtime is invisible to that analysis — vercel.json's
# includeFiles is what actually pulls the project files into the bundle. If
# that ever goes missing, the resulting ImportError says only "no module
# named realkukuERP_System", which does not point at the cause. Fail with
# something that does.
if not (ROOT / 'realkukuERP_System' / 'settings.py').is_file():
    raise RuntimeError(
        f'Django project not found at {ROOT}. '
        f'ROOT contains: {sorted(p.name for p in ROOT.iterdir())!r}. '
        'Check the includeFiles setting in vercel.json.'
    )

sys.path.insert(0, str(ROOT))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'realkukuERP_System.settings')

from django.core.wsgi import get_wsgi_application  # noqa: E402

# Vercel's Python runtime looks for a module-level `app`.
app = get_wsgi_application()
application = app
