"""The background job queue (F4).

F4's acceptance criterion is two sentences, and both are load-bearing:

    `processing` is always truthful — no row stays in it after a worker
    restart, and a failed job never consumes plan quota.

So the weight here is on the ways `processing` lies: a worker killed mid-job,
a queue that loses its contents, a job that never ran. Plus the things that
make retries safe — idempotency, pages reloaded from disk, a row that refuses
to be extracted twice.

The real RQ queue is exercised through fakeredis rather than only the inline
fallback, because "it works inline" would say nothing about the path that
actually runs in production.
"""
import io
import json
from datetime import datetime, timedelta

import pytest

from invoice_schema import normalize
from tests.conftest import auth_header, make_user

INVOICE = {
    "vendor": {"name": "Acme Supplies Ltd"},
    "invoice_number": "INV-001", "invoice_date": "2026-11-01",
    "currency": "NGN",
    "line_items": [{"description": "Widget", "quantity": 1, "unit_price": 100,
                    "amount": 100}],
    "subtotal": "100.00", "tax": 0, "total": "100.00", "confidence": {},
}


@pytest.fixture
def account(app):
    user = make_user(app, email="jobs@example.com", plan="pro")
    return user, auth_header(app, user)


def upload(client, app, monkeypatch, headers, *, document=None, name="inv.pdf",
           content=b"bytes", **form):
    import routes.extract_routes as er

    monkeypatch.setattr(
        "openai_service.extract_document",
        lambda pages, doc_type="invoice": document or normalize(INVOICE),
    )
    data = {"file": (io.BytesIO(content), name)}
    data.update(form)
    return client.post("/api/extract", data=data, headers=headers,
                       content_type="multipart/form-data")


# ─── Queue routing ───────────────────────────────────────────────────────────
def test_a_statement_and_a_multi_page_upload_go_to_the_slow_queue(app):
    """A sixty-page statement and a one-page invoice do not belong in the
    same line."""
    with app.app_context():
        from jobs import QUEUE_BULK, QUEUE_DOCUMENTS, queue_for

        assert queue_for("invoice") == QUEUE_DOCUMENTS
        assert queue_for("receipt") == QUEUE_DOCUMENTS
        assert queue_for("statement") == QUEUE_BULK
        assert queue_for("invoice", page_count=4) == QUEUE_BULK


def test_the_queue_is_off_unless_it_is_configured(app, monkeypatch):
    with app.app_context():
        from jobs import is_enabled

        monkeypatch.delenv("JOB_QUEUE_URL", raising=False)
        assert is_enabled() is False
        monkeypatch.setenv("JOB_QUEUE_URL", "redis://localhost:6379/1")
        assert is_enabled() is True


def test_an_unreachable_queue_falls_back_to_inline_rather_than_failing(
    app, monkeypatch
):
    """Rule 5. A product that stops extracting because a cache is down has
    traded one failure for a worse one."""
    with app.app_context():
        from jobs import enqueue_extraction

        # A port nothing is listening on.
        monkeypatch.setenv("JOB_QUEUE_URL", "redis://127.0.0.1:1/0")
        assert enqueue_extraction("abc", doc_type="invoice") is None


# ─── The inline path still works end to end ──────────────────────────────────
def test_with_no_queue_an_upload_still_returns_the_extraction(
    app, client, account, monkeypatch
):
    """Backwards compatibility: an installation that never sets JOB_QUEUE_URL
    behaves exactly as it did before F4."""
    _user, headers = account
    monkeypatch.delenv("JOB_QUEUE_URL", raising=False)

    response = upload(client, app, monkeypatch, headers)
    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "completed"
    assert body["invoice"]["total"] == "100.00"


def test_the_full_pipeline_still_runs_on_the_inline_path(
    app, client, account, monkeypatch
):
    """Supplier attach, validation and duplicate detection moved into the job.
    They have to still happen."""
    _user, headers = account
    monkeypatch.delenv("JOB_QUEUE_URL", raising=False)

    body = upload(client, app, monkeypatch, headers).get_json()
    assert body["validation"]["status"]
    assert body["corrections"] == []
    with app.app_context():
        from models import Extraction, Supplier

        row = Extraction.query.filter_by(id=body["id"]).first()
        assert row.supplier_id is not None
        assert row.validation_status is not None
        assert row.extracted_field_count > 0
        assert Supplier.query.count() == 1


