# Multi-Agent Support Desk

An open-source, practical multi-agent system for triaging customer support
tickets, finding relevant knowledge base context, drafting replies, checking
quality, and routing work to the right team.

The first version is intentionally dependency-light: it runs with the Python
standard library, SQLite, and a static web dashboard. It is useful without an
LLM key, while leaving clean extension points for OpenAI-compatible providers.

![Multi-Agent Support Desk dashboard preview](docs/dashboard-preview.svg)

## What It Does

- Classifies support tickets by category, sentiment, severity, and urgency.
- Searches a local knowledge base for grounded context.
- Identifies missing details and escalation risks.
- Drafts a customer-facing reply.
- Reviews the draft for tone, completeness, and hallucination risk.
- Routes the ticket to an owner team with tags and SLA guidance.
- Stores tickets and agent traces in SQLite for demos and audits.
- Imports Gmail, Slack, Zendesk, GitHub Issues, and Discord payloads as tickets.
- Tracks human approval state before a drafted reply is send-ready.
- Sends approved replies through a safe outbox, SMTP, or a generic outbound webhook.
- Tracks ticket workflow status from open to reply-ready, waiting, resolved, or closed.
- Shows queue analytics by priority, owner team, SLA, action, approval, and workflow state.
- Supports OAuth installation flow records for provider adapters.
- Supports reviewer accounts and approval audit logs.
- Can run on SQLite by default or an optional Postgres backend.

## Agent Pipeline

```mermaid
flowchart LR
    A["Ticket Intake"] --> B["Intake Agent"]
    B --> C["Knowledge Agent"]
    C --> D["Diagnostic Agent"]
    D --> E["Response Agent"]
    E --> F["Quality Agent"]
    F --> G["Routing Agent"]
    G --> H["Final Triage Packet"]
```

## Quick Start

```bash
python3 -m supportdesk.server
```

Then open:

```text
http://127.0.0.1:8080
```

Run tests:

```bash
python3 -m unittest discover -s tests
```

## Docker

```bash
docker compose up --build
```

## API

```text
GET  /api/health
GET  /api/sample-tickets
GET  /api/knowledge
GET  /api/analytics
GET  /api/oauth/providers
GET  /api/oauth/installs
GET  /api/reviewers
GET  /api/audit-log
GET  /api/outbox
GET  /api/tickets
GET  /api/tickets/{id}
POST /api/tickets/analyze
POST /api/tickets/{id}/reanalyze
POST /api/tickets/{id}/approval
POST /api/tickets/{id}/send-reply
POST /api/tickets/{id}/status
POST /api/oauth/{provider}/begin
GET  /api/oauth/{provider}/callback
POST /api/oauth/{provider}/callback
POST /api/reviewers
POST /api/integrations/gmail
POST /api/integrations/slack
POST /api/integrations/zendesk
POST /api/integrations/github-issues
POST /api/integrations/discord
```

Example request:

```bash
curl -sS -X POST http://127.0.0.1:8080/api/tickets/analyze \
  -H "Content-Type: application/json" \
  -d '{"subject":"Cannot login","message":"Password reset is not working and our team is blocked."}'
```

Approval update:

```bash
curl -sS -X POST http://127.0.0.1:8080/api/tickets/TICKET_ID/approval \
  -H "Content-Type: application/json" \
  -d '{"status":"approved","reviewer":"lead@example.com","note":"Ready to send."}'
```

Supported approval statuses are `pending`, `approved`, `changes_requested`,
and `escalated`.

Reviewer accounts are managed through `POST /api/reviewers`. Approval changes
write audit events, available from `GET /api/audit-log`.

## Solo Developer Workflow

The intended daily loop is:

1. Send tickets from the dashboard or an adapter endpoint.
2. Let the agents classify, search knowledge, diagnose, draft, check, and route.
3. Approve, request edits, or escalate the generated reply.
4. Send the approved reply. By default it is recorded in the outbox as a dry run.
5. Mark the ticket as waiting for the customer, resolved, or closed.

Send an approved reply:

```bash
curl -sS -X POST http://127.0.0.1:8080/api/tickets/TICKET_ID/send-reply \
  -H "Content-Type: application/json" \
  -d '{"sender":"lead@example.com"}'
```

Update workflow status:

```bash
curl -sS -X POST http://127.0.0.1:8080/api/tickets/TICKET_ID/status \
  -H "Content-Type: application/json" \
  -d '{"status":"resolved","actor":"lead@example.com","note":"Customer confirmed."}'
```

