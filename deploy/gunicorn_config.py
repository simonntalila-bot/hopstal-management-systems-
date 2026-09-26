# ---------------------------------------------------------------------------
# Gunicorn configuration for the VPS deployment
#   gunicorn -c deploy/gunicorn_config.py hms_project.wsgi:application
#
# Run under systemd (deploy/systemd/cdms.service), which supplies the real
# values through environment variables. The defaults here are the fallback.
# ---------------------------------------------------------------------------
import multiprocessing
import os

# Socket directory. nginx points at this path (see deploy/nginx).
bind = os.environ.get("GUNICORN_BIND", "unix:/run/cdms/gunicorn.sock")

# 2 x CPU cores + 1, capped so a small VPS is not oversubscribed.
workers = int(
    os.environ.get(
        "WEB_CONCURRENCY",
        min((multiprocessing.cpu_count() * 2) + 1, 5),
    )
)

# Recycle workers to contain any memory growth.
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", "1000"))
max_requests_jitter = int(os.environ.get("GUNICORN_MAX_REQUESTS_JITTER", "100"))

# 120s suits report generation; keep it >= nginx proxy_read_timeout.
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))
graceful_timeout = 30
keepalive = 5

# Logs to systemd journal when running under systemd.
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")

# Do not advertise the exact framework version.
proc_name = "cdms"

# Large uploads stream through; skip the temporary-file buffer where possible.
tmp_upload_dir = "/dev/shm"

forwarded_allow_ips = os.environ.get("GUNICORN_FORWARDED_ALLOW_IPS", "127.0.0.1")
