"""Gunicorn configuration for InvoiceParsed.

    gunicorn -c gunicorn.conf.py wsgi:app

Webhook delivery uses background threads, so a threaded worker class keeps those
alive without needing many processes. Tune workers via the WEB_CONCURRENCY env.
"""
import multiprocessing
import os

bind = os.getenv("BIND", "0.0.0.0:5000")
workers = int(os.getenv("WEB_CONCURRENCY", str(min(4, multiprocessing.cpu_count() * 2 + 1))))
worker_class = os.getenv("WORKER_CLASS", "gthread")
threads = int(os.getenv("THREADS", "4"))
timeout = int(os.getenv("TIMEOUT", "120"))  # OpenAI extraction can be slow
graceful_timeout = 30
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info")
