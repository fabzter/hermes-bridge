# tests/test_cli.py
import io, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(__file__))
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
                       "agent list": [ok("agent_list", agents=[]), ok("agent_list", agents=[agent("bean", pane="w1:p2")])],
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
                       "agent list": [ok("agent_list", agents=[]), ok("agent_list", agents=[agent("bean", pane="w1:p2")])],
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


if __name__ == "__main__":
    unittest.main()
