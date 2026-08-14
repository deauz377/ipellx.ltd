#!/usr/bin/env bash
# Vercel build step. Only collects static files — Vercel has no release phase,
# so migrations are run manually against Supabase (see DEPLOY_VERCEL.md).
set -o errexit

pip install -r requirements.txt

cd 14xlERP_System
python manage.py collectstatic --noinput
