"""The in-app file browser: list folders/files under the documents root."""


def _period(client, auth_headers, year=2026, month=6):
    return client.post(
        "/api/periods", json={"year": year, "month": month}, headers=auth_headers
    ).json()["id"]


def test_browse_root_then_into_month(client, auth_headers, storage):
    pid = _period(client, auth_headers, 2026, 6)
    client.post(
        f"/api/periods/{pid}/documents",
        data={"kind": "invoice"},
        files={"file": ("inv.pdf", b"PDFDATA", "application/pdf")},
        headers=auth_headers,
    )

    # Root lists the year folder.
    root = client.get("/api/files", headers=auth_headers).json()
    assert root["path"] == "" and root["parent"] == ""
    assert any(e["name"] == "2026" and e["is_dir"] for e in root["entries"])

    # Navigate into 2026/06 and see the file.
    month = client.get("/api/files", params={"path": "2026/06"}, headers=auth_headers).json()
    assert month["path"] == "2026/06"
    assert month["parent"] == "2026"
    files = [e for e in month["entries"] if not e["is_dir"]]
    assert files and files[0]["name"] == "inv.pdf"
    assert files[0]["size_bytes"] == len(b"PDFDATA")


def test_download_file_by_path(client, auth_headers, storage):
    pid = _period(client, auth_headers, 2026, 7)
    client.post(
        f"/api/periods/{pid}/documents",
        data={"kind": "other"},
        files={"file": ("note.txt", b"hello bytes", "text/plain")},
        headers=auth_headers,
    )
    res = client.get("/api/files/download", params={"path": "2026/07/note.txt"}, headers=auth_headers)
    assert res.status_code == 200
    assert res.content == b"hello bytes"


def test_path_traversal_is_rejected(client, auth_headers, storage):
    res = client.get("/api/files", params={"path": "../../etc"}, headers=auth_headers)
    assert res.status_code in (400, 404)
    res2 = client.get("/api/files/download", params={"path": "../secrets"}, headers=auth_headers)
    assert res2.status_code in (400, 404)


def test_requires_auth(client):
    assert client.get("/api/files").status_code == 401
