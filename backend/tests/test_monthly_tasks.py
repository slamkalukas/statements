"""Monthly tasks: a template in settings, copied into each month once.

The copy is the point — editing the template must not rewrite a month that has
already been worked on.
"""


def _period(client, auth_headers, year, month):
    return client.post("/api/periods", json={"year": year, "month": month},
                       headers=auth_headers).json()["id"]


def _set_template(client, auth_headers, titles):
    r = client.patch("/api/monthly-tasks", json={"titles": titles}, headers=auth_headers)
    assert r.status_code == 200
    return r.json()["titles"]


def _tasks(client, auth_headers, pid):
    r = client.get(f"/api/periods/{pid}/tasks", headers=auth_headers)
    assert r.status_code == 200
    return r.json()


def test_template_round_trips_and_cleans_up(client, auth_headers):
    saved = _set_template(client, auth_headers, ["DPH", "  Mzdy  ", "", "DPH", "Banka"])
    assert saved == ["DPH", "Mzdy", "Banka"]  # trimmed, blanks and dupes dropped
    assert client.get("/api/monthly-tasks", headers=auth_headers).json()["titles"] == saved


def test_a_month_materialises_the_template_once(client, auth_headers):
    _set_template(client, auth_headers, ["DPH", "Mzdy"])
    pid = _period(client, auth_headers, 2026, 11)

    first = _tasks(client, auth_headers, pid)
    assert [t["title"] for t in first] == ["DPH", "Mzdy"]
    assert [t["done"] for t in first] == [False, False]

    # Reading again must not duplicate them.
    again = _tasks(client, auth_headers, pid)
    assert [t["id"] for t in again] == [t["id"] for t in first]


def test_editing_the_template_leaves_an_existing_month_alone(client, auth_headers):
    _set_template(client, auth_headers, ["DPH"])
    old_month = _period(client, auth_headers, 2026, 11)
    assert [t["title"] for t in _tasks(client, auth_headers, old_month)] == ["DPH"]

    _set_template(client, auth_headers, ["DPH", "Mzdy", "Banka"])

    # The month already filed keeps its own list...
    assert [t["title"] for t in _tasks(client, auth_headers, old_month)] == ["DPH"]
    # ...while a new month picks up the current template.
    new_month = _period(client, auth_headers, 2026, 12)
    assert [t["title"] for t in _tasks(client, auth_headers, new_month)] == ["DPH", "Mzdy", "Banka"]


def test_ticking_a_task_and_leaving_a_note(client, auth_headers):
    _set_template(client, auth_headers, ["DPH"])
    pid = _period(client, auth_headers, 2026, 11)
    task = _tasks(client, auth_headers, pid)[0]

    r = client.patch(f"/api/period-tasks/{task['id']}",
                     json={"done": True, "note": "podane 25.11."}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["done"] is True
    assert r.json()["note"] == "podane 25.11."

    stored = _tasks(client, auth_headers, pid)[0]
    assert stored["done"] is True and stored["note"] == "podane 25.11."


def test_a_one_off_task_can_be_added_and_dropped(client, auth_headers):
    _set_template(client, auth_headers, ["DPH"])
    pid = _period(client, auth_headers, 2026, 11)

    r = client.post(f"/api/periods/{pid}/tasks", json={"title": "Danove priznanie"},
                    headers=auth_headers)
    assert r.status_code == 201
    extra = r.json()
    assert [t["title"] for t in _tasks(client, auth_headers, pid)] == ["DPH", "Danove priznanie"]

    assert client.delete(f"/api/period-tasks/{extra['id']}", headers=auth_headers).status_code == 204
    assert [t["title"] for t in _tasks(client, auth_headers, pid)] == ["DPH"]
    # The template is untouched, so next month still gets it.
    assert client.get("/api/monthly-tasks", headers=auth_headers).json()["titles"] == ["DPH"]


def test_a_closed_month_is_read_only_and_gains_no_checklist(client, auth_headers):
    _set_template(client, auth_headers, ["DPH"])
    pid = _period(client, auth_headers, 2026, 11)
    task = _tasks(client, auth_headers, pid)[0]
    assert client.post(f"/api/periods/{pid}/close", headers=auth_headers).status_code == 200

    # Still visible, but not changeable.
    assert [t["id"] for t in _tasks(client, auth_headers, pid)] == [task["id"]]
    assert client.patch(f"/api/period-tasks/{task['id']}", json={"done": True},
                        headers=auth_headers).status_code == 409

    # A month closed before it ever had tasks does not acquire them afterwards.
    other = _period(client, auth_headers, 2026, 12)
    assert client.post(f"/api/periods/{other}/close", headers=auth_headers).status_code == 200
    assert _tasks(client, auth_headers, other) == []
