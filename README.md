# Statements — Monthly bank-statement & document archive

A small, self-hosted web app for the monthly bookkeeping ritual: each month you
export a **bank statement** and gather the **invoices and bills** that back it
up. Statements parses the statement into its transactions, matches your uploaded
documents to them, and tells you **which outgoing payments are still missing a
supporting invoice or bill** — the whole point of the app. Files live on an
**external folder mapped from your host**, so they stay yours.

It runs entirely locally with **Docker Compose**, can be published to **GitHub**
and **Docker Hub**, and the document folder is just a directory on your disk —
your files stay yours.

---

## Stack

| Layer    | Technology |
|----------|-----------|
| Frontend | React 18 + Vite, React Router, custom CSS design system, served by **nginx** |
| Backend  | **FastAPI** (Python 3.12), SQLAlchemy 2.0, Pydantic v2, JWT sessions |
| Database | **PostgreSQL 16** with a persistent named volume (metadata + audit log) |
| Files    | Stored on a host folder mapped into the container at `/data/documents` |
| Runtime  | **Docker Compose** (three services: `db`, `backend`, `frontend`) |

nginx serves the built React app and reverse-proxies `/api/*` to the backend, so
the browser only ever talks to one origin.

---

## How it works

1. **Create a month** (e.g. June 2026). Each month is *open* (editable) or
   *closed* (archived/locked, to prevent accidental changes).
2. **Import the bank statement.** The statement's transactions are parsed into a
   checklist. Formats are detected automatically:
   - ISO 20022 **CAMT.053 XML** (e.g. Tatra Banka),
   - **OFX 2.x XML** (e.g. Tatra Banka credit-card export),
   - **George / Erste JSON** (Slovenská sporiteľňa),
   - generic **CSV** (date / amount / description columns auto-detected).
3. **Reconcile.** Every **outgoing payment** needs a supporting invoice/bill. The
   month view lists payments with the **missing** ones first. Upload an invoice
   and the app **reads its total** (and date) and **auto-links the payment with
   the same amount** when the match is unambiguous; otherwise it suggests
   candidates or you attach a file directly. **Sync from folder** pulls in files
   dropped into the month folder and reads + pairs each one in the same step;
   **Scan & auto-match** does the same pass on demand for anything still unpaired.
   Payments that legitimately have no invoice (bank fees, charges, FX costs) can
   be marked **"No invoice"** — they drop out of the missing report and are not
   auto-matched. Incoming/transfer lines are ignored.
   A month can hold **multiple accounts** (e.g. "Bank account" + "Credit card"):
   each import is tagged with an account name and gets its own statement and
   missing list, while documents and auto-matching are shared across the month.
   A payment posted in one month but belonging to another's books can be **moved
   to another month** (it keeps its date; re-importing the statement won't
   recreate it).
   - Digital PDFs are read from their text layer; **scanned, image-only PDFs and
     photos are read with OCR** (Tesseract, Slovak + English). Disable with
     `OCR_ENABLED=0`, or change languages with `OCR_LANG` (must match an
     installed pack).
4. **See what's missing.** Each month shows its count of unmatched payments, and
   the dashboard rolls up the total missing across all months — so "which
   invoices am I still missing?" is answered at a glance.
5. **Browse the files.** The **Files** page is a read-only browser of the
   documents root — navigate the `YYYY/MM` folders with a breadcrumb and
   download any file, all confined to the root (no path traversal).

