# hermes-bridge on herdr — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the tmux-based `hermes-bridge` (Claude Code → Hermes Agent) with a Python 3 tool that drives Hermes through herdr's CLI and socket API, built on the vendored `herdrbridge.py` library from `fabzter/herdrbridge`.

**Architecture:** The stdlib-only library `scripts/herdrbridge.py` (vendored at a pinned commit from `fabzter/herdrbridge`; herdr client, state store, state classification, reply extraction, approval-menu planner, topology/resolve) plus a thin CLI module `scripts/hermes_bridge_cli.py` and a launcher `scripts/hermes-bridge`. All herdr calls run in the named herdr session `agents`. Tests inject a fake herdr client; one live end-to-end task runs in a throwaway named session.

**Tech Stack:** Python 3.9+ stdlib only (`subprocess`, `socket`, `json`, `argparse`, `unittest`), herdr 0.8.2 CLI + socket API, Hermes Agent v0.20.0 (`hermes chat --cli --source tool`).

**Spec:** `docs/superpowers/specs/2026-09-01-herdr-bridges-design.md` (this repo). Read it first; section numbers below refer to it.

**Prerequisite:** the `fabzter/herdrbridge` plan (`docs/superpowers/plans/2026-09-01-herdrbridge-lib.md` in that repo) is complete and pushed.

## Global Constraints