Supported workflow statuses are `open`, `reply_ready`, `waiting_customer`,
`resolved`, and `closed`.

## Reply Delivery

The default reply mode is safe for local development and open-source demos:

```bash
export SUPPORT_DESK_REPLY_MODE=dry_run
```

Dry-run replies are stored in the outbox and visible from the ticket response or
`GET /api/outbox`. To send email, set `SUPPORT_DESK_REPLY_MODE=send` and SMTP
settings:

```bash
export SUPPORT_DESK_REPLY_MODE=send
export SMTP_HOST=smtp.example.com
export SMTP_PORT=587
export SMTP_USERNAME=apikey
export SMTP_PASSWORD=...
export SMTP_FROM=support@example.com
```

For non-email workflows, set `SUPPORT_DESK_OUTBOUND_WEBHOOK_URL` to post the
approved reply payload to a tool such as n8n, Make, Zapier, or a custom worker.

## Intake Adapters

Provider webhook or fixture payloads can be sent to:

```text
POST /api/integrations/gmail
POST /api/integrations/slack
POST /api/integrations/zendesk
POST /api/integrations/github-issues
POST /api/integrations/discord
```

The adapters normalize external payloads into the same `Ticket` model used by
the dashboard, preserving provider metadata in the stored triage packet.

## OAuth Installation

Provider installation flows are available for Gmail, Slack, Zendesk, GitHub, and
Discord:

```bash
curl -sS -X POST http://127.0.0.1:8080/api/oauth/github/begin \
  -H "Content-Type: application/json" \
  -d '{"installed_by":"lead@example.com"}'
```

The response includes an `authorization_url` and server-side install record.
After the provider redirects back with `code` and `state`, the callback endpoint
marks the install as connected. Set provider client IDs through environment
variables such as `GITHUB_CLIENT_ID`, `GMAIL_CLIENT_ID`, and `SLACK_CLIENT_ID`.

## Document Knowledge Base

The default knowledge base is JSON. To load a directory of Markdown and
searchable PDF articles, point `SUPPORT_DESK_KNOWLEDGE_PATH` at a folder:

```bash
export SUPPORT_DESK_KNOWLEDGE_PATH=./knowledge
python3 -m supportdesk.server
```

Markdown files may include simple front matter:

```markdown
---
title: Refund Playbook
category: billing
team: Revenue Operations
keywords: [refund, duplicate charge, invoice]
---

# Refund Playbook

Confirm invoice evidence before promising a refund.
```

Searchable PDFs are loaded without external dependencies. For PDF metadata, add
a sidecar JSON file with the same basename, for example `refund-guide.json` next
to `refund-guide.pdf`.

For scanned PDFs, add a same-name `.txt` OCR sidecar, or set
`SUPPORT_DESK_OCR_COMMAND` to a command that emits text to stdout or writes to
`{output}`. The PDF path is available as `{input}`.

```bash
export SUPPORT_DESK_OCR_COMMAND='tesseract {input} stdout'
```

## Optional LLM Drafting

The default response agent is deterministic. To test an OpenAI-compatible
provider for final draft generation:

```bash
cp .env.example .env
export SUPPORT_DESK_USE_LLM=true
export OPENAI_API_KEY=...
python3 -m supportdesk.server
```

If the provider call fails, the system falls back to the deterministic draft and
records the error in the response agent output.

## Database Backends

SQLite is the default and needs no setup:

```bash
export SUPPORT_DESK_DB=.data/support_desk.sqlite3
```

For URL-based configuration:

```bash
export SUPPORT_DESK_DATABASE_URL=sqlite:///.data/support_desk.sqlite3
```

For Postgres, install `psycopg` in your deployment image and set:

```bash
pip install ".[postgres]"
export SUPPORT_DESK_DATABASE_URL=postgresql://user:pass@host:5432/supportdesk
```

## Project Structure

```text
supportdesk/     Agent pipeline, API server, SQLite storage
frontend/        Static dashboard served by the Python app
data/            Sample tickets and knowledge base articles
tests/           Standard-library unittest coverage
scripts/         Local development helpers
deploy/          Docker hosting template and deployment notes
```

## Repository Goals

This project is built to be easy to understand, demo, fork, and extend:

- no required paid API key for the baseline demo
- readable agent boundaries
- testable business logic
- useful sample data
- clear open-source contribution path
