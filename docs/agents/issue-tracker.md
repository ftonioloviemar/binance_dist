# Issue Tracker

The issue tracker for this repository is the internal markdown kanban under `workflow/kanban/`.

Do not create GitHub Issues by default, even though the repo has a GitHub remote. When a skill asks for the issue tracker, map that to kanban cards:

- proposed work: `workflow/kanban/00_pending_approval/`
- approved executable work: `workflow/kanban/02_ready/`
- active work: `workflow/kanban/03_doing/`
- blocked human decision: `workflow/kanban/07_needs_human/`
- completed work: `workflow/kanban/05_done/`

Cards should be small enough to verify and commit independently.
