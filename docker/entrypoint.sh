#!/bin/sh
# Backend container entrypoint: provide a SECRET_KEY, prepare the database when asked, then run the command.
set -e

# Without SECRET_KEY, generate one on first start and keep it in the shared data volume, so sessions and
# signed download links survive restarts and every app container uses the same key.
if [ -z "$SECRET_KEY" ]; then
    key_file=/app/data/secret_key
    if [ ! -s "$key_file" ]; then
        umask 077
        python -c 'import secrets; print(secrets.token_urlsafe(50))' > "$key_file"
    fi
    SECRET_KEY=$(cat "$key_file")
    export SECRET_KEY
fi

# Only the web container sets DIAGNOSEIT_INIT=1; the workers wait until it is healthy.
if [ "${DIAGNOSEIT_INIT:-0}" = "1" ]; then
    uv run python manage.py migrate --noinput
    uv run python manage.py populate_lab_tests
    uv run python manage.py collectstatic --noinput
    if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
        uv run python manage.py shell -c "
import os
from django.contrib.auth import get_user_model
User = get_user_model()
name = os.environ['DJANGO_SUPERUSER_USERNAME']
if not User.objects.filter(username=name).exists():
    User.objects.create_superuser(name, os.environ.get('DJANGO_SUPERUSER_EMAIL', ''), os.environ['DJANGO_SUPERUSER_PASSWORD'])
    print(f'Created administrator {name}')
"
    fi
fi

exec "$@"
