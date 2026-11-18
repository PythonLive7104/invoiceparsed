"""Bring the database schema up to date before the app serves traffic.

Run by docker-entrypoint.sh ahead of gunicorn. Handles three situations:

1. Fresh database (no tables at all)
       → `upgrade` builds every table from the migration history.

2. A database that predates migrations — the existing deploy, whose tables were
   built by db.create_all() and which therefore has no alembic_version table
       → `stamp` records it as already at the baseline revision, then later
         migrations apply normally. Without this, `upgrade` would try to CREATE
         TABLE over tables that already exist and abort the deploy.

3. A database already under Alembic
       → `upgrade` applies whatever is new.

Deliberately read-only about data: it never drops or rewrites a table, and case
2 only writes the one-row alembic_version bookkeeping table.
"""
import logging
import sys

from flask_migrate import stamp, upgrade
from sqlalchemy import inspect

from app import create_app
from extensions import db

logging.basicConfig(level=logging.INFO, format="[db-bootstrap] %(message)s")
log = logging.getLogger("db_bootstrap")

# Tables that existed before migrations were introduced. If we find these but no
# alembic_version, we are looking at situation 2 above.
PRE_MIGRATION_TABLES = {"users", "extractions"}


def main() -> int:
    # AUTO_CREATE_TABLES must stay off here: create_all() would build the tables
    # itself and leave Alembic with nothing to do but disagree about the schema.
    app = create_app()
    with app.app_context():
        tables = set(inspect(db.engine).get_table_names())

        if not tables:
            log.info("empty database — building schema from migrations")
            upgrade()
        elif "alembic_version" not in tables:
            if not (PRE_MIGRATION_TABLES & tables):
                log.error(
                    "database has tables %s but no alembic_version, and none of "
                    "the expected pre-migration tables. Refusing to guess — "
                    "inspect it by hand (see DEPLOY.md).",
                    sorted(tables),
                )
                return 1
            log.info("adopting pre-migration database: stamping baseline, then upgrading")
            stamp()
            upgrade()
        else:
            log.info("database already under Alembic — applying any new migrations")
            upgrade()

        log.info("schema is up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
