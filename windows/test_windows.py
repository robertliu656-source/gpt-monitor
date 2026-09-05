import tempfile
from pathlib import Path
import unittest
from gpt_monitor_windows import load_config, voice_matches, PROMPTS
from parser import sanitize_visible_text, split_for_speech


class WindowsTests(unittest.TestCase):
    def test_settings_and_bounds(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.txt"
            path.write_text("language=zh-CN\nrate=99\nvolume=-1\n")
            config = load_config(path)
            self.assertEqual(config["rate"], 10)
            self.assertEqual(config["volume"], 0)
            path.write_text("rate=invalid")
            with self.assertRaises(ValueError):
                load_config(path)

    def test_language_voice_selection(self):
        self.assertTrue(voice_matches("en-US", "409;809"))
        self.assertTrue(voice_matches("zh-CN", "804"))
        self.assertFalse(voice_matches("en-US", "804"))
        self.assertFalse(voice_matches("zh-CN", "invalid"))
        self.assertEqual(set(PROMPTS["en"]), set(PROMPTS["zh"]))

    def test_shared_text_filter(self):
        self.assertEqual(sanitize_visible_text("Hello <oai-mem-citation>hidden</oai-mem-citation>"), "Hello")
        text = "Hello world. " * 100
        parts = split_for_speech(text, 120)
        self.assertGreater(len(parts), 1)


if __name__ == "__main__":
    unittest.main()
