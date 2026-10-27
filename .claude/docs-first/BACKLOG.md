# Scoped delivery

- [x] Enforce the local mutation opt-in at each callable tool boundary, document actual behavior, and verify distributable setup.
  - Definition of done: `sh .claude/docs-first/verify.sh`
  - Libraries: Python stdlib, pydantic-settings 2.13.1, MCP SDK 1.26.0, pytest 9.0.2, LangChain Core 1.2.20; setuptools for wheel packaging.
  - Sources: installed version source and official documentation recorded in EVIDENCE.md.

- [x] Make GPU adapter tests deterministic on CPU-only CI while preserving explicit no-hardware responses.
  - Definition of done: `sh .claude/docs-first/verify.sh` plus a CPU-only backend test run.
  - Libraries: pytest 9.0.2; Python unittest.mock and contextlib; existing GPU utility interfaces.
  - Sources: installed APIs recorded in EVIDENCE.md.

## Follow-up

- [ ] Authenticated deployment, per-action approval tokens, external integration tests, and dashboard dependency updates require separate changes.
