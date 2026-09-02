# tests/test_vendored_lib.py
import os, sys, unittest
sys.path.insert(0, os.path.dirname(__file__))
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
