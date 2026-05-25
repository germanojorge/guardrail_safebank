🏠 [Home](../README_FOR_HUMANS.md) · [Getting Started](../GETTING_STARTED.md) · [Architecture](../ARCHITECTURE.md) · [Tech](../TECH_STACK.md) · [Integrations](../INTEGRATIONS.md) · [Repo Map](../MAP/repo_map.md) · [Links](../LINKS.md)

---

# Assumptions

These are Buddy's guesses. They are not facts. Verify before relying on them.

---

- **This is a tutorial / educational project, not production software.** Evidence: the project name contains "Tutorial", `main.py` is a placeholder, tests use print statements instead of a test framework. But this was not stated explicitly anywhere in the code.

- **`uv` is the intended package manager.** Evidence: `uv.lock` is committed and `pyproject.toml` is present. No `requirements.txt` or `Makefile` was found. But the README is empty (one blank line), so no instructions were provided to confirm this.

- **The Detoxify `'original'` model is a deliberate choice.** Detoxify supports several models (`original`, `unbiased`, `multilingual`). The code uses `'original'`. Since the project handles both English and Portuguese text, `'multilingual'` might have been a better fit — but this may be intentional to keep it simple for tutorial purposes.

- **The project targets a Brazilian Portuguese audience.** Evidence: variable names, comments, and blocked-topic examples (`bomba`, `arma`, `matar`, `senha`) are in Portuguese, and PII patterns include CPF (a Brazilian ID format). However, the injection keyword list includes both English and Portuguese phrases.

- **There is no test runner in CI.** Based on the absence of a `Makefile`, `tox.ini`, or pytest config, and the print-based test style. Could not verify without reading `.github/`.

- **`config.yaml` is meant to be created from scratch by each developer.** Evidence: it is gitignored and there is no `config.yaml.example` or template file in the repo. Steps to create it are only described in comments in the source code.
