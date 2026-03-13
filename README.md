# Mini Cloud Storage Server

A Google Drive-style file storage backend built with FastAPI, PostgreSQL, and Nginx — fully containerised with Docker Compose.

---

## Architecture

```
Client → Nginx (port 80) → FastAPI/Gunicorn (port 8000) → PostgreSQL
                                      ↓
                               /app/storage (Docker volume)
```

| Service | Technology         | Role                                  |
|---------|--------------------|---------------------------------------|
| `nginx` | Nginx 1.25         | Reverse proxy, upload size gate       |
| `api`   | FastAPI + Gunicorn | REST API, file handling logic         |
| `db`    | PostgreSQL 16      | File & folder metadata                |

---

## Quick Start (Windows / Mac / Linux)

### Prerequisites
- Docker Desktop running

### 1. Extract and enter the project

```powershell
# Windows
tar -xzf ministorage.tar.gz
cd ministorage\ministorage
```
```bash
# Mac / Linux
tar -xzf ministorage.tar.gz
cd ministorage/ministorage
```

### 2. Start all services

```bash
docker compose up --build
```

Wait for all three services to show as healthy (about 30 seconds).

### 3. Verify

```bash
curl http://localhost/health
# → {"status":"ok","db":"ok","version":"1.0.0"}

# Browser: http://localhost/docs  ← interactive Swagger UI
```

---

## API Reference

Base URL: `http://localhost`

### Upload a file

```bash
curl -X POST http://localhost/files/upload \
  -F "file=@/path/to/yourfile.pdf"

# Upload into a specific folder
curl -X POST "http://localhost/files/upload?folder_id=<folder-id>" \
  -F "file=@photo.jpg"
```

### List files

```bash
# All files (newest first, 20 per page)
curl http://localhost/files

# Search by filename
curl "http://localhost/files?search=report"

# Filter by folder
curl "http://localhost/files?folder_id=<folder-id>"

# Root-level only (no folder)
curl "http://localhost/files?folder_id=none"

# Pagination
curl "http://localhost/files?page=2&limit=10"
```

### Download a file

```bash
curl -OJ http://localhost/files/<file-id>
# -O saves to disk, -J uses the server filename
```

### Rename a file

```bash
curl -X PATCH http://localhost/files/<file-id>/rename \
  -H "Content-Type: application/json" \
  -d '{"filename": "new-name.pdf"}'
```

### Delete a file

```bash
curl -X DELETE http://localhost/files/<file-id>
# → 204 No Content
```

### Create a folder

```bash
# Top-level folder
curl -X POST http://localhost/folders \
  -H "Content-Type: application/json" \
  -d '{"name": "Documents"}'

# Nested folder
curl -X POST http://localhost/folders \
  -H "Content-Type: application/json" \
  -d '{"name": "Reports", "parent_id": "<parent-folder-id>"}'
```

### List folders

```bash
# Top-level folders
curl http://localhost/folders

# Children of a folder
curl "http://localhost/folders?parent_id=<folder-id>"

# All folders
curl "http://localhost/folders?parent_id=all"
```

---

## Configuration (.env)

| Variable             | Default       | Description                      |
|----------------------|---------------|----------------------------------|
| `POSTGRES_USER`      | `storageuser` | DB username                      |
| `POSTGRES_PASSWORD`  | `storagepass` | DB password                      |
| `POSTGRES_DB`        | `ministorage` | DB name                          |
| `STORAGE_ROOT`       | `/app/storage`| Where uploaded files are saved   |
| `MAX_UPLOAD_SIZE_MB` | `100`         | Per-file size limit              |
| `LOG_LEVEL`          | `INFO`        | Python log level                 |
| `DEFAULT_PAGE_SIZE`  | `20`          | Files returned per page          |
| `MAX_PAGE_SIZE`      | `100`         | Max files per page               |

---

## File Storage Layout

```
/app/storage/
├── root/                    ← files with no folder
│   ├── a3f1c8d2...pdf
│   └── 9b7e2f01...jpg
└── <folder-id>/             ← files inside a folder
    └── 4d82a1b0...docx
```

Files are stored with UUID-based names on disk. The original filename is preserved only in PostgreSQL — which means renames are instant (no disk I/O).

---

## Development (without Docker)

```bash
# 1. Start only PostgreSQL
docker compose up db -d

# 2. Install deps
pip install -r requirements.txt

# 3. Set env vars
set POSTGRES_HOST=localhost    # Windows
export POSTGRES_HOST=localhost # Mac/Linux

# 4. Run the API
uvicorn api.main:app --reload --port 8000
```

---

## Useful Commands

```bash
# View logs
docker compose logs -f api
docker compose logs -f nginx

# Open a DB shell
docker compose exec db psql -U storageuser -d ministorage

# Useful SQL
# SELECT id, filename, size, folder_id FROM files ORDER BY created_at DESC LIMIT 20;
# SELECT * FROM folders;

# Tear down (keep data)
docker compose down

# Tear down (delete all data)
docker compose down -v
```
