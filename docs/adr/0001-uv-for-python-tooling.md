# 0001 — uv for Python dependencies and tooling

**Status:** Accepted (2026-10-04)

## Context
We need reproducible installs for local dev, CI and Docker, plus Python version management. Candidates: Poetry, pip-tools, uv.

## Decision
Use **uv** with a committed `uv.lock`; standard `pyproject.toml` metadata; `uv_build` backend.

## Consequences
- Much faster resolves and installs; small, cache-friendly Docker layers (`uv sync --frozen`).
- One tool replaces pyenv/pip/Poetry/pipx.
- `uv lock --check` runs in pre-commit and CI so the lockfile can't drift.
- Contributors must install uv.
