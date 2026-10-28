# GreenSearch live backend for Cloud Run (and any container host).
# Python standard library only, no dependencies to install.
# The server serves the website at / and the API at /api/chat, so one
# container is the whole demo: no separate frontend host, no CORS split
# once GREENSEARCH_BACKEND_ORIGIN includes the Cloud Run URL.
FROM python:3.12-slim
WORKDIR /app
# Copy only what the server needs to run. Tests, scripts, results and
# docs are not needed at runtime and are left out to keep the image small.
COPY greensearch/ ./greensearch/
COPY server/ ./server/
COPY website/ ./website/
ENV PYTHONUNBUFFERED=1
# Cloud Run sets $PORT (default 8080). The server reads $PORT when
# --port is not given, so only the bind address needs to be set here:
# 0.0.0.0, not the local-only default 127.0.0.1.
CMD ["python3", "server/app.py", "--host", "0.0.0.0"]
