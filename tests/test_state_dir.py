import importlib
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "hermes-bridge", "scripts"))
import hermes_bridge_cli as cli  # noqa: E402


class StateDirTests(unittest.TestCase):
    def tearDown(self):
        importlib.reload(cli)

    def test_default_is_outside_the_plugin_cache(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("HERMES_BRIDGE_STATE_DIR", None)
            mod = importlib.reload(cli)
        self.assertEqual(mod.STATE_DIR, os.path.join(os.path.expanduser("~"), ".local", "state", "hermes-bridge"))
        self.assertFalse(mod.STATE_DIR.startswith(mod.SKILL_DIR))

    def test_env_override_wins(self):
        with mock.patch.dict(os.environ, {"HERMES_BRIDGE_STATE_DIR": "/tmp/hb-state-test"}):
            mod = importlib.reload(cli)
        self.assertEqual(mod.STATE_DIR, "/tmp/hb-state-test")


if __name__ == "__main__":
    unittest.main()
