# Deployment Template

This project is designed to run as a single Docker web service with persistent
SQLite storage.

## Render Blueprint

Use `deploy/render.yaml` as a Render Blueprint. It builds the existing
`Dockerfile`, exposes `/api/health` for health checks, and mounts a small disk at
`/app/.data` for the SQLite database.

Required settings:

- `SUPPORT_DESK_HOST=0.0.0.0`
- `SUPPORT_DESK_DB=/app/.data/support_desk.sqlite3`
- `SUPPORT_DESK_KNOWLEDGE_PATH=data/knowledge_base.json`

Optional LLM settings:

- `SUPPORT_DESK_USE_LLM=true`
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`

Optional production settings:

- `SUPPORT_DESK_DATABASE_URL=postgresql://...` with `psycopg` installed in the image
- `SUPPORT_DESK_OCR_COMMAND` for scanned PDF OCR extraction
- Provider OAuth client IDs such as `GITHUB_CLIENT_ID`, `GMAIL_CLIENT_ID`, and `SLACK_CLIENT_ID`

To build the Docker image with optional Postgres support:

```bash
docker build --build-arg SUPPORT_DESK_EXTRAS=postgres -t multi-agent-support-desk .
```

The app also respects the common `PORT` environment variable used by hosted
platforms, so no custom start command is needed for providers that inject a
runtime port.

## Generic Docker Host

Build and run:

```bash
docker build -t multi-agent-support-desk .
docker run --rm -p 8080:8080 \
  -e SUPPORT_DESK_HOST=0.0.0.0 \
  -e SUPPORT_DESK_DB=/app/.data/support_desk.sqlite3 \
  -v support-desk-data:/app/.data \
  multi-agent-support-desk
```

Then open:

```text
http://localhost:8080
```
