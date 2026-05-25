# Contributing

Thanks for improving Multi-Agent Support Desk.

## Local Development

```bash
python3 -m supportdesk.server
```

Run tests:

```bash
python3 -m unittest discover -s tests
```

## Useful Contribution Areas

- Add integrations for GitHub Issues, Slack, Gmail, Zendesk, Freshdesk, or Discord.
- Improve deterministic classification rules with more examples.
- Add knowledge base loaders for Markdown, CSV, or Notion exports.
- Add role-based human approval flows.
- Add analytics for SLA breaches and support load.
- Add provider-specific LLM adapters behind the existing optional interface.

## Pull Request Checklist

- Keep the default demo runnable without paid services.
- Add or update tests for changed agent behavior.
- Avoid storing secrets, customer data, or generated SQLite files.
- Update the README when commands, APIs, or environment variables change.
