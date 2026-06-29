from pathlib import Path


def _period(client, auth_headers, year=2026, month=6):
    return client.post(
        "/api/periods", json={"year": year, "month": month}, headers=auth_headers
    ).json()["id"]


def _upload(client, auth_headers, pid, *, name="statement.pdf", kind="bank_statement",
            content=b"PDF-BYTES", **form):
    data = {"kind": kind, **{k: v for k, v in form.items() if v is not None}}
    return client.post(
        f"/api/periods/{pid}/documents",
        data=data,
        files={"file": (name, content, "application/pdf")},
        headers=auth_headers,
    )


def test_upload_lands_on_disk_under_year_month(client, auth_headers, storage):
    pid = _period(client, auth_headers, 2026, 6)
    res = _upload(client, auth_headers, pid)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["kind"] == "bank_statement"
    assert body["size_bytes"] == len(b"PDF-BYTES")

    # The file exists on the mapped folder at <root>/2026/06/statement.pdf.
    expected = storage.DOCUMENTS_DIR / "2026" / "06" / "statement.pdf"
    assert expected.is_file()
    assert expected.read_bytes() == b"PDF-BYTES"

    # The period now reports one document. has_statement stays False — it tracks
    # whether the statement has been *parsed into lines*, not just a file upload.
    period = client.get("/api/periods", headers=auth_headers).json()[0]
    assert period["document_count"] == 1
    assert period["has_statement"] is False
    assert period["total_size"] == len(b"PDF-BYTES")


