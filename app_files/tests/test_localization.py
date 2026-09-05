from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from config import Config
from gpt_monitor import Controller
from i18n import MESSAGES, message
from parser import sanitize_visible_text
from release import _assert_release_child, clear_generated


class LocalizationTests(unittest.TestCase):
    def load(self, text):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "config.txt"
            path.write_text(text)
            return Config.load(path)

    def test_english_defaults_and_explicit_voice(self):
        config = self.load("language=en-US\n")
        self.assertEqual(config["local_voice"], "Samantha")
        self.assertEqual(config["voice"], "en-US-AriaNeural")
        self.assertEqual(config["local_wpm"], "220")
        self.assertFalse(config.bool("translate_english"))
        custom = self.load("language=en-GB\nlocal_voice=Daniel\nlocal_wpm=180\n")
        self.assertEqual(custom["local_voice"], "Daniel")
        self.assertEqual(custom["local_wpm"], "180")

    def test_existing_chinese_settings_survive(self):
        config = self.load("local_voice=Tingting\nlocal_wpm=750\n")
        self.assertEqual(config["local_voice"], "Tingting")
        self.assertEqual(config["local_wpm"], "750")
        self.assertEqual(message(config, "greeting"), MESSAGES["zh"]["greeting"])

    def test_all_prompts_translated_and_handlers_work(self):
        self.assertEqual(set(MESSAGES["zh"]), set(MESSAGES["en"]))
        controller = Controller.__new__(Controller)
        controller.config = self.load("language=en-US\n")
        controller.audio = Mock()
        for payload, key in [({"type": "control_start"}, "greeting"),
                             ({"type": "copy_result", "success": True}, "copied"),
                             ({"type": "attention"}, "attention")]:
            controller._handle(payload)
            self.assertEqual(controller.audio.announce_local.call_args.args[0], MESSAGES["en"][key])
        controller.audio.play_alert.assert_not_called()

    def test_english_text_is_not_translated(self):
        text = "Hello, this is your new reply."
        self.assertEqual(sanitize_visible_text(text), text)

    def test_release_paths_remain_bounded(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _assert_release_child(root / "GPTMonitor_Mac_0.2.0-en", root)
            for name in ("unrelated", "GPTMonitor_Mac_0.2.0-other", "../GPTMonitor_Mac_0.2.0"):
                with self.assertRaises(ValueError):
                    _assert_release_child(root / name, root)
            with self.assertRaises(ValueError):
                clear_generated(root / "unrelated", root)
