"""Container entrypoint: migrate the database, then exec the real command.

Used instead of a shell script because this repo is edited on Windows: a .sh
entrypoint depends on a shebang line and an executable bit, and a single CRLF
line ending silently breaks both inside the container. Python source is parsed
rather than shebang-executed, so it is immune to that.

Runs db_bootstrap first and refuses to start the server if it fails - serving
traffic against a schema that does not match the code is worse than being down.
"""
import os
import subprocess
import sys


def main() -> int:
    argv = sys.argv[1:]
    if not argv:
        print("[entrypoint] no command given", file=sys.stderr)
        return 2

    # create_all() must not race the migrations; db_bootstrap sets this too, but
    # being explicit here documents that the deploy's schema is Alembic-owned.
    env = {**os.environ, "AUTO_CREATE_TABLES": "false"}

    print("[entrypoint] bringing database schema up to date...", flush=True)
    result = subprocess.run([sys.executable, "db_bootstrap.py"], env=env)
    if result.returncode != 0:
        print(
            "[entrypoint] migrations failed - refusing to start the server. "
            "See DEPLOY.md for recovering a database that predates migrations.",
            file=sys.stderr,
        )
        return result.returncode

    print("[entrypoint] starting: " + " ".join(argv), flush=True)
    # execvp replaces this process, so gunicorn becomes PID 1 and receives
    # Docker's stop signals directly instead of through a Python parent.
    os.execvp(argv[0], argv)
    return 0  # unreachable: execvp either replaces the process or raises


if __name__ == "__main__":
    sys.exit(main())
