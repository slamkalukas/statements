"""Reconciliation: parse a statement, see which outgoing payments are missing a
document, and match documents to lines."""
import json


def _period(client, auth_headers, year=2026, month=6):
    return client.post(
        "/api/periods", json={"year": year, "month": month}, headers=auth_headers
    ).json()["id"]


# A George/Erste-style JSON export: two payments out, one income in.
SLSP_JSON = json.dumps(
    [
        {"amount": {"value": -1500, "precision": 2, "currency": "EUR"}, "booking": "2026-06-03",
         "reference": "Office rent", "partnerName": "Landlord s.r.o."},
        {"amount": {"value": -4999, "precision": 2, "currency": "EUR"}, "booking": "2026-06-10",
         "reference": "Internet", "partnerName": "Telekom"},
        {"amount": {"value": 250000, "precision": 2, "currency": "EUR"}, "booking": "2026-06-01",
         "reference": "Client payment", "partnerName": "Acme Corp"},
    ]
).encode()

CSV_TEXT = (
    "Date;Amount;Description;Partner\n"
    "05.06.2026;-12,50;Coffee beans;Beanery\n"
    "06.06.2026;-99,00;Hosting;Cloudy\n"
    "07.06.2026;1000,00;Refund;Acme\n"
).encode()

CAMT_XML = b"""<?xml version="1.0"?>
<Document><BkToCstmrStmt><Stmt>
  <Ntry><Amt Ccy="EUR">75.00</Amt><CdtDbtInd>DBIT</CdtDbtInd>
    <BookgDt><Dt>2026-06-08</Dt></BookgDt>
    <NtryDtls><TxDtls><RmtInf><Ustrd>Stationery</Ustrd></RmtInf>
      <RltdPties><Cdtr><Nm>Paper Co</Nm></Cdtr></RltdPties></TxDtls></NtryDtls>
  </Ntry>
</Stmt></BkToCstmrStmt></Document>"""


def _import(client, auth_headers, pid, content, name):
    return client.post(
        f"/api/periods/{pid}/statement",
        files={"file": (name, content, "application/octet-stream")},
        headers=auth_headers,
    )


def test_import_json_counts_outgoing(client, auth_headers):
    pid = _period(client, auth_headers)
    res = _import(client, auth_headers, pid, SLSP_JSON, "george.json")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["format"] == "George JSON"
    assert body["imported"] == 3
    assert body["outgoing"] == 2  # the income line doesn't need a document

    # Period now reports 2 missing (both outgoing payments, unmatched).
    p = next(p for p in client.get("/api/periods", headers=auth_headers).json() if p["id"] == pid)
    assert p["has_statement"] is True
    assert p["outgoing_count"] == 2
    assert p["missing_count"] == 2

    # The statement file itself was also stored as a document.
    docs = client.get(f"/api/periods/{pid}/documents", headers=auth_headers).json()
    assert any(d["kind"] == "bank_statement" for d in docs)


