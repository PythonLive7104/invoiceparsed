"""Shared Flask extensions, initialized in the app factory."""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Rate limiter. Keyed by client IP; storage + default limits are configured from
# the app config in create_app(). Use a Redis storage URI in production so limits
# are shared across workers.
limiter = Limiter(key_func=get_remote_address)
