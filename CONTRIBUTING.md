# Contributing to Research-to-Report

Thank you for your interest in contributing. This document covers how to get involved, what we expect from contributors, and how to submit changes.

---

## Code of Conduct

This project is committed to providing a welcoming and respectful environment for everyone. By participating — whether by filing issues, submitting pull requests, joining discussions, or any other form of engagement — you agree to the following:

**Be respectful.** Disagreement is fine; disrespect is not. Critique ideas, not people.

**Be constructive.** Feedback should help the recipient improve. If something is wrong, explain why and suggest a better path.

**Be inclusive.** This project welcomes contributors regardless of background, experience level, nationality, gender, religion, or any other personal characteristic. Language that excludes or demeans others has no place here.

**Be honest.** Do not misrepresent your work, others' work, or the state of the project. If you are unsure about something, say so.

**Be patient.** Maintainers and contributors are often working in their spare time. Allow reasonable time for responses before following up.

Behaviour that violates these principles — including harassment, sustained disruption, or personal attacks — will result in removal from the project at the maintainers' discretion.

---

## How to Contribute

### Reporting bugs

Open a [GitHub Issue](../../issues) with:
- A clear, descriptive title
- Steps to reproduce the problem
- What you expected to happen vs. what actually happened
- Your OS, Python version, and any relevant error output

### Suggesting improvements

Open a [GitHub Issue](../../issues) labelled `enhancement`. Describe the problem you are trying to solve and your proposed approach. For non-trivial changes, please discuss before writing code — it avoids wasted effort.

### Submitting a pull request

1. Fork the repository and create a branch from `main`:
   ```bash
   git checkout -b feat/your-feature-name
   ```

2. Install dependencies and the CLI:
   ```bash
   pip install -r requirements.txt
   pip install -e .
   ```

3. Make your changes. Follow the conventions already in the codebase:
   - All new behaviour should have tests in `tests/`
   - Tests must run without any real API calls (mock all external services)
   - Keep functions small and focused; avoid side effects in module-level code

4. Run the full test suite before pushing:
   ```bash
   pytest tests/ -v
   ```
   All 89 tests must pass.

5. Open a pull request against `main`. Describe:
   - What problem this solves
   - How you tested it
   - Any trade-offs or open questions

---

## Development Notes

**Project layout:** source code lives in `src/` organised into subpackages (`agents/`, `pdf/`, `delivery/`, `config/`, `log/`, `run/`, `tools/`). Tests live in `tests/` and mirror the source structure.

**Import paths:** `src/` is the package root (`pythonpath = ["src"]` in `pyproject.toml`). Imports look like `from agents.researcher import ...`, not `from src.agents.researcher import ...`.

**Design docs:** `docs/plans/` contains the design document and implementation plan. Update these when your change affects the architecture, config schema, error codes, or component behaviour.

**No commits with secrets.** Never commit `.env` or any file containing API keys. The `.gitignore` covers `.env` by default — keep it that way.

---

## License

By contributing to this project, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).