def test_mark_no_document_excludes_from_missing(client, auth_headers):
    pid = _period(client, auth_headers, month=7)
    _import(client, auth_headers, pid, SLSP_JSON, "george.json")
    lines = client.get(f"/api/periods/{pid}/lines", headers=auth_headers).json()
    fee = next(l for l in lines if l["amount"] == -15.0)

    # Mark the fee as not needing a document.
    r = client.post(f"/api/lines/{fee['id']}/no-document", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["no_doc_needed"] is True

    p = next(p for p in client.get("/api/periods", headers=auth_headers).json() if p["id"] == pid)
    assert p["outgoing_count"] == 2
    assert p["missing_count"] == 1   # the fee no longer counts as missing
    assert p["no_doc_count"] == 1

    # Revert: it needs a document again.
    client.post(f"/api/lines/{fee['id']}/needs-document", headers=auth_headers)
    p = next(p for p in client.get("/api/periods", headers=auth_headers).json() if p["id"] == pid)
    assert p["missing_count"] == 2
    assert p["no_doc_count"] == 0


def test_mark_no_document_detaches_existing_link(client, auth_headers, storage):
    pid = _period(client, auth_headers, month=8)
    _import(client, auth_headers, pid, SLSP_JSON, "george.json")
    lines = client.get(f"/api/periods/{pid}/lines", headers=auth_headers).json()
    fee = next(l for l in lines if l["amount"] == -15.0)

    # Upload an invoice and link it, then change our mind: no document needed.
    doc = client.post(
        f"/api/periods/{pid}/documents",
        data={"kind": "invoice"},
        files={"file": ("x.txt", b"hello", "text/plain")},
        headers=auth_headers,
    ).json()
    client.post(f"/api/lines/{fee['id']}/link", json={"document_id": doc["id"]}, headers=auth_headers)
    r = client.post(f"/api/lines/{fee['id']}/no-document", headers=auth_headers).json()
    assert r["no_doc_needed"] is True
    assert r["document_id"] is None  # the link was cleared


CC_JSON = json.dumps(
    [
        {"amount": {"value": -2500, "precision": 2, "currency": "EUR"}, "booking": "2026-09-15",
         "reference": "Cloud hosting", "partnerName": "AWS"},
    ]
).encode()


def test_multiple_accounts_per_month(client, auth_headers):
    pid = _period(client, auth_headers, month=9)

    r1 = client.post(
        f"/api/periods/{pid}/statement",
        files={"file": ("bank.json", SLSP_JSON, "application/octet-stream")},
        data={"source": "Bank account"},
        headers=auth_headers,
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["source"] == "Bank account"
    assert r1.json()["outgoing"] == 2

    r2 = client.post(
        f"/api/periods/{pid}/statement",
        files={"file": ("cc.json", CC_JSON, "application/octet-stream")},
        data={"source": "Credit card"},
        headers=auth_headers,
    )
    assert r2.json()["source"] == "Credit card"
    assert r2.json()["outgoing"] == 1

    # Lines carry their account; the two accounts stay separate.
    lines = client.get(f"/api/periods/{pid}/lines", headers=auth_headers).json()
    bank = [l for l in lines if l["source"] == "Bank account"]
    card = [l for l in lines if l["source"] == "Credit card"]
    assert len(bank) == 3 and len(card) == 1

    # Aggregate missing counts every account's outgoing payments (2 + 1).
    p = next(p for p in client.get("/api/periods", headers=auth_headers).json() if p["id"] == pid)
    assert p["missing_count"] == 3

    # Re-importing an account dedups within that account only.
    again = client.post(
        f"/api/periods/{pid}/statement",
        files={"file": ("cc.json", CC_JSON, "application/octet-stream")},
        data={"source": "Credit card"},
        headers=auth_headers,
    ).json()
    assert again["imported"] == 0 and again["duplicates"] == 1

    # Clearing one account leaves the other intact.
    client.delete(f"/api/periods/{pid}/lines", params={"source": "Credit card"}, headers=auth_headers)
    after = client.get(f"/api/periods/{pid}/lines", headers=auth_headers).json()
    assert len(after) == 3 and all(l["source"] == "Bank account" for l in after)


def test_move_line_to_another_month(client, auth_headers):
    # Import into May; one payment actually belongs to April's books.
    may = _period(client, auth_headers, 2026, 5)
    _import(client, auth_headers, may, SLSP_JSON, "may.json")
    line = next(l for l in client.get(f"/api/periods/{may}/lines", headers=auth_headers).json()
                if l["amount"] == -15.0)

    # Move it to April (which doesn't exist yet — it gets created).
    r = client.post(f"/api/lines/{line['id']}/move", json={"year": 2026, "month": 4}, headers=auth_headers)
    assert r.status_code == 200, r.text

    # It's gone from May and now in April, keeping its transaction date.
    may_lines = client.get(f"/api/periods/{may}/lines", headers=auth_headers).json()
    assert all(l["id"] != line["id"] for l in may_lines)
    periods = client.get("/api/periods", headers=auth_headers).json()
    april = next(p for p in periods if p["year"] == 2026 and p["month"] == 4)
    april_lines = client.get(f"/api/periods/{april['id']}/lines", headers=auth_headers).json()
    moved = next(l for l in april_lines if l["id"] == line["id"])
    assert moved["txn_date"] == "2026-06-03"  # original date preserved


def test_reimport_does_not_recreate_a_moved_line(client, auth_headers):
    may = _period(client, auth_headers, 2026, 5)
    _import(client, auth_headers, may, SLSP_JSON, "may.json")
    line = next(l for l in client.get(f"/api/periods/{may}/lines", headers=auth_headers).json()
                if l["amount"] == -15.0)
    client.post(f"/api/lines/{line['id']}/move", json={"year": 2026, "month": 4}, headers=auth_headers)

    # Re-importing the same May statement must NOT recreate the moved line.
    again = _import(client, auth_headers, may, SLSP_JSON, "may.json").json()
    assert again["imported"] == 0
    assert again["duplicates"] == 3  # all three lines already exist (one now in April)


def test_import_csv_and_camt(client, auth_headers):
    pid_csv = _period(client, auth_headers, month=4)
    r1 = _import(client, auth_headers, pid_csv, CSV_TEXT, "export.csv")
    assert r1.status_code == 200, r1.text
    assert r1.json()["format"] == "CSV"
    assert r1.json()["outgoing"] == 2

    pid_xml = _period(client, auth_headers, month=5)
    r2 = _import(client, auth_headers, pid_xml, CAMT_XML, "tatra.xml")
    assert r2.status_code == 200, r2.text
    assert r2.json()["format"] == "CAMT.053 XML"
    assert r2.json()["outgoing"] == 1


def test_reimport_is_deduplicated(client, auth_headers):
    pid = _period(client, auth_headers)
    _import(client, auth_headers, pid, SLSP_JSON, "george.json")
    again = _import(client, auth_headers, pid, SLSP_JSON, "george.json")
    assert again.json()["imported"] == 0
    assert again.json()["duplicates"] == 3


def test_link_document_clears_missing(client, auth_headers):
    pid = _period(client, auth_headers)
    _import(client, auth_headers, pid, SLSP_JSON, "george.json")
    lines = client.get(f"/api/periods/{pid}/lines", headers=auth_headers).json()
    outgoing = [ln for ln in lines if ln["amount"] < 0]
    assert len(outgoing) == 2

    # Upload an invoice and link it to the first outgoing payment.
    up = client.post(
        f"/api/periods/{pid}/documents",
        data={"kind": "invoice", "amount": "15.00"},
        files={"file": ("rent.pdf", b"rent invoice", "application/pdf")},
        headers=auth_headers,
    )
    doc_id = up.json()["id"]
    linked = client.post(
        f"/api/lines/{outgoing[0]['id']}/link",
        json={"document_id": doc_id},
        headers=auth_headers,
    )
    assert linked.status_code == 200
    assert linked.json()["document_id"] == doc_id
    assert linked.json()["document_filename"] == "rent.pdf"

    # One payment still missing.
    p = next(p for p in client.get("/api/periods", headers=auth_headers).json() if p["id"] == pid)
    assert p["missing_count"] == 1

    # The document reports it now supports one line.
    docs = client.get(f"/api/periods/{pid}/documents", headers=auth_headers).json()
    assert next(d for d in docs if d["id"] == doc_id)["linked_line_count"] == 1


def test_link_on_upload_and_unlink(client, auth_headers):
    pid = _period(client, auth_headers)
    _import(client, auth_headers, pid, SLSP_JSON, "george.json")
    line = next(ln for ln in client.get(f"/api/periods/{pid}/lines", headers=auth_headers).json() if ln["amount"] < 0)

    # Upload-and-link in one step via the optional line_id form field.
    up = client.post(
        f"/api/periods/{pid}/documents",
        data={"kind": "invoice", "line_id": str(line["id"])},
        files={"file": ("bill.pdf", b"bill", "application/pdf")},
        headers=auth_headers,
    )
    assert up.status_code == 201
    refreshed = next(ln for ln in client.get(f"/api/periods/{pid}/lines", headers=auth_headers).json() if ln["id"] == line["id"])
    assert refreshed["document_id"] == up.json()["id"]

    # Unlink reverts it to missing.
    client.post(f"/api/lines/{line['id']}/unlink", headers=auth_headers)
    p = next(p for p in client.get("/api/periods", headers=auth_headers).json() if p["id"] == pid)
    assert p["missing_count"] == 2


def test_deleting_document_reverts_line_to_missing(client, auth_headers):
    pid = _period(client, auth_headers)
    _import(client, auth_headers, pid, SLSP_JSON, "george.json")
    line = next(ln for ln in client.get(f"/api/periods/{pid}/lines", headers=auth_headers).json() if ln["amount"] < 0)
    up = client.post(
        f"/api/periods/{pid}/documents",
        data={"kind": "invoice", "line_id": str(line["id"])},
        files={"file": ("bill.pdf", b"bill", "application/pdf")},
        headers=auth_headers,
    )
    assert client.delete(f"/api/documents/{up.json()['id']}", headers=auth_headers).status_code == 204
    refreshed = next(ln for ln in client.get(f"/api/periods/{pid}/lines", headers=auth_headers).json() if ln["id"] == line["id"])
    assert refreshed["document_id"] is None


def test_dashboard_missing_totals(client, auth_headers):
    pid = _period(client, auth_headers)
    _import(client, auth_headers, pid, SLSP_JSON, "george.json")
    d = client.get("/api/dashboard", headers=auth_headers).json()
    assert d["total_missing"] == 2
    assert d["months_with_missing"] == 1
    assert d["no_statement"] == 0


def test_import_to_closed_period_blocked(client, auth_headers):
    pid = _period(client, auth_headers)
    client.post(f"/api/periods/{pid}/close", headers=auth_headers)
    assert _import(client, auth_headers, pid, SLSP_JSON, "g.json").status_code == 409


def test_unparseable_statement_rejected(client, auth_headers):
    pid = _period(client, auth_headers)
    res = _import(client, auth_headers, pid, b"not a statement at all", "junk.txt")
    assert res.status_code == 400
