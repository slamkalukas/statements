def _make_period(client, auth_headers, year=2026, month=6, note=""):
    return client.post(
        "/api/periods",
        json={"year": year, "month": month, "note": note},
        headers=auth_headers,
    )


def test_create_and_list_period(client, auth_headers):
    res = _make_period(client, auth_headers, note="June books")
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["year"] == 2026 and body["month"] == 6
    assert body["status"] == "open"
    assert body["document_count"] == 0
    assert body["has_statement"] is False

    listing = client.get("/api/periods", headers=auth_headers)
    assert listing.status_code == 200
    assert len(listing.json()) == 1


def test_duplicate_month_rejected(client, auth_headers):
    assert _make_period(client, auth_headers).status_code == 201
    dup = _make_period(client, auth_headers)
    assert dup.status_code == 409


def test_invalid_month_rejected(client, auth_headers):
    assert _make_period(client, auth_headers, month=13).status_code == 422


def test_close_and_reopen(client, auth_headers):
    pid = _make_period(client, auth_headers).json()["id"]
    closed = client.post(f"/api/periods/{pid}/close", headers=auth_headers)
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"

    reopened = client.post(f"/api/periods/{pid}/reopen", headers=auth_headers)
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "open"


def test_delete_empty_period(client, auth_headers):
    pid = _make_period(client, auth_headers).json()["id"]
    assert client.delete(f"/api/periods/{pid}", headers=auth_headers).status_code == 204
    assert client.get("/api/periods", headers=auth_headers).json() == []


def test_delete_period_with_documents_blocked(client, auth_headers):
    pid = _make_period(client, auth_headers).json()["id"]
    up = client.post(
        f"/api/periods/{pid}/documents",
        data={"kind": "invoice"},
        files={"file": ("inv.pdf", b"hello", "application/pdf")},
        headers=auth_headers,
    )
    assert up.status_code == 201, up.text
    blocked = client.delete(f"/api/periods/{pid}", headers=auth_headers)
    assert blocked.status_code == 409
