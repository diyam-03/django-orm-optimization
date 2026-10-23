#!/usr/bin/env bash
# Render runs this on every deploy. Free Render plans have no shell, so data loading lives here too.
set -o errexit
pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate --noinput
# Idempotent: safe on every deploy. Falls back to the bundled sample if the API is unreachable.
python manage.py load_countries || python manage.py load_countries --offline