Each month stores its files under `<root>/YYYY/MM/` by default. The default
**layout is configurable** in Settings — a template with `{YYYY}`/`{MM}`
placeholders (e.g. `{YYYY}/{MM}` or `#{YYYY}/Vydavky`) that every month follows
unless it has its own override. The per-month subfolder is also **editable per
month** (e.g. `2026/04-vat`). Either change affects new uploads and folder sync;
already-stored files stay where they are. (The host folder itself is read-only —
it's fixed by the `DOCUMENTS_DIR_HOST` volume mount.)

**Sharing one folder across months:** point several months at the same folder
and name files with a **leading month** (e.g. `05_shell.pdf`). Sync only picks up
files whose prefix matches the month, so each month claims just its own files
with no cross-month duplication. (Files with no month prefix have no month signal,
so in a shared folder they'd be claimed by every month — prefix them.)

**Subfolders are included.** Sync is recursive, so files filed into a subfolder
(e.g. a `hotove` "done" folder) are still checked. If you move an already-tracked
file into such a subfolder, sync follows it — its link/download stays valid
rather than creating a duplicate.

Documents are tagged **invoice**, **receipt**, **bank statement**, or **other**,
with an optional date/amount/note. Files are written to your mapped folder; the
database holds the index, the parsed statement lines, the document↔payment links,
and an append-only **audit log** of every create / delete / link.

### Where files land on disk

Uploads are organized **by year and month**, mirroring how you'd file paper:

```
<DOCUMENTS_DIR_HOST>/
  2026/
    06/
      statement.pdf
      acme-invoice.pdf
      receipt-trains.pdf
    07/
      ...
```

Filenames are sanitized (no path traversal) and de-duplicated (` (1)`, ` (2)`
suffixes). Because the files are plain files on your host folder, you can browse,
sync, or back them up with whatever tools you already use.

---

## Running it

**Prerequisites:** Docker Desktop (or Docker Engine) with the Compose plugin.
Nothing else — Python and Node dependencies are installed inside the containers.

```bash
# 1. (optional) set your own secrets / port / documents folder
cp .env.example .env

# 2. build and start everything
docker compose up --build
```

Then open **http://localhost:3000** and sign in with the admin account
(default `admin@example.com` / `changeme` — change these in `.env` before first
boot, or change the password later from **Settings**).

The API is also exposed at **http://localhost:8000** (interactive docs at
http://localhost:8000/docs).

By default the documents folder is `./documents` next to the compose file. Point
it anywhere on your machine by setting `DOCUMENTS_DIR_HOST` in `.env`:

```bash
DOCUMENTS_DIR_HOST=/mnt/nas/accounting        # Linux / NAS
DOCUMENTS_DIR_HOST=C:/Users/you/Documents/Books   # Windows
```

To stop: `Ctrl-C`, then `docker compose down`. The database persists in the
`db_data` volume and your files persist in the mapped folder. To wipe the
database (not your files), run `docker compose down -v`.

### Configuration

Everything is configurable through environment variables, each with a built-in
default — so the stack runs with zero config. Copy `.env.example` to `.env` and
override only what you need.

| Variable | Default | Purpose |
|----------|---------|---------|
| `ENV` | `development` | `development` auto-creates tables and tolerates a missing key. `production` **refuses to start** without a strong `SECRET_KEY` and an `ADMIN_PASSWORD`. |
| `SECRET_KEY` | _(ephemeral in dev)_ | Signs JWT sessions. In production must be ≥32 random chars — e.g. `openssl rand -hex 32`. |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | `admin@example.com` / `changeme` | The single admin account, created on first boot only. Change the password later from Settings. |
| `DOCUMENTS_DIR_HOST` | `./documents` | **Host folder** mapped to `/data/documents` — where your files are filed. |
| `MAX_UPLOAD_MB` | `25` | Per-file upload size cap (kept in sync with nginx). |
| `OCR_ENABLED` | `1` | OCR scanned/image-only invoices (`0` to disable). |
| `OCR_LANG` | `slk+eng` | Tesseract languages (must match installed packs). |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `statements` | Database credentials and name. |
| `POSTGRES_VERSION` | `16-alpine` | Tag of the official `postgres` image. |
| `DB_HOST` / `DB_PORT` | `127.0.0.1` / `5432` | Host interface + port Postgres is published on (dev stack). |
| `API_PORT` | `8000` | Host port for the API. |
| `APP_PORT` | `3000` | Host port for the web app. |
| `BACKEND_IMAGE` / `FRONTEND_IMAGE` | `slamkalukas/statements-*:latest` | Image names/tags to build, pull, and push. |
| `RESTART_POLICY` | `unless-stopped` | Compose restart policy for all services. |

The login endpoint (`/api/auth/login`) is rate-limited per IP.

### Production deployment

`docker-compose.prod.yml` is a pull-only, production-flavored example: it uses
prebuilt images instead of building, runs `ENV=production`, **requires** a
`SECRET_KEY`, a real `POSTGRES_PASSWORD`, and an `ADMIN_PASSWORD` (startup fails
without them), applies migrations on boot, and does not expose Postgres to the
host.

```bash
cp .env.example .env
# set at least these in .env (or the environment):
#   SECRET_KEY=$(openssl rand -hex 32)
#   POSTGRES_PASSWORD=<something strong>
#   ADMIN_PASSWORD=<your admin password>
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

### Testing

```bash
cd backend
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest
```

The suite covers authentication, the month lifecycle, document upload / download
/ delete (filename sanitization, size cap, closed-month locking), and the
reconciliation flow — parsing CAMT / George-JSON / CSV statements, counting
missing outgoing payments, and linking/unlinking documents — using an in-memory
SQLite database and a temp documents folder, no running Postgres required.

### Database migrations

Schema is managed by **Alembic**. In development the app auto-creates tables for
convenience; in production (`ENV=production`) it does not. The
`docker-compose.prod.yml` stack runs `alembic upgrade head` automatically on
boot. To apply migrations manually:

```bash
cd backend
DATABASE_URL=postgresql+psycopg2://statements:statements@localhost:5432/statements alembic upgrade head
```

When you change a model, generate a migration with
`alembic revision --autogenerate -m "describe change"` and review it before
committing.

### Backups

`scripts/backup.sh` dumps the database to a timestamped gzip file;
`scripts/restore.sh` restores one. Both talk to the running `db` container:

```bash
./scripts/backup.sh                          # -> ./backups/statements-<timestamp>.sql.gz
./scripts/restore.sh backups/statements-….sql.gz
```

These cover the **metadata** (months, the document index, the audit log). Your
actual document files live on the `DOCUMENTS_DIR_HOST` folder — back that folder
up with your normal file backups.

---

## Project layout

```
statements-app/
├── docker-compose.yml        # dev stack (builds from source)
├── docker-compose.prod.yml   # production example (pull-only, migrates on boot)
├── .env.example              # every configurable variable, with defaults
├── scripts/                  # backup.sh / restore.sh
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic/              # migrations (alembic upgrade head)
│   └── app/
│       ├── main.py          # app startup, DB init + admin seed, router wiring
│       ├── database.py      # engine / session / Base
│       ├── models.py        # User, Period, Document, StatementLine, AuditLog
│       ├── storage.py       # the file layer (save/resolve/delete on the host folder)
│       ├── statements.py    # statement parsing + format auto-detection
│       ├── camt.py / slsp.py# CAMT.053 XML and George JSON parsers
│       ├── schemas.py       # Pydantic request/response models
│       ├── auth.py          # password hashing + JWT create/decode
│       ├── deps.py          # current-user, period guards, rate limiting
│       ├── audit.py         # append-only audit log helper
│       ├── seed.py          # idempotent first-boot admin user
│       └── routers/         # auth, periods, documents, reconcile, dashboard
└── frontend/
    ├── Dockerfile           # multi-stage: vite build -> nginx
    ├── nginx.conf           # SPA fallback + /api proxy
    └── src/
        ├── App.jsx          # auth gate + routes
        ├── api.js           # fetch wrapper (injects token, blob download)
        ├── context/         # AuthContext
        ├── components/      # Layout (sidebar + header), shared UI
        └── pages/           # Login, Dashboard, Periods, PeriodDetail (reconcile), Settings
```

---

## Pushing to your own GitHub

From inside the `statements-app/` directory:

```bash
git init
git add .
git commit -m "Statements: monthly bank-statement & document archive"

# create an empty repo on GitHub first, then point at it:
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

The included `.gitignore` keeps `node_modules`, build output, `__pycache__`,
your `.env`, the `documents/` folder, and `backups/` out of the repo.

## Publishing images to Docker Hub

The Compose services are tagged via `BACKEND_IMAGE` / `FRONTEND_IMAGE`
(defaulting to the `slamkalukas` namespace), so after a build you can push both
images directly:

```bash
docker login
docker compose build
docker compose push
```

That publishes two repositories to your Docker Hub: `statements-backend` and
`statements-frontend`. Override `BACKEND_IMAGE` / `FRONTEND_IMAGE` in `.env` to
use your own namespace or a pinned version tag.

To deploy from published images on another machine, copy
`docker-compose.prod.yml` and `.env` to the host and run
`docker compose -f docker-compose.prod.yml up -d`. It pulls the images, applies
migrations, and runs in production mode — no source checkout needed.
