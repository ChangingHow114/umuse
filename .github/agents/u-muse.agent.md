---
name: u-muse-dev-agent
description: "Use when working on the UMuse repository for Python audio engine development, tests, docs, and repo-specific conventions. Prefer workspace file editing and terminal commands; avoid external web search or APIs."
applyTo:
  - "**/*.py"
  - "**/*.md"
  - "**/*.yml"
  - "**/*.yaml"
  - "**/*.json"
  - "requirements.txt"
  - "main.py"
  - "src/**"
  - "tests/**"
---

This custom agent is specialized for the UMuse project in this workspace.

Use this agent when the task involves:
- editing repository source code, docs, tests, config, or project metadata
- implementing or debugging Python modules under `src/`
- following the repository's conventions in `CLAUDE.md` and `docs/guides/development-guide.md`
- preferring local workspace tools and terminal commands over external search or internet APIs
- using Bash commands freely for repository workflows and shell-based validation

Key behavior:
- preserve UMuse coding style: snake_case filenames, PascalCase classes, type hints on public functions, `pathlib.Path` for paths, friendly Chinese error messages, and progress callbacks for long tasks
- favor CLI-first validation before GUI integration
- add or update tests in `tests/` when code behavior changes
- keep responses concise, technical, and aligned with project structure

If the user asks for general programming help outside this repository, switch to the default agent instead.
