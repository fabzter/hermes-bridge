# hermes-bridge follow-up — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Claude run Hermes in `--yolo` mode when the user explicitly asks, document the CLI's option-ordering rules prominently, drop the tmux narrative from the README, and re-vendor the follow-up library (polling `answer`, `wait_status`, log rotation).

**Architecture:** Additive CLI options in `scripts/hermes_bridge_cli.py`; docs in `SKILL.md`/`README.md`; vendored library refresh via `tools/sync-lib.sh`.

**Tech Stack:** Python 3.9+ stdlib; herdr 0.8.2; Hermes v0.20.0 (`hermes chat --cli --source tool [--yolo]`).

**Spec:** `docs/superpowers/specs/2026-09-01-herdr-bridges-design.md` §4 (amend §3.9/§4 so that `--yolo` is allowed only on explicit user request).

## Global Constraints

- Repo root `/Users/fabzter/.claude/skills/hermes-bridge` — the live Claude skill; never leave the tree broken. Never edit the vendored `scripts/herdrbridge.py` (use `tools/sync-lib.sh <sha>`).
- Python 3 stdlib only; Python 3.9 compatible. `python3 -m unittest discover -s tests -v` pristine under `python3` and `/Users/fabzter/.hermes/hermes-agent/venv/bin/python` before every commit.
- SKILL.md frontmatter `name:`/`description:` unchanged. No AI-authorship text; no attribution footers. Push after each task.
- Safety policy: the default launch never passes `--yolo`; `--yolo` requires the user to have asked for it in chat for that session, and the SKILL.md must say so.

---

### Task 1: `start --yolo` (explicit opt-in) and flag persistence

**Files:** Modify `scripts/hermes_bridge_cli.py`, `tests/test_cli.py`.

**Interfaces — Produces:** `start NAME [--fresh] [--timeout N] [--yolo]`; `HERMES_LAUNCH` unchanged; `build_hermes_launch(yolo: bool) -> list` = `HERMES_LAUNCH + (["--yolo"] if yolo else [])`; the store records `launch_flags` (`["--yolo"]` or `[]`) on start; `state`/`list` print `yolo` in the state column suffix? No — keep output stable; instead `list` gains a trailing `flags` column showing `--yolo` when set; `send` prints a one-line stderr note `hermes-bridge: this session runs with --yolo (no approval prompts)` when the stored flags contain `--yolo`.

- [ ] **Step 1: Failing tests:** `start bean --yolo` → `agent start … -- chat --cli --source tool --yolo` and `store.load("bean")["launch_flags"] == ["--yolo"]`; plain `start` → no `--yolo`, `launch_flags == []`; `send` on a yolo session writes the stderr note; `list` shows `--yolo` for that row.
- [ ] **Step 2: Run → fail.**  - [ ] **Step 3: Implement.**  - [ ] **Step 4: Run → pass.**
- [ ] **Step 5: Commit** `hermes-bridge: start --yolo (explicit opt-in), recorded and surfaced`; push.

---

### Task 2: Docs — option ordering, yolo policy, README without the tmux story

**Files:** Modify `SKILL.md`, `README.md`, `docs/superpowers/specs/2026-09-01-herdr-bridges-design.md`.

- [ ] SKILL.md: (a) a dedicated short section "Argument order" near the Quick Reference: `hermes-bridge <cmd> NAME [TEXT] [--options]` — options go AFTER the positionals; `send bean --timeout 900 "hi"` fails, `send bean "hi" --timeout 900` works, `send bean -f FILE --timeout 900` works; `--session NAME` is a deprecated alias and cannot be combined with a NAME positional. (b) `--yolo`: allowed only when the user explicitly asked for a yolo/autonomous Hermes session in chat; say so in the Safety section (replace "Never pass `--yolo`" with "Never pass `--yolo` on your own initiative; use it only when the user asked for it for this session; yolo sessions never produce `approval` states, so `approve`/`deny` do not apply"); keep `--tui` forbidden. (c) Resuming crashy sessions: one explicit line — "`dead` after a turn (Ladybug crash) → `start NAME` resumes the same conversation; `--fresh` only when the user wants a new one." Frontmatter unchanged; ≤ 120 lines.
- [ ] README.md: delete the "Migration from the tmux version" section; replace with a 4-line "Upgrading" note (names rule, `state/<name>.json`, legacy `.session-id` auto-migration, `send -f` replaces `send-file`). Add the argument-order rule and the `--yolo` policy to Usage.
- [ ] Spec: amend §3.9/§4 ("`--yolo` only on explicit user request; default prompts").
- [ ] Verify `grep -n -i tmux README.md SKILL.md` returns nothing; commit `docs: argument order, explicit --yolo policy, upgrading note`; push.

---

### Task 3: Re-vendor the follow-up library and use it

**Files:** `tools/sync-lib.sh <SHA>` (given at dispatch), `tests/test_cli.py`, `scripts/hermes_bridge_cli.py`.

- [ ] `tools/sync-lib.sh <SHA>`; suite must pass (fix FakeHerdr scripting only).
- [ ] `wait` subcommand uses `b.wait_status(name, timeout_ms=…)` (polling fallback) instead of `b.wait`; test asserts `agent wait` is called and that a `HerdrError("closed")` from it falls back to polling (`agent list` scripted to idle) and still prints `idle`.
- [ ] `answer` inherits the polling library behavior; update SKILL.md wording ("answer waits up to 5 s for the prompt to clear").
- [ ] Live smoke (bounded, throwaway `HERDR_BRIDGE_SESSION=bridge-test-$$`): `start smoke --fresh`, `send smoke "Reply with exactly the word PONG."`, `stop smoke`; cleanup the session. Record.
- [ ] Commit `Re-vendor herdrbridge at <SHA>; wait uses wait_status`; push.
