release: cd 14xlERP_System && python manage.py migrate --noinput
web: cd 14xlERP_System && gunicorn realkukuERP_System.wsgi:application --bind 0.0.0.0:$PORT --workers 3 --timeout 120
