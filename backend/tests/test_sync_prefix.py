"""Sync routing by filename month prefix, so several months can share a folder."""


def _period(client, auth_headers, year, month):
    return client.post(
        "/api/periods", json={"year": year, "month": month}, headers=auth_headers
    ).json()["id"]


def _set_folder(client, auth_headers, pid, folder):
    return client.post(f"/api/periods/{pid}/folder", json={"folder": folder}, headers=auth_headers)


def _docs(client, auth_headers, pid):
    return client.get(f"/api/periods/{pid}/documents", headers=auth_headers).json()


def test_shared_folder_routes_by_month_prefix(client, auth_headers, storage):
    # Two months pointed at the SAME shared folder.
    apr = _period(client, auth_headers, 2026, 4)
    may = _period(client, auth_headers, 2026, 5)
    _set_folder(client, auth_headers, apr, "shared")
    _set_folder(client, auth_headers, may, "shared")

    shared = storage.DOCUMENTS_DIR / "shared"
    shared.mkdir(parents=True, exist_ok=True)
    (shared / "04_rent.txt").write_text("x", encoding="utf-8")
    (shared / "05_shell.txt").write_text("x", encoding="utf-8")
    (shared / "05_alza.txt").write_text("x", encoding="utf-8")

    # April sync takes only 04_* files.
    client.post(f"/api/periods/{apr}/sync", headers=auth_headers)
    apr_names = sorted(d["original_filename"] for d in _docs(client, auth_headers, apr))
    assert apr_names == ["04_rent.txt"]

    # May sync takes only 05_* — the 04_ file is NOT duplicated into May.
    client.post(f"/api/periods/{may}/sync", headers=auth_headers)
    may_names = sorted(d["original_filename"] for d in _docs(client, auth_headers, may))
    assert may_names == ["05_alza.txt", "05_shell.txt"]


def test_resync_shared_folder_is_idempotent(client, auth_headers, storage):
    may = _period(client, auth_headers, 2026, 5)
    _set_folder(client, auth_headers, may, "shared")
    shared = storage.DOCUMENTS_DIR / "shared"
    shared.mkdir(parents=True, exist_ok=True)
    (shared / "05_shell.txt").write_text("x", encoding="utf-8")

    first = client.post(f"/api/periods/{may}/sync", headers=auth_headers).json()
    assert first["imported"] == 1
    second = client.post(f"/api/periods/{may}/sync", headers=auth_headers).json()
    assert second["imported"] == 0  # already tracked, not re-added
