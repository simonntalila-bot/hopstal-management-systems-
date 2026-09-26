web: gunicorn hms_project.wsgi:application --workers ${WEB_CONCURRENCY:-3} --timeout ${GUNICORN_TIMEOUT:-120} --access-logfile - --error-logfile -
