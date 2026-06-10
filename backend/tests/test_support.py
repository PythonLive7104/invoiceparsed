"""Support assistant chat + contact form."""


def test_chat_pricing_intent(client):
    r = client.post("/api/chat", json={"message": "how much does it cost?"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["intent"] == "pricing"
    assert "$19" in body["reply"]


def test_chat_accepts_messages_array(client):
    r = client.post("/api/chat", json={"messages": [
        {"role": "user", "content": "do you support receipts?"},
    ]})
    assert r.status_code == 200
    assert r.get_json()["intent"] == "receipts"


def test_chat_fallback(client):
    r = client.post("/api/chat", json={"message": "qwerty zxcv asdf"})
    assert r.status_code == 200
    assert r.get_json()["intent"] == "fallback"


def test_contact_validates_email(client):
    r = client.post("/api/contact", json={"name": "A", "email": "bad", "message": "hello there"})
    assert r.status_code == 400


def test_contact_sends(client, monkeypatch):
    import routes.support_routes as sr
    captured = {}
    monkeypatch.setattr(sr, "send_contact", lambda n, e, m: captured.update(name=n, email=e, msg=m) or True)
    r = client.post("/api/contact", json={
        "name": "Olu", "email": "olu@example.com", "message": "Great tool, a question…",
    })
    assert r.status_code == 200
    assert captured["email"] == "olu@example.com"