def test_custom_folder_changes_upload_location(client, auth_headers, storage):
    pid = _period(client, auth_headers, 2026, 4)

    # Set a custom subfolder for this month.
    r = client.post(f"/api/periods/{pid}/folder", json={"folder": "2026/04-vat"}, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["folder"] == "2026/04-vat"

    # Uploads now land under the custom folder, not 2026/04.
    _upload(client, auth_headers, pid, name="bill.pdf", kind="invoice", content=b"X")
    assert (storage.DOCUMENTS_DIR / "2026" / "04-vat" / "bill.pdf").is_file()
    assert not (storage.DOCUMENTS_DIR / "2026" / "04" / "bill.pdf").exists()


def test_layout_setting_drives_default_folder(client, auth_headers, storage):
    pid = _period(client, auth_headers, 2030, 3)
    # Default layout -> YYYY/MM.
    def folder_of(pid):
        return next(p for p in client.get("/api/periods", headers=auth_headers).json()
                    if p["id"] == pid)["folder"]
    assert folder_of(pid) == "2030/03"

    # Host folder is reported read-only; only the layout is editable.
    info = client.get("/api/storage", headers=auth_headers).json()
    assert info["layout"] == "{YYYY}/{MM}"
    assert info["host_path"]  # present (read-only display)

    r = client.patch("/api/storage", json={"layout": "#{YYYY}/Vydavky"}, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["layout"] == "#{YYYY}/Vydavky"

    # A month without an explicit folder now follows the new layout, and uploads
    # land there.
    assert folder_of(pid) == "#2030/Vydavky"
    _upload(client, auth_headers, pid, name="x.pdf", kind="invoice", content=b"x")
    assert (storage.DOCUMENTS_DIR / "#2030" / "Vydavky" / "x.pdf").is_file()


def test_blank_folder_resets_to_default(client, auth_headers, storage):
    pid = _period(client, auth_headers, 2026, 5)
    client.post(f"/api/periods/{pid}/folder", json={"folder": "custom/x"}, headers=auth_headers)
    back = client.post(f"/api/periods/{pid}/folder", json={"folder": ""}, headers=auth_headers).json()
    assert back["folder"] == "2026/05"  # default restored


def test_folder_traversal_is_neutralized(client, auth_headers, storage):
    pid = _period(client, auth_headers, 2026, 6)
    # ".." segments are stripped, so the path can't escape the root.
    r = client.post(f"/api/periods/{pid}/folder", json={"folder": "../../etc"}, headers=auth_headers)
    assert r.status_code == 200
    assert ".." not in r.json()["folder"]


def test_download_round_trips_bytes(client, auth_headers):
    pid = _period(client, auth_headers)
    doc_id = _upload(client, auth_headers, pid, content=b"hello world").json()["id"]
    res = client.get(f"/api/documents/{doc_id}/download", headers=auth_headers)
    assert res.status_code == 200
    assert res.content == b"hello world"


def test_delete_removes_row_and_file(client, auth_headers, storage):
    pid = _period(client, auth_headers)
    doc_id = _upload(client, auth_headers, pid, name="del.pdf").json()["id"]
    path = storage.DOCUMENTS_DIR / "2026" / "06" / "del.pdf"
    assert path.is_file()

    assert client.delete(f"/api/documents/{doc_id}", headers=auth_headers).status_code == 204
    assert not path.exists()
    assert client.get(f"/api/documents/{doc_id}/download", headers=auth_headers).status_code == 404


def test_filename_collisions_get_suffixed(client, auth_headers, storage):
    pid = _period(client, auth_headers)
    _upload(client, auth_headers, pid, name="dup.pdf")
    _upload(client, auth_headers, pid, name="dup.pdf")
    folder = storage.DOCUMENTS_DIR / "2026" / "06"
    names = sorted(p.name for p in folder.iterdir())
    assert names == ["dup (1).pdf", "dup.pdf"]


def test_path_traversal_filename_is_sanitized(client, auth_headers, storage):
    pid = _period(client, auth_headers)
    res = _upload(client, auth_headers, pid, name="../../evil.pdf")
    assert res.status_code == 201
    # Nothing escaped the root; the file is inside 2026/06 with a flattened name.
    assert res.json()["original_filename"] == "../../evil.pdf"  # original recorded as sent
    files = list((storage.DOCUMENTS_DIR / "2026" / "06").iterdir())
    assert len(files) == 1
    assert files[0].name == "evil.pdf"
    # The root has only the 2026 tree — no stray files above it.
    assert {p.name for p in storage.DOCUMENTS_DIR.iterdir()} == {"2026"}


def test_oversize_upload_rejected(client, auth_headers, storage):
    pid = _period(client, auth_headers)
    too_big = b"x" * (storage.MAX_UPLOAD_BYTES + 1)
    res = _upload(client, auth_headers, pid, name="big.pdf", content=too_big)
    assert res.status_code == 413
    # Partial file was cleaned up.
    assert not (storage.DOCUMENTS_DIR / "2026" / "06").exists() or not list(
        (storage.DOCUMENTS_DIR / "2026" / "06").iterdir()
    )


def test_invalid_kind_rejected(client, auth_headers):
    pid = _period(client, auth_headers)
    assert _upload(client, auth_headers, pid, kind="nonsense").status_code == 400


def test_upload_to_closed_period_blocked(client, auth_headers):
    pid = _period(client, auth_headers)
    client.post(f"/api/periods/{pid}/close", headers=auth_headers)
    res = _upload(client, auth_headers, pid)
    assert res.status_code == 409


def test_delete_on_closed_period_blocked(client, auth_headers):
    pid = _period(client, auth_headers)
    doc_id = _upload(client, auth_headers, pid).json()["id"]
    client.post(f"/api/periods/{pid}/close", headers=auth_headers)
    assert client.delete(f"/api/documents/{doc_id}", headers=auth_headers).status_code == 409


def test_optional_metadata_persisted(client, auth_headers):
    pid = _period(client, auth_headers)
    res = _upload(
        client, auth_headers, pid, kind="invoice",
        doc_date="2026-06-15", amount="123.45", note="Acme supplies",
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["doc_date"] == "2026-06-15"
    assert body["amount"] == 123.45
    assert body["note"] == "Acme supplies"
