# tests/test_cli.py
import io, os, sys, tempfile, types, unittest
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "hermes-bridge", "scripts"))
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

    def test_legacy_session_flag_with_text_positional(self):
        after = "● hi\n╭─ ⚕ Hermes  10:00─╮\nhello back\n╰──╯\n❯\n"
        h = FakeHerdr({"workspace list": [ok("workspace_list", workspaces=[WS])],
                       "agent list": [ok("agent_list", agents=[agent("bean")])],
                       "agent prompt": [ok("agent_prompt", agent=agent("bean"))]},
                      {"agent read": ["", after]})
        rc, out, _ = run(["send", "--session", "bean", "hi"], h)
        self.assertEqual((rc, out.strip()), (0, "hello back"))
        prompt = [c for c in h.calls if c[:3] == ("cli", "agent", "prompt")][0]
        self.assertEqual(prompt[3:], ("bean", "hi", "--wait", "--timeout", "600000"))

    def test_invalid_name(self):
        rc, _, err = run(["state", "Bean"], FakeHerdr())
        self.assertEqual(rc, 2); self.assertIn("invalid session name", err)

    def test_legacy_session_flag_with_deny_reason(self):
        h = FakeHerdr({"workspace list": [ok("workspace_list", workspaces=[WS])],
                       "agent list": [ok("agent_list", agents=[agent("bean")])]})
        rc, _, err = run(["deny", "--session", "bean", "not now"], h)
        self.assertNotEqual(rc, 0)
        self.assertIn("not approval", err)
        self.assertIn("deny reason: not now", err)

    def test_legacy_session_flag_with_answer_text(self):
        h = FakeHerdr({"workspace list": [ok("workspace_list", workspaces=[WS])],
                       "agent list": [ok("agent_list", agents=[agent("bean", status="blocked")]),
                                      ok("agent_list", agents=[agent("bean", status="idle")])],
                       "agent explain": [{"matched_rule": {"id": "clarification_prompt"}}],
                       "pane send-text": [ok("ok")],
                       "pane send-keys": [ok("ok")]})
        rc, out, _ = run(["answer", "--session", "bean", "yes"], h)
        self.assertEqual((rc, out.strip()), (0, "idle"))
        send_text = [c for c in h.calls if c[:3] == ("cli", "pane", "send-text")][0]
        self.assertEqual(send_text[3:], (agent("bean")["pane_id"], "yes"))

    def test_invalid_name_checked_before_ensure_server(self):
        h = FakeHerdr()
        h.ensure_server = lambda **k: (_ for _ in ()).throw(hb.ServerUnavailable("down"))
        rc, _, err = run(["state", "Bean"], h)
        self.assertEqual(rc, 2)
        self.assertIn("invalid session name", err)
        self.assertEqual(h.calls, [])

    def test_start_does_not_mutate_shared_cfg(self):
        h = FakeHerdr({"workspace list": [ok("workspace_list", workspaces=[WS])],
                       "agent list": [ok("agent_list", agents=[]), ok("agent_list", agents=[]), ok("agent_list", agents=[agent("bean", pane="w1:p2")])],
                       "tab create": [ok("tab_created", tab={"tab_id": "w1:t2"}, root_pane={"pane_id": "w1:p2"})],
                       "pane get": [ok("pane_get", pane={"pane_id": "w1:p2", "workspace_id": "w1"})],
                       "pane process-info": [ok("pane_process_info", process_info={"shell_pid": 1, "foreground_processes": [{"name": "zsh", "argv": ["-zsh"]}]})],
                       "agent start": [ok("agent_started", agent=agent("bean", pane="w1:p2"))]})
        rc, _, _ = run(["start", "bean", "--timeout", "5"], h)
        self.assertEqual(rc, 0)
        self.assertEqual(cli.HERMES_CFG.start_timeout_ms, 120000)

    def test_send_file_not_found_is_usage_error(self):
        h = FakeHerdr({"workspace list": [ok("workspace_list", workspaces=[WS])],
                       "agent list": [ok("agent_list", agents=[agent("bean")])]})
        rc, _, err = run(["send", "bean", "-f", "/nonexistent/path/for/sure.md"], h)
        self.assertEqual(rc, 2)
        self.assertIn("cannot read", err)
        self.assertEqual([c for c in h.calls if c[:3] == ("cli", "agent", "prompt")], [])

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
                       "agent list": [ok("agent_list", agents=[]), ok("agent_list", agents=[]), ok("agent_list", agents=[agent("bean", pane="w1:p2")])],
                       "tab create": [ok("tab_created", tab={"tab_id": "w1:t2"}, root_pane={"pane_id": "w1:p2"})],
                       "pane get": [ok("pane_get", pane={"pane_id": "w1:p2", "workspace_id": "w1"})],
                       "pane process-info": [ok("pane_process_info", process_info={"shell_pid": 1, "foreground_processes": [{"name": "zsh", "argv": ["-zsh"]}]})],
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
        self.assertNotEqual(rc, 0); self.assertIn("not approval", err)

    def test_list_table(self):
        h = FakeHerdr({"workspace list": [ok("workspace_list", workspaces=[WS])],
                       "tab list": [ok("tab_list", tabs=[{"tab_id": "w1:t1", "label": "bean"}])],
                       "agent list": [ok("agent_list", agents=[agent("bean", session="S1")])]})
        rc, out, _ = run(["list"], h)
        self.assertEqual(rc, 0); self.assertIn("bean", out); self.assertIn("S1", out); self.assertIn("idle", out)

    # -- item 1: start --timeout default is 120s (matches the library's own default) --------

    _START_FAKE_CALLS = {
        "workspace list": [ok("workspace_list", workspaces=[WS])],
        "agent list": [ok("agent_list", agents=[]), ok("agent_list", agents=[]), ok("agent_list", agents=[agent("bean", pane="w1:p2")])],
        "tab create": [ok("tab_created", tab={"tab_id": "w1:t2"}, root_pane={"pane_id": "w1:p2"})],
        "pane get": [ok("pane_get", pane={"pane_id": "w1:p2", "workspace_id": "w1"})],
        "pane process-info": [ok("pane_process_info", process_info={"shell_pid": 1, "foreground_processes": [{"name": "zsh", "argv": ["-zsh"]}]})],
        "agent start": [ok("agent_started", agent=agent("bean", pane="w1:p2"))],
    }

    def test_start_timeout_default_is_120000ms(self):
        h = FakeHerdr(dict(self._START_FAKE_CALLS))
        rc, _, _ = run(["start", "bean"], h)
        self.assertEqual(rc, 0)
        start = [c for c in h.calls if c[:3] == ("cli", "agent", "start")][0]
        self.assertEqual(start[start.index("--timeout") + 1], "120000")

    def test_start_timeout_override_converts_seconds_to_ms(self):
        h = FakeHerdr(dict(self._START_FAKE_CALLS))
        rc, _, _ = run(["start", "bean", "--timeout", "5"], h)
        self.assertEqual(rc, 0)
        start = [c for c in h.calls if c[:3] == ("cli", "agent", "start")][0]
        self.assertEqual(start[start.index("--timeout") + 1], "5000")

    # -- item 4: approve/deny exit code follows the *new* state, not always 0 --------------

    _MENU_ALLOW_SELECTED = "⚠ Dangerous command approval\n▸ 1. Allow once\n  2. Deny\n↑/↓ to select · Enter confirm\n"
    _MENU_DENY_SELECTED = "⚠ Dangerous command approval\n  1. Allow once\n▸ 2. Deny\n↑/↓ to select · Enter confirm\n"

    def test_approve_exit_follows_new_state_when_menu_stays_open(self):
        h = FakeHerdr({"workspace list": [ok("workspace_list", workspaces=[WS])],
                       "agent list": [ok("agent_list", agents=[agent("bean", status="blocked")]),
                                      ok("agent_list", agents=[agent("bean", status="blocked")])],
                       "agent explain": [{"matched_rule": {"id": "dangerous_command_approval"}},
                                         {"matched_rule": {"id": "dangerous_command_approval"}}],
                       "agent send-keys": [ok("ok")]},
                      {"agent read": [self._MENU_ALLOW_SELECTED]})
        rc, out, _ = run(["approve", "bean"], h)
        self.assertEqual((rc, out.strip()), (3, "approval"))

    def test_deny_exit_follows_new_state_when_menu_stays_open(self):
        h = FakeHerdr({"workspace list": [ok("workspace_list", workspaces=[WS])],
                       "agent list": [ok("agent_list", agents=[agent("bean", status="blocked")]),
                                      ok("agent_list", agents=[agent("bean", status="blocked")])],
                       "agent explain": [{"matched_rule": {"id": "dangerous_command_approval"}},
                                         {"matched_rule": {"id": "dangerous_command_approval"}}],
                       "agent send-keys": [ok("ok")]},
                      {"agent read": [self._MENU_DENY_SELECTED]})
        rc, out, _ = run(["deny", "bean"], h)
        self.assertEqual((rc, out.strip()), (3, "approval"))

    # -- item 6: send reports failure when blocked before input, even if state reads idle --

    def test_send_undelivered_forces_error_exit_even_when_state_is_idle(self):
        store = hb.StateStore(tempfile.mkdtemp())
        bridge = hb.Bridge(FakeHerdr(), cli.HERMES_CFG, store)
        bridge.send = lambda name, text, timeout_ms: (
            "idle", "", False, "MESSAGE NOT DELIVERED: agent was blocked before input\nsome dialog text\n")
        out, err = io.StringIO(), io.StringIO()
        rc = cli.main(["send", "bean", "hi"], bridge_factory=lambda: bridge, stdout=out, stderr=err)
        self.assertEqual(rc, hb.EXIT_ERROR)
        self.assertIn("message was NOT delivered", err.getvalue())

    # -- item 7: log forwards tail's stderr on failure -------------------------------------

    def test_log_forwards_stderr_on_tail_failure(self):
        orig_run = cli.subprocess.run
        cli.subprocess.run = lambda argv, capture_output=True, text=True: types.SimpleNamespace(
            stdout="", stderr="tail: cannot open file\n", returncode=1)
        try:
            rc, out, err = run(["log"], FakeHerdr())
        finally:
            cli.subprocess.run = orig_run
        self.assertEqual(rc, hb.EXIT_ERROR)
        self.assertIn("cannot open file", err)

    # -- item 8: TEXT and -f FILE together is a usage error --------------------------------

    def test_send_text_and_file_together_is_usage_error(self):
        rc, _, err = run(["send", "bean", "hi", "-f", "somefile.md"], FakeHerdr())
        self.assertEqual(rc, 2)
        self.assertIn("not both", err)

    # -- item 9: --session NAME cannot collide with a real second positional ---------------

    def test_legacy_session_alias_collides_with_second_positional(self):
        rc, _, err = run(["send", "--session", "bean", "hi", "there"], FakeHerdr())
        self.assertEqual(rc, 2)
        self.assertIn("cannot both be given", err)

    def test_legacy_session_alias_shift_still_applies_without_second_positional(self):
        after = "● hi\n╭─ ⚕ Hermes  10:00─╮\nhello back\n╰──╯\n❯\n"
        h = FakeHerdr({"workspace list": [ok("workspace_list", workspaces=[WS])],
                       "agent list": [ok("agent_list", agents=[agent("bean")])],
                       "agent prompt": [ok("agent_prompt", agent=agent("bean"))]},
                      {"agent read": ["", after]})
        rc, out, _ = run(["send", "--session", "bean", "hi"], h)
        self.assertEqual((rc, out.strip()), (0, "hello back"))

    # -- fix round 1: --session + NAME positional is refused even for commands with no ------
    # -- second positional to shift into (start/state/wait/peek/approve/session/stop/forget) -

    def test_legacy_session_alias_collides_on_command_without_second_positional(self):
        h = FakeHerdr()
        rc, _, err = run(["state", "--session", "bean", "bean2"], h)
        self.assertEqual(rc, 2)
        self.assertIn("cannot both be given", err)
        self.assertEqual(h.calls, [])

    def test_legacy_session_alias_collides_on_stop(self):
        rc, _, err = run(["stop", "--session", "bean", "bean"], FakeHerdr())
        self.assertEqual(rc, 2)
        self.assertIn("cannot both be given", err)

    # -- task 1: `start --yolo` explicit opt-in and flag persistence -----------------------

    def test_build_hermes_launch_default_and_yolo(self):
        self.assertEqual(cli.build_hermes_launch(False), cli.HERMES_LAUNCH)
        self.assertEqual(cli.build_hermes_launch(True), cli.HERMES_LAUNCH + ["--yolo"])
        # must not alias/mutate the shared constant
        self.assertIsNot(cli.build_hermes_launch(False), cli.HERMES_LAUNCH)

    def test_start_yolo_appends_flag_and_persists_launch_flags(self):
        store = hb.StateStore(tempfile.mkdtemp())
        h = FakeHerdr(dict(self._START_FAKE_CALLS))
        rc, _, _ = run(["start", "bean", "--yolo"], h, store)
        self.assertEqual(rc, 0)
        start = [c for c in h.calls if c[:3] == ("cli", "agent", "start")][0]
        self.assertEqual(start[start.index("--") + 1:], ("chat", "--cli", "--source", "tool", "--yolo"))
        self.assertEqual(store.load("bean").get("launch_flags"), ["--yolo"])

    def test_start_plain_persists_empty_launch_flags(self):
        store = hb.StateStore(tempfile.mkdtemp())
        h = FakeHerdr(dict(self._START_FAKE_CALLS))
        rc, _, _ = run(["start", "bean"], h, store)
        self.assertEqual(rc, 0)
        start = [c for c in h.calls if c[:3] == ("cli", "agent", "start")][0]
        self.assertEqual(start[start.index("--") + 1:], ("chat", "--cli", "--source", "tool"))
        self.assertEqual(store.load("bean").get("launch_flags"), [])

    def test_start_on_live_yolo_session_keeps_stored_flags_and_warns(self):
        # `start` on an already-live session doesn't relaunch anything (Bridge.start returns the
        # running agent as-is) -- a plain `start` here must not erase the session's --yolo record.
        store = hb.StateStore(tempfile.mkdtemp())
        store.save("bean", launch_flags=["--yolo"])
        h = FakeHerdr({"workspace list": [ok("workspace_list", workspaces=[WS])],
                       "agent list": [ok("agent_list", agents=[agent("bean")])]})
        rc, out, err = run(["start", "bean"], h, store)
        self.assertEqual(rc, 0)
        self.assertEqual(store.load("bean").get("launch_flags"), ["--yolo"])
        self.assertIn("hermes-bridge: this session runs with --yolo (no approval prompts)", err)
        self.assertEqual([c for c in h.calls if c[:3] == ("cli", "agent", "start")], [])

    def test_start_yolo_on_live_plain_session_is_refused(self):
        # The reverse: `start --yolo` on a session already running WITHOUT --yolo must not
        # relaunch it (that would silently record a --yolo flag the running process never got).
        store = hb.StateStore(tempfile.mkdtemp())
        h = FakeHerdr({"workspace list": [ok("workspace_list", workspaces=[WS])],
                       "agent list": [ok("agent_list", agents=[agent("bean")])]})
        rc, _, err = run(["start", "bean", "--yolo"], h, store)
        self.assertEqual(rc, 1)
        self.assertIn("already running without --yolo", err)
        self.assertEqual([c for c in h.calls if c[:3] == ("cli", "agent", "start")], [])
        self.assertEqual(store.load("bean").get("launch_flags"), None)

    def test_send_on_yolo_session_writes_stderr_note(self):
        after = "● hi\n╭─ ⚕ Hermes  10:00─╮\nhello back\n╰──╯\n❯\n"
        store = hb.StateStore(tempfile.mkdtemp())
        store.save("bean", launch_flags=["--yolo"])
        h = FakeHerdr({"workspace list": [ok("workspace_list", workspaces=[WS])],
                       "agent list": [ok("agent_list", agents=[agent("bean")])],
                       "agent prompt": [ok("agent_prompt", agent=agent("bean"))]},
                      {"agent read": ["", after]})
        rc, out, err = run(["send", "bean", "hi"], h, store)
        self.assertEqual((rc, out.strip()), (0, "hello back"))
        self.assertIn("hermes-bridge: this session runs with --yolo (no approval prompts)", err)

    def test_send_on_plain_session_has_no_yolo_note(self):
        after = "● hi\n╭─ ⚕ Hermes  10:00─╮\nhello back\n╰──╯\n❯\n"
        h = FakeHerdr({"workspace list": [ok("workspace_list", workspaces=[WS])],
                       "agent list": [ok("agent_list", agents=[agent("bean")])],
                       "agent prompt": [ok("agent_prompt", agent=agent("bean"))]},
                      {"agent read": ["", after]})
        rc, out, err = run(["send", "bean", "hi"], h)
        self.assertEqual(rc, 0)
        self.assertNotIn("--yolo", err)

    def test_list_shows_yolo_flag_column(self):
        store = hb.StateStore(tempfile.mkdtemp())
        store.save("bean", launch_flags=["--yolo"])
        h = FakeHerdr({"workspace list": [ok("workspace_list", workspaces=[WS])],
                       "tab list": [ok("tab_list", tabs=[{"tab_id": "w1:t1", "label": "bean"}])],
                       "agent list": [ok("agent_list", agents=[agent("bean", session="S1")])]})
        rc, out, _ = run(["list"], h, store)
        self.assertEqual(rc, 0)
        line = [l for l in out.splitlines() if "bean" in l][0]
        self.assertTrue(line.rstrip().endswith("--yolo"))

    def test_list_shows_dash_when_no_yolo_flag(self):
        h = FakeHerdr({"workspace list": [ok("workspace_list", workspaces=[WS])],
                       "tab list": [ok("tab_list", tabs=[{"tab_id": "w1:t1", "label": "bean"}])],
                       "agent list": [ok("agent_list", agents=[agent("bean", session="S1")])]})
        rc, out, _ = run(["list"], h)
        line = [l for l in out.splitlines() if "bean" in l][0]
        self.assertTrue(line.rstrip().endswith("-"))
        self.assertNotIn("--yolo", line)

    # -- task 3: `wait` uses wait_status (herdr `agent wait` first, polling fallback) ------

    def test_wait_happy_path_calls_agent_wait_and_prints_state(self):
        h = FakeHerdr({"workspace list": [ok("workspace_list", workspaces=[WS])],
                       "agent list": [ok("agent_list", agents=[agent("bean", status="idle")])],
                       "agent wait": [ok("agent_wait")]})
        rc, out, _ = run(["wait", "bean", "--timeout", "5"], h)
        self.assertEqual((rc, out.strip()), (0, "idle"))
        self.assertEqual(len([c for c in h.calls if c[:3] == ("cli", "agent", "wait")]), 1)

    def test_wait_argv_includes_until_values_and_timeout(self):
        h = FakeHerdr({"workspace list": [ok("workspace_list", workspaces=[WS])],
                       "agent list": [ok("agent_list", agents=[agent("bean", status="idle")])],
                       "agent wait": [ok("agent_wait")]})
        rc, out, _ = run(["wait", "bean", "--timeout", "5"], h)
        self.assertEqual((rc, out.strip()), (0, "idle"))
        wait_call = [c for c in h.calls if c[:3] == ("cli", "agent", "wait")][0]
        self.assertEqual(wait_call[3:], ("bean", "--until", "idle", "--until", "done",
                                          "--until", "blocked", "--timeout", "5000"))

    def test_wait_blocked_outcome_exits_3(self):
        h = FakeHerdr({"workspace list": [ok("workspace_list", workspaces=[WS])],
                       "agent list": [ok("agent_list", agents=[agent("bean", status="blocked")])],
                       "agent explain": [{"matched_rule": {"id": "unmapped_rule"}}],
                       "agent wait": [ok("agent_wait")]})
        rc, out, _ = run(["wait", "bean", "--timeout", "5"], h)
        self.assertEqual((rc, out.strip()), (3, "blocked"))

    def test_wait_timeout_option_has_help_text(self):
        parser = cli.build_parser()
        wait_sub = parser._subparsers._group_actions[0].choices["wait"]
        self.assertTrue(wait_sub.format_help().strip())
        timeout_action = [a for a in wait_sub._actions if "--timeout" in a.option_strings][0]
        self.assertTrue(timeout_action.help)

    # -- item 7: --session + NAME refusal, parametrized over every named command -----------

    def test_legacy_session_alias_collision_refused_for_every_named_command(self):
        for cmd in sorted(cli._NAMED_CMDS):
            extra = ["bean2", "bean3"] if cmd in cli._LEGACY_POSITIONAL else ["bean2"]
            with self.subTest(cmd=cmd):
                rc, _, err = run([cmd, "--session", "bean"] + extra, FakeHerdr())
                self.assertEqual(rc, 2)
                self.assertIn("cannot both be given", err)

    def test_wait_falls_back_to_polling_when_herdr_wait_socket_closes(self):
        h = FakeHerdr({"workspace list": [ok("workspace_list", workspaces=[WS])],
                       "agent list": [ok("agent_list", agents=[agent("bean", status="idle")])],
                       "agent wait": [hb.HerdrError("closed", "socket closed")]})
        orig_sleep, orig_now = hb._sleep, hb._now
        clock = [0.0]
        hb._sleep = lambda s: clock.__setitem__(0, clock[0] + s)
        hb._now = lambda: clock[0]
        try:
            rc, out, _ = run(["wait", "bean", "--timeout", "5"], h)
        finally:
            hb._sleep, hb._now = orig_sleep, orig_now
        self.assertEqual((rc, out.strip()), (0, "idle"))
        wait_idx = [i for i, c in enumerate(h.calls) if c[:3] == ("cli", "agent", "wait")]
        list_idx = [i for i, c in enumerate(h.calls) if c[:3] == ("cli", "agent", "list")]
        self.assertEqual(len(wait_idx), 1)
        self.assertGreaterEqual(len(list_idx), 1)
        self.assertGreater(list_idx[0], wait_idx[0])

    # -- fix round 2, item 2: restorable (dead-pane) `start` relaunches with the STORED ------
    # -- launch_flags unless the caller passes --yolo explicitly; result is re-recorded ------

    _RESTORABLE_FAKE_CALLS = {
        "workspace list": [ok("workspace_list", workspaces=[WS])],
        "agent list": [ok("agent_list", agents=[]), ok("agent_list", agents=[]),
                       ok("agent_list", agents=[agent("bean", pane="w1:p1", session="S1")])],
        "pane get": [ok("pane_get", pane={"pane_id": "w1:p1", "workspace_id": "w1"})],
        "pane process-info": [ok("pane_process_info", process_info={
            "shell_pid": 1, "foreground_processes": [{"name": "zsh", "argv": ["-zsh"]}]})],
        "agent start": [ok("agent_started", agent=agent("bean", pane="w1:p1", session="S1"))],
    }

    def test_start_restorable_session_relaunches_with_stored_yolo_flag(self):
        store = hb.StateStore(tempfile.mkdtemp())
        store.save("bean", pane_id="w1:p1", tab_id="w1:t1", agent_session_id="S1",
                   launch_flags=["--yolo"])
        h = FakeHerdr(dict(self._RESTORABLE_FAKE_CALLS))
        rc, _, err = run(["start", "bean"], h, store)
        self.assertEqual(rc, 0)
        start = [c for c in h.calls if c[:3] == ("cli", "agent", "start")][0]
        self.assertEqual(start[start.index("--") + 1:],
                         ("chat", "--cli", "--source", "tool", "--yolo", "--resume", "S1"))
        self.assertEqual(store.load("bean").get("launch_flags"), ["--yolo"])
        self.assertIn("hermes-bridge: this session runs with --yolo (no approval prompts)", err)

    def test_start_restorable_session_without_stored_flags_plus_explicit_yolo(self):
        store = hb.StateStore(tempfile.mkdtemp())
        store.save("bean", pane_id="w1:p1", tab_id="w1:t1", agent_session_id="S1")
        h = FakeHerdr(dict(self._RESTORABLE_FAKE_CALLS))
        rc, _, err = run(["start", "bean", "--yolo"], h, store)
        self.assertEqual(rc, 0)
        start = [c for c in h.calls if c[:3] == ("cli", "agent", "start")][0]
        self.assertEqual(start[start.index("--") + 1:],
                         ("chat", "--cli", "--source", "tool", "--yolo", "--resume", "S1"))
        self.assertEqual(store.load("bean").get("launch_flags"), ["--yolo"])
        self.assertIn("hermes-bridge: this session runs with --yolo (no approval prompts)", err)

    # -- fix round 2, item 5: `start NAME --yolo` on a brand-new pane also prints the note ---

    def test_start_fresh_pane_with_explicit_yolo_prints_note(self):
        store = hb.StateStore(tempfile.mkdtemp())
        h = FakeHerdr(dict(self._START_FAKE_CALLS))
        rc, _, err = run(["start", "bean", "--yolo"], h, store)
        self.assertEqual(rc, 0)
        self.assertIn("hermes-bridge: this session runs with --yolo (no approval prompts)", err)

    def test_start_fresh_pane_without_yolo_prints_no_note(self):
        store = hb.StateStore(tempfile.mkdtemp())
        h = FakeHerdr(dict(self._START_FAKE_CALLS))
        rc, _, err = run(["start", "bean"], h, store)
        self.assertEqual(rc, 0)
        self.assertNotIn("--yolo", err)

    # -- fix round 2, item 4: `start NAME --fresh` on a LIVE session is refused, not a no-op -

    def test_start_fresh_on_live_session_is_refused(self):
        h = FakeHerdr({"workspace list": [ok("workspace_list", workspaces=[WS])],
                       "agent list": [ok("agent_list", agents=[agent("bean")])]})
        rc, _, err = run(["start", "bean", "--fresh"], h)
        self.assertEqual(rc, 1)
        self.assertIn("bean is running; stop bean first, then start bean --fresh", err)
        self.assertEqual([c for c in h.calls if c[:3] == ("cli", "agent", "start")], [])

    # -- fix round 2, item 6: `forget NAME` on a LIVE session is refused, state untouched ----

    def test_forget_on_live_session_is_refused(self):
        store = hb.StateStore(tempfile.mkdtemp())
        store.save("bean", launch_flags=["--yolo"])
        h = FakeHerdr({"workspace list": [ok("workspace_list", workspaces=[WS])],
                       "agent list": [ok("agent_list", agents=[agent("bean")])]})
        rc, _, err = run(["forget", "bean"], h, store)
        self.assertEqual(rc, 1)
        self.assertIn("bean is running; stop bean first", err)
        self.assertEqual(store.load("bean").get("launch_flags"), ["--yolo"])

    def test_forget_on_dead_session_still_works(self):
        store = hb.StateStore(tempfile.mkdtemp())
        store.save("bean", launch_flags=["--yolo"])
        h = FakeHerdr({"workspace list": [ok("workspace_list", workspaces=[WS])],
                       "agent list": [ok("agent_list", agents=[])]})
        rc, out, _ = run(["forget", "bean"], h, store)
        self.assertEqual(rc, 0)
        self.assertIn("forgotten", out)
        self.assertEqual(store.load("bean"), {})


if __name__ == "__main__":
    unittest.main()