- Repo root is `/Users/fabzter/.claude/skills/hermes-bridge` (it is both the git clone and the live Claude skill). Every commit is immediately live for Claude; do not leave the tree broken between commits.
- Python 3 stdlib only. No third-party imports. Code must run on Python 3.9 (`from __future__ import annotations`, no `match`, no `X | Y` outside annotations). Run tests with the pyenv interpreter `python3` (3.13) and also `/Users/fabzter/.hermes/hermes-agent/venv/bin/python` (3.11) in the final task.
- herdr session name constant `agents`; env `HERDR_BRIDGE_SESSION` overrides (tests use `bridge-test-<pid>`). Never touch the default herdr session. Never run `herdr server stop` or `herdr session stop` against `agents`.
- Agent/session names: `^[a-z][a-z0-9_-]{0,31}$` (herdr's rule).
- Exit codes (spec §3.11): 0 ok · 1 error/refused · 2 missing session or bad usage · 3 approval/blocked · 4 secret · 5 clarify · 6 timeout · 7 dead/unknown · 8 busy · 9 herdr server unavailable. `state` always exits 0.
- Hermes launch args: `chat --cli --source tool [--resume ID]`. Never `--yolo`, never `--tui`.
- Safety (spec §3.9): `approve` only navigates to "Allow once"; nothing is ever auto-approved; secrets are never typed.
- Tests: `python3 -m unittest discover -s tests -v` from the repo root must pass before every commit.
- Commit messages carry no attribution footers of any kind. Push after each task (`git push origin main`; the repo has a repo-local credential helper for the `fabzter` account).

## File structure

| File | Responsibility |
|---|---|
| `scripts/herdrbridge.py` | Vendored copy of the shared library from `fabzter/herdrbridge` (never edit here; run `tools/sync-lib.sh`) |
| `tools/sync-lib.sh` | Fetches `herdrbridge.py`, `tests/fakes.py` and fixtures at a pinned commit |
| `scripts/hermes_bridge_cli.py` | argparse CLI, subcommand handlers, Hermes-specific `BridgeConfig` |
| `scripts/hermes-bridge` | 6-line launcher (shebang, sys.path insert, `main()`); replaces the bash script of the same name in Task 3 |
| `tests/fakes.py` | Vendored `FakeHerdr` scripted client |
| `tests/fixtures/*.txt` | Vendored pane transcripts |
| `tests/test_*.py` | Vendored-lib sanity test and CLI tests |
| `SKILL.md`, `README.md` | Rewritten in Task 4 |

---

### Task 1: Vendor the shared library and scaffold tests

**Files:**
- Create: `tools/sync-lib.sh`
- Create: `scripts/herdrbridge.py`, `scripts/herdrbridge.version` (fetched)
- Create: `tests/__init__.py`, `tests/fakes.py` (fetched), `tests/fixtures/*.txt` (fetched), `tests/test_vendored_lib.py`

**Interfaces:**
- Consumes: the `fabzter/herdrbridge` repo at its latest `main` commit (its plan `docs/superpowers/plans/2026-09-01-herdrbridge-lib.md` lists the full API: `Herdr`, `StateStore`, `BridgeConfig`, `Bridge`, `classify`, `state_exit`, `extract_reply`, `plan_menu_step`, `validate_name`, `session_name`, `EXIT_*`, `BridgeError`, `UsageError`, `ServerUnavailable`, `HerdrError`).
- Produces: importable `herdrbridge` under `scripts/`, `tests/fakes.py` with `FakeHerdr`, `agent`, `ok`, `WS`.

- [ ] **Step 1: Write the sync script**

```bash
#!/usr/bin/env bash
# tools/sync-lib.sh — vendor herdrbridge.py (+ test fakes/fixtures) from fabzter/herdrbridge at a pinned ref.
# Usage: tools/sync-lib.sh [REF]   (REF defaults to the pinned commit in herdrbridge.version, else main)
# Set HERDRBRIDGE_DIR=/path/to/local/clone to copy from a local checkout instead of GitHub.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
dest="$here/scripts"
ref="${1:-$(cat "$dest/herdrbridge.version" 2>/dev/null || echo main)}"
src="${HERDRBRIDGE_DIR:-}"
fetch() { if [[ -n $src ]]; then cp "$src/$1" "$2"; else curl -fsSL "https://raw.githubusercontent.com/fabzter/herdrbridge/$ref/$1" -o "$2"; fi; }
mkdir -p "$dest" "$here/tests/fixtures"
fetch herdrbridge.py "$dest/herdrbridge.py"
fetch tests/fakes.py "$here/tests/fakes.py"
for f in claude_reply.txt hermes_reply.txt hermes_before.txt hermes_approval_menu.txt; do
  fetch "tests/fixtures/$f" "$here/tests/fixtures/$f" || echo "note: fixture $f not available at $ref"
done
# fakes.py in the library repo imports from "..": point it at the vendored location here.
sed -i '' 's#os.path.join(os.path.dirname(__file__), "..")#os.path.join(os.path.dirname(__file__), "..", "scripts")#' "$here/tests/fakes.py"
if [[ -n $src ]]; then ( cd "$src" && git rev-parse HEAD ) > "$dest/herdrbridge.version"
else curl -fsSL "https://api.github.com/repos/fabzter/herdrbridge/commits/$ref" | python3 -c 'import json,sys; print(json.load(sys.stdin)["sha"])' > "$dest/herdrbridge.version"; fi
echo "vendored herdrbridge @ $(cat "$dest/herdrbridge.version")"
```

- [ ] **Step 2: Write the failing sanity test**

```python
# tests/test_vendored_lib.py
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import herdrbridge as hb
from fakes import FakeHerdr, agent, ok


class VendoredLibTests(unittest.TestCase):
    def test_library_surface(self):
        for attr in ("Herdr", "StateStore", "BridgeConfig", "Bridge", "classify", "state_exit",
                     "extract_reply", "plan_menu_step", "validate_name", "session_name",
                     "BridgeError", "UsageError", "ServerUnavailable", "HerdrError"):
            self.assertTrue(hasattr(hb, attr), attr)

    def test_hermes_rules_classify(self):
        self.assertEqual(hb.classify("blocked", "dangerous_command_approval"), "approval")
        self.assertEqual(hb.classify("blocked", "credential_prompt"), "secret")

    def test_fake_works(self):
        h = FakeHerdr({"agent list": [ok("agent_list", agents=[agent("x")])]})
        self.assertEqual(h.cli("agent", "list")["result"]["agents"][0]["name"], "x")

    def test_version_stamp_present(self):
        p = os.path.join(os.path.dirname(__file__), "..", "scripts", "herdrbridge.version")
        self.assertTrue(os.path.exists(p))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run to verify failure**

Run: `cd /Users/fabzter/.claude/skills/hermes-bridge && python3 -m unittest tests.test_vendored_lib -v` → `ModuleNotFoundError: herdrbridge`.

- [ ] **Step 4: Sync and re-run**

```bash
chmod +x tools/sync-lib.sh && tools/sync-lib.sh
touch tests/__init__.py
python3 -m unittest tests.test_vendored_lib -v
```

Expected: 4 tests OK.

- [ ] **Step 5: Commit**

```bash
git add tools/sync-lib.sh scripts/herdrbridge.py scripts/herdrbridge.version tests
git commit -m "Vendor herdrbridge library; sync script; sanity tests"
```

### Task 2: `hermes-bridge` CLI module and launcher

**Files:**
- Create: `scripts/hermes_bridge_cli.py`
- Create: `scripts/hermes-bridge.new` (renamed over the bash script in Task 3)
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: everything from `herdrbridge`.
- Produces: `main(argv: list[str] | None = None, bridge_factory=None, stdout=None, stderr=None) -> int` in `hermes_bridge_cli`; `HERMES_CFG = BridgeConfig(workspace_label="hermes-bridge", kind="hermes", default_cwd=$HOME)`; `HERMES_LAUNCH = ["chat", "--cli", "--source", "tool"]`; `STATE_DIR = <skill dir>/state`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli.py
import io, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import herdrbridge as hb
import hermes_bridge_cli as cli
from fakes import FakeHerdr, agent, ok, WS


def run(argv, h, store=None):
    out, err = io.StringIO(), io.StringIO()
    store = store or hb.StateStore(tempfile.mkdtemp())
    rc = cli.main(argv, bridge_factory=lambda: hb.Bridge(h, cli.HERMES_CFG, store), stdout=out, stderr=err)
    return rc, out.getvalue(), err.getvalue()


class CliTests(unittest.TestCase):
    def test_missing_name_is_usage_error(self):
        rc, out, err = run(["state"], FakeHerdr())
        self.assertEqual(rc, 2); self.assertIn("NAME", err)

    def test_legacy_session_flag_accepted(self):
        h = FakeHerdr({"workspace list": [ok("workspace_list", workspaces=[WS])], "agent list": [ok("agent_list", agents=[agent("bean")])]})
        rc, out, _ = run(["state", "--session", "bean"], h)
        self.assertEqual((rc, out.strip()), (0, "idle"))

    def test_invalid_name(self):
        rc, _, err = run(["state", "Bean"], FakeHerdr())
        self.assertEqual(rc, 2); self.assertIn("invalid session name", err)

    def test_state_prints_word_exit_zero_even_when_missing(self):
        h = FakeHerdr({"workspace list": [ok("workspace_list", workspaces=[WS])], "agent list": [ok("agent_list", agents=[])]})
        rc, out, _ = run(["state", "bean"], h)
        self.assertEqual((rc, out.strip()), (0, "missing"))

    def test_send_prints_reply_and_exit_by_state(self):
        after = "● hi\n╭─ ⚕ Hermes  10:00─╮\nhello back\n╰──╯\n❯\n"
        h = FakeHerdr({"workspace list": [ok("workspace_list", workspaces=[WS])],
                       "agent list": [ok("agent_list", agents=[agent("bean")])],
                       "agent prompt": [ok("agent_prompt", agent=agent("bean"))]},
                      {"agent read": ["", after]})
        rc, out, _ = run(["send", "bean", "hi"], h)
        self.assertEqual((rc, out.strip()), (0, "hello back"))
        prompt = [c for c in h.calls if c[:3] == ("cli", "agent", "prompt")][0]
        self.assertEqual(prompt[3:], ("bean", "hi", "--wait", "--timeout", "600000"))

    def test_send_from_file_and_stdin(self):
        after = "● line one\n╭─ ⚕ Hermes  10:00─╮\nok\n╰──╯\n❯\n"
        p = os.path.join(tempfile.mkdtemp(), "m.md")
        with open(p, "w") as f: f.write("line one\nline two\n")
        h = FakeHerdr({"workspace list": [ok("workspace_list", workspaces=[WS])],
                       "agent list": [ok("agent_list", agents=[agent("bean")])],
                       "agent prompt": [ok("agent_prompt", agent=agent("bean"))]}, {"agent read": ["", after]})
        rc, out, _ = run(["send", "bean", "-f", p], h)
        self.assertEqual((rc, out.strip()), (0, "ok"))
        self.assertEqual([c for c in h.calls if c[:3] == ("cli", "agent", "prompt")][0][4], "line one\nline two\n")

    def test_send_busy_exit_8(self):
        h = FakeHerdr({"workspace list": [ok("workspace_list", workspaces=[WS])],
                       "agent list": [ok("agent_list", agents=[agent("bean", status="working")])]})
        rc, _, err = run(["send", "bean", "hi"], h)
        self.assertEqual(rc, 8); self.assertIn("busy", err)

    def test_start_uses_hermes_launch_args(self):
        h = FakeHerdr({"workspace list": [ok("workspace_list", workspaces=[WS])],
                       "agent list": [ok("agent_list", agents=[])],
                       "tab create": [ok("tab_created", tab={"tab_id": "w1:t2"}, root_pane={"pane_id": "w1:p2"})],
                       "agent start": [ok("agent_started", agent=agent("bean", pane="w1:p2"))]})
        rc, out, _ = run(["start", "bean"], h)
        self.assertEqual(rc, 0)
        start = [c for c in h.calls if c[:3] == ("cli", "agent", "start")][0]
        self.assertEqual(start[start.index("--") + 1:], ("chat", "--cli", "--source", "tool"))
        self.assertIn("w1:p2", out)

    def test_server_unavailable_exit_9(self):
        h = FakeHerdr()
        h.ensure_server = lambda **k: (_ for _ in ()).throw(hb.ServerUnavailable("down"))
        rc, _, err = run(["state", "bean"], h)
        self.assertEqual(rc, 9); self.assertIn("down", err)

    def test_approve_requires_approval_state(self):
        h = FakeHerdr({"workspace list": [ok("workspace_list", workspaces=[WS])], "agent list": [ok("agent_list", agents=[agent("bean")])]})
        rc, _, err = run(["approve", "bean"], h)
        self.assertEqual(rc, 0 if False else rc)  # placeholder-free: real assertion below
        self.assertNotEqual(rc, 0); self.assertIn("not approval", err)

    def test_list_table(self):
        h = FakeHerdr({"workspace list": [ok("workspace_list", workspaces=[WS])],
                       "tab list": [ok("tab_list", tabs=[{"tab_id": "w1:t1", "label": "bean"}])],
                       "agent list": [ok("agent_list", agents=[agent("bean", session="S1")])]})
        rc, out, _ = run(["list"], h)
        self.assertEqual(rc, 0); self.assertIn("bean", out); self.assertIn("S1", out); self.assertIn("idle", out)


if __name__ == "__main__":
    unittest.main()
```

Remove the line `self.assertEqual(rc, 0 if False else rc)` before committing; it is there only to be deleted (the real assertions follow it).

- [ ] **Step 2: Run to verify failure** → `ModuleNotFoundError: hermes_bridge_cli`.

- [ ] **Step 3: Implement the CLI**

```python
# scripts/hermes_bridge_cli.py
"""hermes-bridge — drive the user's Hermes Agent CLI through herdr (Claude Code -> Hermes)."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

import herdrbridge as hb

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DIR = os.path.join(SKILL_DIR, "state")
HERMES_LAUNCH = ["chat", "--cli", "--source", "tool"]
HERMES_CFG = hb.BridgeConfig(workspace_label="hermes-bridge", kind="hermes",
                             default_cwd=os.path.expanduser("~"))
HERMES_LOG = os.path.expanduser("~/.hermes/logs/agent.log")


def default_bridge_factory():
    h = hb.Herdr(hb.session_name())
    return hb.Bridge(h, HERMES_CFG, hb.StateStore(STATE_DIR))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hermes-bridge", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def named(name, help_, **kw):
        sp = sub.add_parser(name, help=help_, **kw)
        sp.add_argument("name", nargs="?", help="session NAME ([a-z][a-z0-9_-]{0,31})")
        sp.add_argument("--session", dest="session_alias", help="legacy alias for NAME")
        return sp

    sp = named("start", "launch or resume Hermes in herdr session 'agents'")
    sp.add_argument("--fresh", action="store_true", help="abandon the stored conversation; start a new one")
    sp.add_argument("--timeout", type=int, default=60, help="startup timeout seconds")
    sp = named("send", "send one message (multiline safe) and print Hermes's reply")
    sp.add_argument("text", nargs="?", help="message text; '-' reads stdin")
    sp.add_argument("-f", "--file", help="read the message from FILE")
    sp.add_argument("--timeout", type=int, default=600, help="seconds to wait for the reply")
    named("state", "print idle|busy|approval|secret|clarify|blocked|unknown|dead|missing")
    sp = named("wait", "block until Hermes settles, then print the state")
    sp.add_argument("--timeout", type=int, default=600)
    sp = named("peek", "print recent pane text")
    sp.add_argument("-n", "--lines", type=int, default=80)
    named("approve", "select 'Allow once' in an approval menu (only after the human said yes)")
    sp = named("deny", "select 'Deny' in an approval menu")
    sp.add_argument("reason", nargs="?", default="")
    sp = named("answer", "answer a clarification prompt")
    sp.add_argument("text")
    named("session", "print the Hermes session id")
    named("stop", "send /exit and close the tab (conversation stays resumable)")
    named("forget", "delete the stored session id for NAME")
    sub.add_parser("list", help="list bridge sessions")
    sub.add_parser("gc", help="close tabs whose Hermes process is gone")
    sp = sub.add_parser("log", help="tail ~/.hermes/logs/agent.log")
    sp.add_argument("-n", "--lines", type=int, default=40)
    return p


def _name(args) -> str:
    name = getattr(args, "name", None) or getattr(args, "session_alias", None)
    if not name:
        raise hb.UsageError("NAME is required: hermes-bridge %s NAME ..." % args.cmd)
    return hb.validate_name(name)


def _text(args) -> str:
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()
    elif args.text == "-" or args.text is None:
        text = sys.stdin.read()
    else:
        text = args.text
    if not text.strip():
        raise hb.UsageError("empty message")
    return text


def main(argv=None, bridge_factory=None, stdout=None, stderr=None) -> int:
    out = stdout or sys.stdout
    err = stderr or sys.stderr
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    try:
        if args.cmd == "log":
            cp = subprocess.run(["tail", "-n", str(args.lines), HERMES_LOG], capture_output=True, text=True)
            out.write(cp.stdout)
            return 0 if cp.returncode == 0 else 1
        b = (bridge_factory or default_bridge_factory)()
        b.h.ensure_server()
        if args.cmd == "list":
            for r in b.list_sessions():
                out.write("%-32s %-8s %-10s %s\n" % (r["name"], r["pane_id"] or "-", r["state"], r["session_id"] or "-"))
            return 0
        if args.cmd == "gc":
            for t in b.gc():
                out.write("closed %s\n" % t)
            return 0
        name = _name(args)
        if args.cmd == "start":
            b.cfg.start_timeout_ms = args.timeout * 1000
            a = b.start(name, HERMES_LAUNCH, fresh=args.fresh)
            st = b.state(name)[0]
            out.write("%s %s %s\n" % (name, a.get("pane_id"), st))
            return hb.state_exit(st) if st not in ("idle",) else 0
        if args.cmd == "send":
            state, reply, truncated, dialog = b.send(name, _text(args), args.timeout * 1000)
            out.write(reply + ("\n" if reply and not reply.endswith("\n") else ""))
            if truncated:
                err.write("hermes-bridge: reply anchor not found; printed best-effort tail (may be truncated)\n")
            if dialog:
                out.write("\n[hermes-bridge] Hermes is now %s; dialog:\n%s\n" % (state, dialog.rstrip()))
            return hb.state_exit(state)
        if args.cmd == "state":
            out.write(b.state(name)[0] + "\n")
            return 0
        if args.cmd == "wait":
            st = b.wait(name, args.timeout * 1000)[0]
            out.write(st + "\n")
            return hb.state_exit(st)
        if args.cmd == "peek":
            out.write(b.read(name, args.lines))
            return 0
        if args.cmd == "approve":
            st = b.navigate_menu(name, "Allow once")
            out.write(st + "\n")
            return 0
        if args.cmd == "deny":
            if args.reason:
                err.write("hermes-bridge: deny reason: %s\n" % args.reason)
            st = b.navigate_menu(name, "Deny")
            out.write(st + "\n")
            return 0
        if args.cmd == "answer":
            st = b.answer(name, args.text)
            out.write(st + "\n")
            return hb.state_exit(st) if st != "busy" else 0
        if args.cmd == "session":
            a = b.find_agent(name)
            sid = ((a or {}).get("agent_session") or {}).get("value") or b.store.load(name).get("agent_session_id")
            if not sid:
                err.write("hermes-bridge: no session id known for %r yet (send one message first)\n" % name)
                return 1
            out.write(sid + "\n")
            return 0
        if args.cmd == "stop":
            out.write("stopped\n" if b.stop(name) else "nothing to stop\n")
            return 0
        if args.cmd == "forget":
            out.write("forgotten\n" if b.store.delete(name) else "nothing stored\n")
            return 0
        raise hb.UsageError("unknown command %r" % args.cmd)
    except hb.BridgeError as e:
        err.write("hermes-bridge: %s\n" % e)
        return e.code
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
```

`scripts/hermes-bridge.new`:

```python
#!/usr/bin/env python3
"""Launcher: hermes-bridge (Claude Code -> Hermes Agent over herdr)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hermes_bridge_cli import main  # noqa: E402
sys.exit(main())
```

`chmod +x scripts/hermes-bridge.new`.

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m unittest discover -s tests -v` → all tests OK. In `test_start_uses_hermes_launch_args`, `state()` after start calls `agent list` again; the fake's last scripted result repeats (`agents=[]`), giving `missing`; if that makes `rc` non-zero, script two `agent list` results (`[]` then `[agent("bean", pane="w1:p2")]`).

- [ ] **Step 5: Commit**

```bash
git add scripts/hermes_bridge_cli.py scripts/hermes-bridge.new tests/test_cli.py
git commit -m "hermes-bridge: Python CLI over herdrbridge (start/send/state/wait/peek/approve/deny/answer/session/stop/forget/list/gc/log)"
```

---

### Task 3: Live end-to-end in a throwaway herdr session, real fixtures, cut over

**Files:**
- Modify: `tests/fixtures/hermes_reply.txt` (replace with a fresh live capture if it differs)
- Rename: `scripts/hermes-bridge.new` → `scripts/hermes-bridge` (deleting the bash script)
- Create: `tests/live/README.md` (how to run the live check)
- Create: `tests/live/e2e_hermes.sh`

This task talks to real herdr and real Hermes. Use a throwaway session so the user's `agents` session and default session are untouched.

- [ ] **Step 1: Write the live script**

```bash
#!/usr/bin/env bash
# tests/live/e2e_hermes.sh — end-to-end check against real herdr + Hermes in a throwaway named session.
set -euo pipefail
here="$(cd "$(dirname "$0")/../.." && pwd)"
export HERDR_BRIDGE_SESSION="bridge-test-$$"
B="python3 $here/scripts/hermes-bridge.new"; [[ -x $here/scripts/hermes-bridge && ! -f $here/scripts/hermes-bridge.new ]] && B="$here/scripts/hermes-bridge"
cleanup() { HERDR_SESSION="$HERDR_BRIDGE_SESSION" herdr session stop "$HERDR_BRIDGE_SESSION" --json >/dev/null 2>&1 || true
            herdr session delete "$HERDR_BRIDGE_SESSION" --json >/dev/null 2>&1 || true; }
trap cleanup EXIT
echo "## start"; $B start e2e --fresh
echo "## state"; st=$($B state e2e); [[ $st == idle ]] || { echo "expected idle, got $st"; exit 1; }
echo "## send"; reply=$($B send e2e "Reply with exactly the word PONG and nothing else."); echo "reply=<$reply>"
[[ $reply == *PONG* ]] || { echo "reply did not contain PONG"; exit 1; }
echo "## session"; $B session e2e
echo "## multiline send"; printf 'Answer with one word: what colour is the sky on a clear day?\nSecond line is context only.\n' | $B send e2e -
echo "## approval"; set +e
$B send e2e "Run this exact shell command and show me its output: rm -rf /tmp/hermes-bridge-e2e-does-not-exist" >/tmp/e2e-approval.out 2>&1; rc=$?
set -e; cat /tmp/e2e-approval.out
if [[ $rc == 3 ]]; then echo "approval detected (exit 3)"; $B peek e2e -n 20; echo "## deny"; $B deny e2e "e2e test"; sleep 2; $B state e2e
else echo "NOTE: no approval prompt (rc=$rc) — Hermes may have auto-approved via smart mode; record this in the task notes"; fi
echo "## list"; $B list
echo "## capture fixture"; $B peek e2e -n 60 > /tmp/hermes_live_capture.txt
echo "## stop"; $B stop e2e; $B state e2e
echo "## gc"; $B gc
echo "ALL LIVE CHECKS PASSED"
```

`tests/live/README.md`: three lines: what the script does, that it needs herdr ≥ 0.8.2 and a working `hermes` CLI, and that it creates and deletes its own herdr session.

- [ ] **Step 2: Run it**

Run: `bash tests/live/e2e_hermes.sh` (allow up to 10 minutes; Hermes startup and each turn take 20–60 s).
Expected: `ALL LIVE CHECKS PASSED`. Known outcomes to record rather than fix: if the approval step is auto-approved by Hermes's smart approval mode, note it; if Hermes segfaults in a `--fresh` session, that is new information (the spike only saw crashes on resume) and must be reported to the user.

- [ ] **Step 3: Refresh the Hermes fixture from the live capture**

Compare `/tmp/hermes_live_capture.txt` with `tests/fixtures/hermes_reply.txt`. If the box/echo glyphs differ, replace the fixture with the live capture (trim to the last exchange) and adjust the expected reply string in `tests/test_extract.py::test_reply_from_hermes_box`. Re-run `python3 -m unittest discover -s tests -v`.

- [ ] **Step 4: Cut over the script**

```bash
git rm -q scripts/hermes-bridge
git mv scripts/hermes-bridge.new scripts/hermes-bridge
chmod +x scripts/hermes-bridge
sed -i '' 's#scripts/hermes-bridge.new#scripts/hermes-bridge#' tests/live/e2e_hermes.sh
scripts/hermes-bridge --help | head -3
/Users/fabzter/.hermes/hermes-agent/venv/bin/python -m unittest discover -s tests -v 2>&1 | tail -3
python3 -m unittest discover -s tests -v 2>&1 | tail -3
```

Expected: help prints; both interpreters report OK.

- [ ] **Step 5: Commit and push**

```bash
git add -A scripts tests
git commit -m "hermes-bridge: cut over to the herdr-based Python bridge; live e2e script"
git push origin main
```

---

### Task 4: Rewrite SKILL.md and README.md

**Files:**
- Modify: `SKILL.md` (full rewrite)
- Modify: `README.md` (full rewrite)

- [ ] **Step 1: Write SKILL.md**

Keep the frontmatter `name: hermes-bridge` and the current `description` line unchanged. Body sections, in this order, each with the exact facts below:

1. **Overview** — `~/.claude/skills/hermes-bridge/scripts/hermes-bridge` drives Hermes (`hermes chat --cli --source tool`) inside a pane of the named herdr session `agents`. Always call it by absolute path. Requires herdr ≥ 0.8.2 and python3; the bridge starts the `agents` server itself if it is not running.
2. **Quick reference table** — every subcommand from Task 2 with one-line purpose; note `send -f FILE` and `send NAME -` for multiline (replaces `send-file`), and that `--session NAME` is a deprecated alias for the positional NAME.
3. **Naming** — NAME is the herdr agent name: `^[a-z][a-z0-9_-]{0,31}$`; one stable name per purpose (`cv`, `sync-prep`, `standup-2026-09-01`); old names with dots/uppercase no longer work — pick a new one (`hermes-cv` → `cv`).
4. **Exit codes** — spec §3.11 list; `state` always exits 0.
5. **Workflow** — start → check state → send/wait loop → stop; herdr's `agent prompt` refuses to type into a blocked agent, so `send` never interrupts an approval.
6. **States table** — spec §3.7 rows with required handling (copy the handling column from the current SKILL.md: approval → surface to the human, only `approve` after they say yes; secret → never type it; clarify → `answer` if known; dead → `start` again; missing → `start`). Add: `blocked` (generic) → `peek`, then surface. Mention that state comes from herdr's screen detection plus `agent explain`, not from glyph scraping, so Hermes upgrades no longer require re-verifying glyphs.
7. **Session lifecycle — Claude decides** — copy the current section verbatim (standing authority 2026-08-20), replacing tmux references: stale panes are cleaned with `gc`; foreign same-name agents cannot occur (herdr names are unique).
8. **herdr specifics you must know** — (a) session id appears only after Hermes's first LLM call, so `session` right after `start` may say none; (b) after a herdr server restart herdr relaunches `hermes --resume <id>` on its own and keeps the name, and `start` finds it (no duplicate); (c) known host issue: resumed Hermes sessions have segfaulted in the LadybugDB memory provider right after their first turn; if `state` says `dead` twice in a row after resume, use `start --fresh`; (d) the human can watch with `herdr session attach agents` or `HERDR_SESSION=agents herdr agent attach NAME`; (e) `done` vs `idle` in herdr are both `idle` here.
9. **Knowledge-exchange recipes** — carry over from the current SKILL.md (memory files, ask Hermes, teach Hermes) with `send-file` → `send -f`.
10. **Safety** — carry over: never `--yolo`/`--tui`; never `approve` without the human's yes in chat; never make Hermes message external platforms unless asked. Add: never `herdr session stop agents` to dodge an approval.
11. **Gotchas** — NO_REPLY persona rule (keep); large `send -f` payloads collapse into a temp-file reference in Hermes (keep); reply extraction falls back to the raw tail and warns on stderr when the echo line is not found — if a reply looks cut, `peek -n 200`.

Delete every sentence about tmux, glyph pinning, ownership markers, `send-file`, and `--session` being mandatory.

- [ ] **Step 2: Write README.md**

Sections: what it is (Claude Code → Hermes over herdr, Python 3 stdlib); requirements (herdr ≥ 0.8.2 with the Hermes integration installed, Hermes Agent CLI, python3); usage block with `start`, `send`, `send -f`, `state`, `approve|deny`, `stop`, `list`; how herdr is used (named session `agents`, one tab per session, `agent prompt --wait`, `agent explain`, native session restore); design notes (fail-closed approvals, no auto-approve, session ids from herdr); testing (`python3 -m unittest discover -s tests -v`, `tests/live/e2e_hermes.sh`); the other direction link to `fabzter/hermes-claude-bridge`; a "Migration from the tmux version" paragraph (names rule, `send-file` → `send -f`, state dir now `state/<name>.json`, old `.session-id` files migrate automatically).

- [ ] **Step 3: Verify the skill loads**

Run: `head -5 SKILL.md` (frontmatter intact) and `scripts/hermes-bridge --help`.

- [ ] **Step 4: Commit and push**

```bash
git add SKILL.md README.md
git commit -m "docs: SKILL.md and README for the herdr-based bridge"
git push origin main
```

---

## Self-review notes

- Spec coverage: §3.1–3.3, §3.5–3.11 are implemented by the vendored library (see the herdrbridge plan); §4 Tasks 2, 4; §7 Task 3 live run; §8 step 1 Task 3.
- Type consistency with the library: `Bridge.send` → `(state, reply, truncated, dialog)`; `navigate_menu(name, target_label)`; `stop(name)`; `StateStore.load/save/delete`; `hb.session_name()`; `hb.state_exit(state)`.
