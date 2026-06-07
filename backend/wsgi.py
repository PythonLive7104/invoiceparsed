"""WSGI entrypoint for production servers (gunicorn, uWSGI, etc.).

    gunicorn -c gunicorn.conf.py wsgi:app
"""
from app import create_app

app = create_app()
