# Repository Guidelines

## Hermes Profile Collaboration Repositories

- English workflow latest read-only source: `/Users/yelin/Developer/linye-english-news-workflow`. Never modify, commit, or push in this directory. Do not use the old `/Users/yelin/Developer/agent-tools/express` directory as evidence.
- Social Auto Upload: `/Users/yelin/Developer/agent-tools/social-auto-upload`.
- Browser Harness: `/Users/yelin/Developer/agent-tools/browser-harness`.

## Project Structure & Module Organization

The Python application lives primarily at the repository root: `sau_cli.py` provides the `sau` command, `sau_backend.py` hosts the Flask API, and `uploader/`, `utils/`, and `myUtils/` contain platform automation and shared helpers. The Vue 3 admin UI is in `sau_frontend/`. Put Python tests in `tests/`, matching the target area (for example, `tests/test_sau_bilibili_cli.py`). SQLite setup code and the local database belong in `db/`; runtime media, cookies, and logs belong in their respective ignored directories.

## Build, Test, and Development Commands

Use Python 3.10–3.12. Install backend dependencies with `pip install -r requirements.txt`, then install browser support with `playwright install chromium`. Initialize local storage with `python db/createTable.py` and start the API with `python sau_backend.py` (port 5409).

Run all backend tests with `python -m unittest discover -s tests`. Run a focused suite with `python -m unittest tests.test_sau_bilibili_cli`. For the frontend, run `cd sau_frontend && npm install`, then `npm run dev`; use `npm run build` to verify a production build.

## Coding Style & Naming Conventions

Follow the existing Python style: four-space indentation, `snake_case` functions and modules, `PascalCase` classes, and explicit imports. Keep browser-automation code asynchronous and isolate platform-specific behavior inside its uploader package. Use descriptive CLI flags and preserve current user-facing terminology. Vue components should follow the existing directory conventions and use PascalCase component filenames. No formatter or linter is configured; keep diffs narrowly scoped and consistent with adjacent code.

## Testing Guidelines

Tests use the standard-library `unittest` framework. Name files `test_*.py`, test classes `*Tests`, and test methods `test_*`. Mock browser, filesystem, and network boundaries with `unittest.mock`; tests must not require real credentials, cookies, or external platform access. Add regression coverage for each behavioral change, especially CLI parsing and uploader metadata flows.

## Fork README Synchronization

This repository is a maintained fork. Every update to code, configuration, tests, supported platforms, CLI behavior, browser/CDP behavior, account verification, publishing workflows, installation, limitations, or other repository behavior must update `README.md` in the same change. Work is not complete until the README has been checked against the current implementation and tests and accurately describes this fork. Do not document upstream-only, planned, or unverified capabilities as implemented.

## Commit & Pull Request Guidelines

Recent history uses concise imperative Conventional Commit-style messages, often scoped by platform: `fix(douyin): ...`, `fix(youtube): ...`, or `fix: ...`. Keep each commit focused. Pull requests should explain the behavioral change, list commands run, link relevant issues, and include screenshots for frontend changes. Never commit `conf.py`, cookies, database contents, videos, or other credentials.

## Configuration & Security

Copy `conf.example.py` to `conf.py` for local settings. Treat account cookie files and generated QR codes as sensitive local artifacts; redact them from logs, issues, and review screenshots.
