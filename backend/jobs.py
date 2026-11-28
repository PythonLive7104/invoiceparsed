"""The background job queue.

Extraction used to run inside the HTTP request. A sixty-page bank statement
held a gunicorn worker for minutes, and if the client gave up or the process
restarted mid-call the row sat in `processing` for ever with nothing left to
finish it.

Five rules shape this module.

1. **The work always leaves the request.** Even when a caller asks to wait for
   the result, the extraction itself runs on a worker and the request thread
   merely polls. A parked thread holding no OpenAI connection is cheap; a
   thread doing the work is not, and if it dies the work dies with it.

2. **The queue carries an id, never a document.** Pages are already on disk
   before the job is enqueued, so the worker reloads them. A queue is a
   message bus, not a file store, and putting ten megabytes of PDF through
   Redis would make Redis the most fragile part of the system.

3. **Two queues, so one slow document cannot starve the rest.** A sixty-page
   statement and a one-page invoice do not belong in the same line.

4. **Re-enqueuing is harmless.** The job id IS the extraction id, so a retry,
   a double-submit or a client that reconnects cannot produce two workers
   racing over one row — and the job itself re-checks the row's status before
   doing anything.

5. **No queue is a working configuration.** Where Redis is absent or
   unreachable the work runs inline, exactly as it did before. A product that
   stops extracting because a cache is down has traded one failure for a
   worse one.
"""
import logging
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Single documents must stay responsive; bulk is where the long ones go.
QUEUE_DOCUMENTS = "documents"
QUEUE_BULK = "bulk"
QUEUES = (QUEUE_DOCUMENTS, QUEUE_BULK)

# Per-job wall-clock limits. A job that exceeds its limit is killed by the
# worker and the row is failed, rather than being left to run for ever.
TIMEOUTS = {
    QUEUE_DOCUMENTS: 240,   # 4 minutes: a slow invoice, not a stuck one
    QUEUE_BULK: 1200,       # 20 minutes: a long statement is legitimately slow
}

# Retries, with backoff. Extraction fails for two very different reasons - a
# transient upstream hiccup, which a retry fixes, and an unreadable document,
# which it never will. Three attempts spread over ten minutes covers the first
# without hammering the model provider over the second.
MAX_ATTEMPTS = 3
RETRY_INTERVALS = [20, 120, 420]

# How long after a job was queued we stop believing it is still running. Past
# this the sweeper fails the row: see `stuck_cutoff`.
SWEEP_GRACE = timedelta(minutes=10)


def queue_url() -> str:
    """Where the queue lives, or "" for inline execution.

    Deliberately a separate setting from `RATELIMIT_STORAGE_URI` and pointed at
    a different Redis database in the compose file: flushing rate-limit
    counters must not also throw away a queue of real work.
    """
    return (os.getenv("JOB_QUEUE_URL") or "").strip()


def is_enabled() -> bool:
    return bool(queue_url())


def _connection():
    """A Redis connection, or None if the library or the server is missing."""
    url = queue_url()
    if not url:
        return None
    try:
        from redis import Redis

        connection = Redis.from_url(url, socket_connect_timeout=3,
                                    socket_timeout=5)
        connection.ping()
        return connection
    except Exception:
        # Logged, never raised: rule 5. The caller falls back to inline.
        logger.warning("job queue unreachable at %s; running inline",
                       url.split("@")[-1], exc_info=True)
        return None


def get_queue(name: str = QUEUE_DOCUMENTS):
    """An RQ queue, or None when the queue is unavailable."""
    if name not in QUEUES:
        name = QUEUE_DOCUMENTS
    connection = _connection()
    if connection is None:
        return None
    try:
        from rq import Queue

        return Queue(name, connection=connection,
                     default_timeout=TIMEOUTS.get(name, 300))
    except ImportError:
        logger.warning("rq is not installed; running inline")
        return None


def queue_for(doc_type: str, page_count: int = 1) -> str:
    """Which line this document joins.

    Statements and anything multi-page go to `bulk`. The rule is about
    expected duration rather than document type as such, but those are the two
    signals available before the work starts — and guessing wrong only costs
    the job a slower queue, never correctness.
    """
    if doc_type == "statement" or page_count > 1:
        return QUEUE_BULK
    return QUEUE_DOCUMENTS


def job_name(extraction_id: str) -> str:
    """The queue's name for one extraction's job."""
    return f"extract-{extraction_id}"


# Statuses meaning "somebody is already dealing with this".
LIVE_STATES = ("queued", "started", "deferred", "scheduled")


def _already_queued(name: str, queue) -> bool:
    """Is this job already waiting or running?

    Returns False when the answer cannot be determined: enqueuing a duplicate
    is recoverable (the job itself refuses to extract a finished row), whereas
    wrongly skipping leaves an upload that nothing ever processes.
    """
    try:
        from rq.job import Job

        return Job.fetch(name, connection=queue.connection).get_status()             in LIVE_STATES
    except Exception:
        return False


def enqueue_extraction(extraction_id: str, *, doc_type: str,
                       page_count: int = 1) -> str | None:
    """Queue an extraction. Returns the job id, or None to run inline.

    The job id IS the extraction id (rule 4), and an id already queued or
    running is left alone rather than queued a second time.

    RQ does NOT deduplicate by id on its own: enqueuing the same id twice
    overwrites the job hash but pushes the id onto the queue list again, so
    the work would be picked up twice. The check below is what prevents that,
    and `run_extraction` re-reading the row is the backstop for the race the
    check cannot close.

    The prefix is joined with a hyphen, not a colon: RQ reserves ":" for its
    own key namespacing and rejects an id containing one. It raises at enqueue
    time, which the fallback below would quietly turn into "runs inline for
    ever" - so this is deliberate rather than cosmetic.
    """
    name = queue_for(doc_type, page_count)
    queue = get_queue(name)
    if queue is None:
        return None

    name_for_job = job_name(extraction_id)
    if _already_queued(name_for_job, queue):
        return name_for_job

    try:
        from rq import Retry

        queue.enqueue(
            "extraction_jobs.run_extraction",
            extraction_id,
            job_id=job_name(extraction_id),
            job_timeout=TIMEOUTS.get(name, 300),
            retry=Retry(max=MAX_ATTEMPTS, interval=RETRY_INTERVALS),
            # Keep finished jobs briefly so a poll that arrives just after
            # completion can still see the outcome, and failures long enough
            # to be looked at.
            result_ttl=600,
            failure_ttl=86400,
            description=f"{doc_type} extraction {extraction_id}",
        )
        return job_name(extraction_id)
    except Exception:
        logger.exception("could not enqueue extraction %s", extraction_id)
        return None


def job_state(job_id: str) -> str | None:
    """RQ's view of a job: queued, started, finished, failed… or None.

    Only ever advisory. The truth about an extraction is the row's own status,
    because the row outlives the job registry — which is exactly why the
    sweeper exists.
    """
    if not job_id:
        return None
    connection = _connection()
    if connection is None:
        return None
    try:
        from rq.job import Job

        return Job.fetch(job_id, connection=connection).get_status()
    except Exception:
        return None


def stuck_cutoff(now=None) -> datetime:
    """Queued before this and still `processing` means nobody is coming.

    The longest a legitimate job can take (the bulk timeout) plus the retry
    schedule plus a grace period. Anything older has outlived every way it
    could still be alive.
    """
    now = now or datetime.utcnow()
    longest = timedelta(seconds=TIMEOUTS[QUEUE_BULK] * MAX_ATTEMPTS
                        + sum(RETRY_INTERVALS))
    return now - longest - SWEEP_GRACE
