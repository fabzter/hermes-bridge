"""hermes-bridge — drive the user's Hermes Agent CLI through herdr (Claude Code -> Hermes)."""
from __future__ import annotations

import argparse
import os
import shutil
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
    herdr_bin = os.environ.get("HERDR_BIN") or shutil.which("herdr") or "/opt/homebrew/bin/herdr"
    h = hb.Herdr(hb.session_name(), bin=herdr_bin)
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


_LEGACY_POSITIONAL = {"send": "text", "deny": "reason", "answer": "text"}


def _apply_legacy_session_alias(args) -> None:
    """When `--session NAME` is used with a second positional (e.g. `send --session bean hi`),
    argparse binds the leftover positional token to `name` and leaves the real positional
    (text/reason) empty. Shift it over so `--session` behaves as a NAME alias, not a name-eating flag."""
    pos_attr = _LEGACY_POSITIONAL.get(args.cmd)
    if not pos_attr:
        return
    if getattr(args, "session_alias", None) and getattr(args, pos_attr, None) is None and getattr(args, "name", None):
        setattr(args, pos_attr, args.name)
        args.name = None


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
        _apply_legacy_session_alias(args)
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
        # e.code can legitimately be EXIT_OK (0) when it mirrors the *current* state's
        # exit code (e.g. navigate_menu() refusing because the agent is idle) — but we are
        # inside an error handler, so 0 would misreport failure as success. Never do that.
        return e.code or hb.EXIT_ERROR
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
