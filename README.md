# Multi-Agent Support Desk

An open-source, practical multi-agent system for triaging customer support
tickets, finding relevant knowledge base context, drafting replies, checking
quality, and routing work to the right team.

The first version is intentionally dependency-light: it runs with the Python
standard library, SQLite, and a static web dashboard. It is useful without an
LLM key, while leaving clean extension points for OpenAI-compatible providers.

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

## Repository Goals

This project is built to be easy to understand, demo, fork, and extend:

- no required paid API key for the baseline demo
- readable agent boundaries
- testable business logic
- useful sample data
- clear open-source contribution path

## Roadmap

- Optional OpenAI-compatible response generation
- Gmail, Slack, Zendesk, GitHub Issues, and Discord adapters
- RAG over Markdown and PDF knowledge bases
- Human approval workflow
- Team analytics and SLA reporting
- Docker Compose deployment
