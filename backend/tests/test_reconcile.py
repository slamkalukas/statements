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
