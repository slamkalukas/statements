"""Pairing uploaded documents to outgoing payments by amount."""
import json

SLSP_JSON = json.dumps(
    [
        {"amount": {"value": -1500, "precision": 2, "currency": "EUR"}, "booking": "2026-06-03",
         "reference": "Office rent", "partnerName": "Landlord s.r.o."},
        {"amount": {"value": -4999, "precision": 2, "currency": "EUR"}, "booking": "2026-06-10",
         "reference": "Internet", "partnerName": "Telekom"},
    ]
).encode()


def _period(client, auth_headers, year=2026, month=6):
    return client.post(
        "/api/periods", json={"year": year, "month": month}, headers=auth_headers
    ).json()["id"]


def _import(client, auth_headers, pid):
    return client.post(
        f"/api/periods/{pid}/statement",
        files={"file": ("george.json", SLSP_JSON, "application/octet-stream")},
        headers=auth_headers,
    )


def _upload(client, auth_headers, pid, *, name="invoice.pdf", kind="invoice",
            content=b"PDF", amount=None):
    data = {"kind": kind}
    if amount is not None:
        data["amount"] = amount
    return client.post(
        f"/api/periods/{pid}/documents",
        data=data,
        files={"file": (name, content, "application/pdf")},
        headers=auth_headers,
    )


def _lines(client, auth_headers, pid):
    return client.get(f"/api/periods/{pid}/lines", headers=auth_headers).json()


def test_upload_with_amount_auto_links_unique_payment(client, auth_headers, storage):
    pid = _period(client, auth_headers)
    _import(client, auth_headers, pid)
    # An invoice whose amount matches exactly one outgoing payment (15.00).
    _upload(client, auth_headers, pid, amount="15.00")

    lines = _lines(client, auth_headers, pid)
    rent = next(l for l in lines if l["amount"] == -15.0)
    assert rent["document_id"] is not None  # auto-paired on upload


def test_upload_reports_text_extraction_method(client, auth_headers, storage):
    pid = _period(client, auth_headers, 2026, 11)
    # A text "invoice" with no amount entered — the app reads it from the file.
    res = client.post(
        f"/api/periods/{pid}/documents",
        data={"kind": "invoice"},
        files={"file": ("bill.txt", b"Spolu k uhrade 42,00 EUR", "text/plain")},
        headers=auth_headers,
    )
    body = res.json()
    assert body["amount"] == 42.0
    assert body["extracted_via"] == "text"


def test_upload_with_amount_does_not_link_when_ambiguous(client, auth_headers, storage):
    pid = _period(client, auth_headers, 2026, 7)
    # Two payments of the same amount: a single invoice can't be auto-assigned.
    dup = json.dumps([
        {"amount": {"value": -2000, "precision": 2}, "booking": "2026-07-01", "reference": "A"},
        {"amount": {"value": -2000, "precision": 2}, "booking": "2026-07-02", "reference": "B"},
    ]).encode()
    client.post(f"/api/periods/{pid}/statement",
                files={"file": ("d.json", dup, "application/octet-stream")},
                headers=auth_headers)
    _upload(client, auth_headers, pid, amount="20.00")

    lines = _lines(client, auth_headers, pid)
    assert all(l["document_id"] is None for l in lines)  # left for manual choice


def test_sync_scans_and_pairs_file_from_disk(client, auth_headers, storage):
    """A file dropped on disk is read and paired to the matching outgoing
    payment by the sync itself — no separate auto-match click needed."""
    pid = _period(client, auth_headers, 2026, 8)
    js = json.dumps([
        {"amount": {"value": -1500, "precision": 2}, "booking": "2026-08-03", "reference": "Rent"},
    ]).encode()
    client.post(f"/api/periods/{pid}/statement",
                files={"file": ("d.json", js, "application/octet-stream")},
                headers=auth_headers)

    # Drop a text "invoice" carrying the amount onto the host folder, then sync.
    folder = storage.DOCUMENTS_DIR / "2026" / "08"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "bill.txt").write_text("Spolu k uhrade 15,00 EUR", encoding="utf-8")
    synced = client.post(f"/api/periods/{pid}/sync", headers=auth_headers).json()
    assert synced["imported"] == 1
    assert synced["matched"] == 1  # read + paired during sync

    # The payment is already linked right after the sync.
    line = _lines(client, auth_headers, pid)[0]
    assert line["document_id"] is not None

    # The imported document records that its amount was read from the text layer.
    docs = client.get(f"/api/periods/{pid}/documents", headers=auth_headers).json()
    bill = next(d for d in docs if d["original_filename"] == "bill.txt")
    assert bill["amount"] == 15.0
    assert bill["extracted_via"] == "text"


def test_auto_match_still_works_after_sync(client, auth_headers, storage):
    """Auto-match remains a no-op safety net once sync already paired everything."""
    pid = _period(client, auth_headers, 2026, 9)
    js = json.dumps([
        {"amount": {"value": -1500, "precision": 2}, "booking": "2026-09-03", "reference": "Rent"},
    ]).encode()
    client.post(f"/api/periods/{pid}/statement",
                files={"file": ("d.json", js, "application/octet-stream")},
                headers=auth_headers)
    folder = storage.DOCUMENTS_DIR / "2026" / "09"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "bill.txt").write_text("Spolu k uhrade 15,00 EUR", encoding="utf-8")
    client.post(f"/api/periods/{pid}/sync", headers=auth_headers)

    body = client.post(f"/api/periods/{pid}/auto-match", json={}, headers=auth_headers).json()
    # Already paired during sync, and its amount is set, so nothing left to do.
    assert body["scanned"] == 0
    assert body["matched"] == 0
    assert body["still_missing"] == 0
