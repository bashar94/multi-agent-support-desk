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
GET  /api/tickets
GET  /api/tickets/{id}
POST /api/tickets/analyze
POST /api/tickets/{id}/reanalyze
```

Example request:

```bash
curl -sS -X POST http://127.0.0.1:8080/api/tickets/analyze \
  -H "Content-Type: application/json" \
  -d '{"subject":"Cannot login","message":"Password reset is not working and our team is blocked."}'
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

## Project Structure

```text
supportdesk/     Agent pipeline, API server, SQLite storage
frontend/        Static dashboard served by the Python app
data/            Sample tickets and knowledge base articles
tests/           Standard-library unittest coverage
scripts/         Local development helpers
```

## Repository Goals

This project is built to be easy to understand, demo, fork, and extend:

- no required paid API key for the baseline demo
- readable agent boundaries
- testable business logic
- useful sample data
- clear open-source contribution path

## Roadmap

- Gmail, Slack, Zendesk, GitHub Issues, and Discord adapters
- RAG over Markdown and PDF knowledge bases
- Human approval workflow
- Team analytics and SLA reporting
- Hosted demo deployment template
