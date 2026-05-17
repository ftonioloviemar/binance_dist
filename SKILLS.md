# Local Skill Catalog

Use this catalog to decide which available Codex/project skills apply in this repository.

## Always Relevant

- `superpowers:systematic-debugging`: use before fixing unexpected behavior, failed audits, rejected orders, timeouts, or strategy drift.
- `superpowers:test-driven-development`: use before changing production behavior in Python code.
- `superpowers:verification-before-completion`: use before claiming a card is complete.
- `run-kanban-loop`: use when executing approved kanban cards continuously.

## Planning And Orchestration

- `superpowers:writing-plans`: use for multi-step changes that need a saved plan.
- `superpowers:subagent-driven-development`: use when an implementation plan has independent tasks and review gates.
- `grill-with-docs`: use when strategy or workflow language is ambiguous and a decision should be captured in docs.
- `setup-matt-pocock-skills`: use if `docs/agents/` needs to be regenerated because the tracker or domain-doc layout changed.

## Security And Trading Safety

- `security-best-practices`: use for API key handling, account permissions, secret logging, and live-trading safeguards.
- `security-threat-model`: use before expanding automation that can move funds, trade live, or change API permissions.

## Optional Utilities

- `zoom-out`: use when a module's role in the trading flow is unclear.
- `pdf`, `spreadsheets`, `playwright`: use only when the task actually involves those artifacts or browser validation.

## Local Decisions

- The issue tracker for this repo is `workflow/kanban/`, not GitHub Issues.
- TDD cards should name the exact test file and command.
- Subagents are useful for non-trivial behavior changes, but avoid them for simple docs-only edits.