def test_a_failed_extraction_is_recorded_and_costs_no_quota(
    app, client, account, monkeypatch
):
    """The second half of the acceptance criterion."""
    import routes.extract_routes as er

    user, headers = account
    monkeypatch.delenv("JOB_QUEUE_URL", raising=False)

    def explode(pages, doc_type="invoice"):
        raise RuntimeError("the model refused this document")

    monkeypatch.setattr(
        "openai_service.extract_document", explode)
    response = client.post(
        "/api/extract",
        data={"file": (io.BytesIO(b"bytes"), "bad.pdf")},
        headers=headers, content_type="multipart/form-data",
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "failed"
    assert "refused" in body["errorMessage"]

    with app.app_context():
        from usage import count_usage

        assert count_usage(user["organization_id"]) == 0


# ─── The real queue ──────────────────────────────────────────────────────────
@pytest.fixture
def fake_queue(app, monkeypatch):
    """A real RQ queue on fakeredis.

    Exercises the production path — enqueue, job id, retry policy, worker
    execution — without needing a Redis server. Testing only the inline
    fallback would prove nothing about the code that actually runs.
    """
    import fakeredis
    from rq import Queue

    server = fakeredis.FakeStrictRedis()
    monkeypatch.setenv("JOB_QUEUE_URL", "redis://fake/1")
    monkeypatch.setattr("jobs._connection", lambda: server)
    return {"server": server, "queue": lambda name: Queue(name, connection=server)}


def test_an_upload_is_queued_rather_than_extracted_on_the_request_thread(
    app, client, account, monkeypatch, fake_queue
):
    """Rule 1: the work always leaves the request."""
    import routes.extract_routes as er

    _user, headers = account
    called = []

    def should_not_run(pages, doc_type="invoice"):
        called.append(doc_type)
        return normalize(INVOICE)

    monkeypatch.setattr(
        "openai_service.extract_document", should_not_run)
    response = client.post(
        "/api/extract?wait=false",
        data={"file": (io.BytesIO(b"bytes"), "inv.pdf")},
        headers=headers, content_type="multipart/form-data",
    )
    assert response.status_code == 202
    body = response.get_json()
    assert body["status"] == "processing"
    assert body["jobId"]
    assert body["poll"] == f"/api/extractions/{body['id']}"
    # The extractor was never touched on this thread.
    assert called == []

    queued = fake_queue["queue"]("documents")
    assert len(queued) == 1


def test_the_job_id_is_the_extraction_id_so_a_double_submit_cannot_race(
    app, client, account, monkeypatch, fake_queue
):
    """Rule 4. Two enqueues for one row must not become two workers."""
    with app.app_context():
        from jobs import enqueue_extraction

        first = enqueue_extraction("row-123", doc_type="invoice")
        second = enqueue_extraction("row-123", doc_type="invoice")
        assert first == second == "extract-row-123"
        assert len(fake_queue["queue"]("documents")) == 1


def test_a_statement_is_queued_on_bulk_not_documents(
    app, client, account, monkeypatch, fake_queue
):
    _user, headers = account
    user = make_user(app, email="biz@example.com", plan="business")
    biz_headers = auth_header(app, user)

    response = client.post(
        "/api/extract?wait=false",
        data={"file": (io.BytesIO(b"bytes"), "stmt.pdf"),
              "doc_type": "statement"},
        headers=biz_headers, content_type="multipart/form-data",
    )
    assert response.status_code == 202
    assert len(fake_queue["queue"]("bulk")) == 1
    assert len(fake_queue["queue"]("documents")) == 0


def test_a_worker_running_the_queued_job_completes_the_extraction(
    app, client, account, monkeypatch, fake_queue
):
    """The whole point, end to end: queued here, done by a worker, visible to
    the client afterwards."""
    import extraction_jobs
    import routes.extract_routes as er

    _user, headers = account
    monkeypatch.setattr(
        "openai_service.extract_document",
                        lambda pages, doc_type="invoice": normalize(INVOICE))
    monkeypatch.setattr("openai_service.extract_document",
                        lambda pages, doc_type="invoice": normalize(INVOICE))

    response = client.post(
        "/api/extract?wait=false",
        data={"file": (io.BytesIO(b"bytes"), "inv.pdf")},
        headers=headers, content_type="multipart/form-data",
    )
    eid = response.get_json()["id"]

    with app.app_context():
        assert extraction_jobs.run_extraction(eid, app=app) == "completed"

    detail = client.get(f"/api/extractions/{eid}", headers=headers).get_json()
    assert detail["status"] == "completed"
    assert detail["invoice"]["total"] == "100.00"


def test_waiting_returns_the_finished_result_inline(
    app, client, account, monkeypatch, fake_queue
):
    """`wait` defaults to true so an existing API integration keeps getting a
    result inline. What changed underneath it is where the work runs."""
    import extraction_jobs
    import routes.extract_routes as er

    _user, headers = account
    monkeypatch.setattr(
        "openai_service.extract_document",
                        lambda pages, doc_type="invoice": normalize(INVOICE))

    # Stand in for a worker: finish the job the instant the route starts
    # polling, which is what the real one does a moment later.
    real_await = er._await_extraction

    def finish_then_await(extraction_id, budget):
        extraction_jobs.run_extraction(extraction_id, app=app)
        return real_await(extraction_id, budget)

    monkeypatch.setattr(er, "_await_extraction", finish_then_await)
    monkeypatch.setattr("openai_service.extract_document",
                        lambda pages, doc_type="invoice": normalize(INVOICE))

    response = client.post(
        "/api/extract",
        data={"file": (io.BytesIO(b"bytes"), "inv.pdf")},
        headers=headers, content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert response.get_json()["status"] == "completed"


def test_a_slow_job_answers_202_rather_than_hanging(
    app, client, account, monkeypatch, fake_queue
):
    """The budget is shorter than any sensible proxy timeout: the point is to
    answer, not to hang."""
    import routes.extract_routes as er

    _user, headers = account
    monkeypatch.setattr(er, "WAIT_BUDGET", {"default": 0.2, "statement": 0.2})
    monkeypatch.setattr(er, "POLL_INTERVAL", 0.05)

    response = client.post(
        "/api/extract",
        data={"file": (io.BytesIO(b"bytes"), "inv.pdf")},
        headers=headers, content_type="multipart/form-data",
    )
    assert response.status_code == 202
    assert response.get_json()["status"] == "processing"


# ─── Idempotency ─────────────────────────────────────────────────────────────
def test_running_a_job_twice_does_not_extract_twice(
    app, client, account, monkeypatch, fake_queue
):
    """What makes a retry safe. A job that already finished returns early."""
    import extraction_jobs
    import routes.extract_routes as er

    _user, headers = account
    calls = []

    def count(pages, doc_type="invoice"):
        calls.append(doc_type)
        return normalize(INVOICE)

    monkeypatch.setattr(
        "openai_service.extract_document", count)
    monkeypatch.setattr("openai_service.extract_document", count)

    eid = client.post(
        "/api/extract?wait=false",
        data={"file": (io.BytesIO(b"bytes"), "inv.pdf")},
        headers=headers, content_type="multipart/form-data",
    ).get_json()["id"]

    with app.app_context():
        assert extraction_jobs.run_extraction(eid, app=app) == "completed"
        assert extraction_jobs.run_extraction(eid, app=app) == "completed"
    assert len(calls) == 1


def test_a_job_for_a_deleted_row_does_nothing(app, client, account,
                                              monkeypatch, fake_queue):
    import extraction_jobs
    import routes.extract_routes as er

    _user, headers = account
    monkeypatch.setattr(
        "openai_service.extract_document",
                        lambda pages, doc_type="invoice": normalize(INVOICE))

    eid = client.post(
        "/api/extract?wait=false",
        data={"file": (io.BytesIO(b"bytes"), "inv.pdf")},
        headers=headers, content_type="multipart/form-data",
    ).get_json()["id"]
    client.delete(f"/api/extractions/{eid}", headers=headers)

    with app.app_context():
        assert extraction_jobs.run_extraction(eid, app=app) == "deleted"


def test_a_job_for_a_row_that_vanished_does_not_raise(app):
    import extraction_jobs

    with app.app_context():
        assert extraction_jobs.run_extraction("nope", app=app) == "missing"


def test_the_worker_reloads_pages_from_disk_not_from_the_queue(
    app, client, account, monkeypatch, fake_queue
):
    """Rule 2: the queue carries an id, never a document. If pages did not
    survive on disk the job could not run at all."""
    import routes.extract_routes as er

    _user, headers = account
    monkeypatch.setattr(
        "openai_service.extract_document",
                        lambda pages, doc_type="invoice": normalize(INVOICE))

    eid = client.post(
        "/api/extract?wait=false",
        data={"file": (io.BytesIO(b"the actual bytes"), "inv.pdf")},
        headers=headers, content_type="multipart/form-data",
    ).get_json()["id"]

    with app.app_context():
        from documents import load_pages

        pages = load_pages(eid)
        assert len(pages) == 1
        assert pages[0]["bytes"] == b"the actual bytes"
        assert pages[0]["name"] == "inv.pdf"


def test_pages_come_back_in_upload_order(app, client, account, monkeypatch,
                                         fake_queue):
    """Page order is part of the document, and file_hash is order-sensitive."""
    _user, headers = account
    user = make_user(app, email="multi@example.com", plan="pro")
    multi_headers = auth_header(app, user)
    import routes.extract_routes as er

    monkeypatch.setattr(
        "openai_service.extract_document",
                        lambda pages, doc_type="invoice": normalize(INVOICE))

    eid = client.post(
        "/api/extract?wait=false",
        data={"file": [
            (io.BytesIO(b"page-one"), "a.pdf"),
            (io.BytesIO(b"page-two"), "b.pdf"),
            (io.BytesIO(b"page-three"), "c.pdf"),
        ]},
        headers=multi_headers, content_type="multipart/form-data",
    ).get_json()["id"]

    with app.app_context():
        from documents import load_pages

        assert [p["bytes"] for p in load_pages(eid)] == [
            b"page-one", b"page-two", b"page-three",
        ]


def test_a_job_whose_files_are_gone_fails_with_a_readable_reason(
    app, client, account, monkeypatch, fake_queue
):
    import shutil

    import extraction_jobs
    import routes.extract_routes as er

    _user, headers = account
    monkeypatch.setattr(
        "openai_service.extract_document",
                        lambda pages, doc_type="invoice": normalize(INVOICE))

    eid = client.post(
        "/api/extract?wait=false",
        data={"file": (io.BytesIO(b"bytes"), "inv.pdf")},
        headers=headers, content_type="multipart/form-data",
    ).get_json()["id"]

    with app.app_context():
        from documents import extraction_dir

        shutil.rmtree(extraction_dir(eid), ignore_errors=True)
        assert extraction_jobs.run_extraction(eid, app=app) == "failed"

        from models import Extraction

        row = Extraction.query.filter_by(id=eid).first()
        assert "could not be read back" in row.error_message


# ─── The sweeper: `processing` is always truthful ────────────────────────────
def _stranded(app, account, *, age_hours=4):
    """A row left in `processing` by a worker that never came back."""
    from extensions import db
    from models import Extraction

    user, _headers = account
    with app.app_context():
        row = Extraction(
            organization_id=user["organization_id"], user_id=user["id"],
            doc_type="invoice", file_name="stuck.pdf",
            file_type="application/pdf", file_size=10, data="{}",
            status="processing",
        )
        row.job_queued_at = datetime.utcnow() - timedelta(hours=age_hours)
        db.session.add(row)
        db.session.commit()
        return row.id


def test_the_sweeper_fails_a_row_nothing_is_coming_back_for(app, account):
    from extraction_jobs import sweep_stuck
    from models import Extraction

    eid = _stranded(app, account, age_hours=48)
    with app.app_context():
        assert sweep_stuck() == 1
        row = Extraction.query.filter_by(id=eid).first()
        assert row.status == "failed"
        assert "restarted" in row.error_message
        assert json.loads(row.data)["error"]


def test_the_sweeper_leaves_a_job_that_could_still_be_running(app, account):
    """The cutoff allows for the longest legitimate job plus its retries. A
    sweeper that is too eager kills work that was about to succeed."""
    from extraction_jobs import sweep_stuck
    from models import Extraction

    eid = _stranded(app, account, age_hours=1)
    with app.app_context():
        assert sweep_stuck() == 0
        assert Extraction.query.filter_by(id=eid).first().status == "processing"


def test_the_sweeper_uses_created_at_when_a_row_was_never_queued(app, account):
    """A row created before F4 existed, or one the enqueue never reached."""
    from extensions import db
    from extraction_jobs import sweep_stuck
    from models import Extraction

    user, _headers = account
    with app.app_context():
        row = Extraction(
            organization_id=user["organization_id"], user_id=user["id"],
            doc_type="invoice", file_name="old.pdf",
            file_type="application/pdf", file_size=10, data="{}",
            status="processing",
        )
        db.session.add(row)
        db.session.commit()
        row.created_at = datetime.utcnow() - timedelta(days=3)
        db.session.commit()

        assert sweep_stuck() == 1
        assert Extraction.query.filter_by(id=row.id).first().status == "failed"


def test_the_sweeper_never_touches_a_finished_row(app, client, account,
                                                  monkeypatch):
    from extraction_jobs import sweep_stuck
    from models import Extraction

    _user, headers = account
    monkeypatch.delenv("JOB_QUEUE_URL", raising=False)
    eid = upload(client, app, monkeypatch, headers).get_json()["id"]

    with app.app_context():
        assert sweep_stuck() == 0
        assert Extraction.query.filter_by(id=eid).first().status == "completed"


def test_a_swept_row_consumed_no_quota(app, account):
    """Stranded and then failed is still a failure, and a failure is free."""
    from extraction_jobs import sweep_stuck
    from usage import count_usage

    user, _headers = account
    _stranded(app, account, age_hours=48)
    with app.app_context():
        sweep_stuck()
        assert count_usage(user["organization_id"]) == 0


def test_reading_history_sweeps_abandoned_rows(app, client, account):
    """No scheduler on this deployment, so the sweep happens at the moment
    somebody asks "did that work?"."""
    from models import Extraction

    _user, headers = account
    eid = _stranded(app, account, age_hours=48)

    body = client.get("/api/extractions", headers=headers).get_json()
    assert body
    with app.app_context():
        assert Extraction.query.filter_by(id=eid).first().status == "failed"


def test_the_sweeper_is_bounded(app, account):
    """It runs on a read path, so it must never become a full table scan."""
    from extensions import db
    from extraction_jobs import sweep_stuck
    from models import Extraction

    user, _headers = account
    with app.app_context():
        for index in range(5):
            row = Extraction(
                organization_id=user["organization_id"], user_id=user["id"],
                doc_type="invoice", file_name=f"s{index}.pdf",
                file_type="application/pdf", file_size=10, data="{}",
                status="processing",
            )
            row.job_queued_at = datetime.utcnow() - timedelta(days=2)
            db.session.add(row)
        db.session.commit()

        assert sweep_stuck(limit=2) == 2
        assert sweep_stuck(limit=10) == 3
        assert sweep_stuck() == 0


def test_attempts_are_counted_so_a_retry_loop_is_visible(
    app, client, account, monkeypatch, fake_queue
):
    import extraction_jobs
    import routes.extract_routes as er

    _user, headers = account
    monkeypatch.setattr(
        "openai_service.extract_document",
                        lambda pages, doc_type="invoice": normalize(INVOICE))

    def fail(pages, doc_type="invoice"):
        raise RuntimeError("upstream hiccup")

    eid = client.post(
        "/api/extract?wait=false",
        data={"file": (io.BytesIO(b"bytes"), "inv.pdf")},
        headers=headers, content_type="multipart/form-data",
    ).get_json()["id"]

    monkeypatch.setattr("openai_service.extract_document", fail)
    with app.app_context():
        from extensions import db
        from models import Extraction

        extraction_jobs.run_extraction(eid, app=app)
        row = Extraction.query.filter_by(id=eid).first()
        assert row.status == "failed"
        assert row.job_attempts == 1

        # A retry of a failed row runs again and counts again.
        row.status = "processing"
        db.session.commit()
        extraction_jobs.run_extraction(eid, app=app)
        assert Extraction.query.filter_by(id=eid).first().job_attempts == 2


def test_the_row_records_which_job_owns_it(app, client, account, monkeypatch,
                                           fake_queue):
    _user, headers = account
    import routes.extract_routes as er

    monkeypatch.setattr(
        "openai_service.extract_document",
                        lambda pages, doc_type="invoice": normalize(INVOICE))

    eid = client.post(
        "/api/extract?wait=false",
        data={"file": (io.BytesIO(b"bytes"), "inv.pdf")},
        headers=headers, content_type="multipart/form-data",
    ).get_json()["id"]

    with app.app_context():
        from models import Extraction

        row = Extraction.query.filter_by(id=eid).first()
        assert row.job_id == f"extract-{eid}"
        assert row.job_queued_at is not None
