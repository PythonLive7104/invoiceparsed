# InvoiceParsed API — Flask served by gunicorn.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first for better layer caching. psycopg2-binary ships wheels, so
# no system build deps are needed.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Uploaded originals live here; mount a volume at this path to persist them.
RUN mkdir -p /app/uploads
EXPOSE 5000

# The entrypoint applies database migrations, then execs the CMD below. A failed
# migration stops the container rather than serving against a mismatched schema.
# It is Python, not a shell script, so CRLF line endings cannot break it.
ENTRYPOINT ["python", "/app/docker_entrypoint.py"]

# gunicorn.conf.py binds 0.0.0.0:5000 and uses threaded workers (webhook
# delivery runs in background threads).
CMD ["gunicorn", "-c", "gunicorn.conf.py", "wsgi:app"]
