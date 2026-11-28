"""The background worker process.

    python worker.py              # both queues, documents first
    python worker.py bulk         # only the slow queue

Run as its own container (see docker-compose.yml). Keeping it separate from
the API is the point of F4: a sixty-page statement being read by a model has
no business occupying a thread that is supposed to be answering HTTP.

**Queue order matters.** Listed as `documents bulk`, RQ drains `documents`
first and only looks at `bulk` when the first is empty — so a single invoice
uploaded behind a long statement is still answered in seconds. Running one
worker per queue would be better still on a bigger box; on a 2 GB VPS one
worker that prioritises correctly is the right trade.

The Flask app is built once, here, and handed to every job. Building it
per-job would re-read config, re-create the engine and re-register blueprints
for every document.
"""
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("worker")


def main() -> int:
    from jobs import QUEUES, queue_url

    url = queue_url()
    if not url:
        logger.error(
            "JOB_QUEUE_URL is not set, so there is no queue to work. The API "
            "will run extractions inline; this process has nothing to do."
        )
        return 1

    try:
        from redis import Redis
        from rq import Queue, Worker
    except ImportError:
        logger.error("rq and redis must be installed to run a worker")
        return 1

    requested = [name for name in sys.argv[1:] if name in QUEUES]
    names = requested or list(QUEUES)

    connection = Redis.from_url(url)
    # Fail loudly and immediately rather than idling against a dead Redis:
    # a worker that looks healthy and is doing nothing is worse than one that
    # restarts.
    connection.ping()

    # One app for the whole process, passed into each job.
    from app import create_app
    from config import Config

    app = create_app(Config)

    # Anything left in `processing` from a previous life is swept before the
    # first new job is taken. This is the acceptance criterion: no row stays
    # in `processing` after a worker restart.
    from extraction_jobs import sweep_stuck

    with app.app_context():
        swept = sweep_stuck()
        if swept:
            logger.warning("swept %d extraction(s) abandoned by a previous "
                           "worker", swept)

    queues = [Queue(name, connection=connection) for name in names]
    logger.info("worker starting on queues: %s", ", ".join(names))

    worker = Worker(queues, connection=connection)
    worker.work(with_scheduler=True)
    return 0


if __name__ == "__main__":
    # The job function resolves as "extraction_jobs.run_extraction", so the
    # worker's working directory has to be the backend package root. The
    # container sets this; the guard catches a hand-run from the wrong place.
    if not os.path.exists("extraction_jobs.py"):
        logger.error("run this from the backend directory")
        sys.exit(1)
    sys.exit(main())
