"""Shared Flask extensions, initialized in the app factory."""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Schema versioning (Alembic). Every schema change from here on ships as a
# migration: `flask db migrate -m "..."` to generate, `flask db upgrade` to
# apply. The deploy runs `flask db upgrade` before gunicorn starts.
migrate = Migrate()

# Rate limiter. Keyed by client IP; storage + default limits are configured from
# the app config in create_app(). Use a Redis storage URI in production so limits
# are shared across workers.
limiter = Limiter(key_func=get_remote_address)
