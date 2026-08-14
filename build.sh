#!/usr/bin/env bash
# Build step for Railway / Render. Exit on any failure so a broken build never
# gets promoted to a running service.
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --noinput
python manage.py migrate --noinput
