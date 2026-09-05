from __future__ import annotations

from pathlib import Path
import json
import logging
import os
import plistlib
import tempfile
import threading
import time
import unittest
import mac_audio as mac_audio_module
from carbon_hotkey import ExactMasterHotkey

from config import Config, DEFAULTS, normalize_hotkey
from launch_agent import launch_agent_payload
from mac_audio import MacAudioEngine, PlaybackState, SpeechJob
from mac_clipboard import copy_unicode, read_unicode
from mac_hotkeys import GlobalHotkeys
from monitor import SessionMonitor, latest_complete_reply
from parser import (
    CompleteLineReader,
    TurnSpeechState,
    decode_json_line,
    explicit_attention_event,
    extract_visible_event,
    sanitize_visible_text,
    split_for_speech,
)
from process_guard import InstanceLock, process_record, validate_pid_record


LOG = logging.getLogger("gpt-monitor-tests")
LOG.addHandler(logging.NullHandler())


def response(text="正文", phase="final_answer", turn="turn-1", message_id="message-1", **metadata):
    meta = {"turn_id": turn, **metadata}
    return {
        "timestamp": "2026-08-17T00:00:01Z",
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "assistant",
            "phase": phase,
            "id": message_id,
            "internal_chat_message_metadata_passthrough": meta,
            "content": [{"type": "output_text", "text": text}],
        },
    }


def event(event_type, turn="turn-1"):
    return {"timestamp": "2026-08-17T00:00:00Z", "type": "event_msg", "payload": {"type": event_type, "turn_id": turn}}


def write_jsonl(path: Path, records, newline=True, bom=False, crlf=False):
    sep = "\r\n" if crlf else "\n"
    text = sep.join(json.dumps(x, ensure_ascii=False) for x in records)
    if newline:
        text += sep
    if bom:
        text = "\ufeff" + text
    path.write_text(text, encoding="utf-8")


class ConfigTests(unittest.TestCase):
    def test_01_config_parsing_and_fixed_cloud_values(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "config.txt"
            p.write_text("voice=wrong\nedge_rate=0%\nedge_volume=-10%\npoll_seconds=1.25\n", encoding="utf-8")
            c = Config.load(p)
            self.assertEqual(c["voice"], "zh-CN-YunxiNeural")
            self.assertEqual(c["edge_rate"], "+65%")
            self.assertEqual(c["edge_volume"], "+30%")
            self.assertEqual(c.number("poll_seconds"), 1.25)

    def test_02_bad_config_falls_back_safely(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "config.txt"
            p.write_text("poll_seconds=garbage\nrecent_files=-999\nnot_a_line\n", encoding="utf-8")
            c = Config.load(p)
            self.assertEqual(c.number("poll_seconds"), 0.1)
            self.assertEqual(c.integer("recent_files", 16, 256), 16)
            self.assertTrue(c.bool("low_latency"))
            self.assertFalse(c.bool("announce_reply_start"))
            self.assertTrue(c.bool("prefer_latest_reply"))
            self.assertFalse(c.bool("hotkeys_enabled"))
            self.assertEqual(c.number("local_rate", 0.1, 1.0), 1.0)
            self.assertEqual(c.number("local_volume", 0.0, 1.0), 0.7)

    def test_03_hotkey_aliases(self):
        self.assertEqual(normalize_hotkey("CONTROL+COMMAND+/", DEFAULTS["hotkey"]), "CTRL+CMD+/")
        self.assertEqual(normalize_hotkey("CTRL+ALT+K", DEFAULTS["hotkey"]), "CTRL+OPTION+K")
        self.assertEqual(DEFAULTS["master_hotkey"], "CTRL+CMD+M")


class JsonlTests(unittest.TestCase):
    def test_04_utf8_bom(self):
        self.assertEqual(decode_json_line(b"\xef\xbb\xbf{\"x\":1}"), {"x": 1})

    def test_05_crlf(self):
        self.assertEqual(decode_json_line(b'{"x":2}\r'), {"x": 2})

    def test_06_incomplete_tail_is_not_advanced(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.jsonl"
            p.write_bytes(b'{"a":1}\n{"b":')
            lines, offset = CompleteLineReader.read(p, 0)
            self.assertEqual(lines, [b'{"a":1}'])
            self.assertEqual(offset, len(b'{"a":1}\n'))

    def test_07_line_larger_than_64k(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.jsonl"
            value = "中" * 70000
            write_jsonl(p, [{"value": value}])
            lines, offset = CompleteLineReader.read(p, 0)
            self.assertEqual(json.loads(lines[0])["value"], value)
            self.assertEqual(offset, p.stat().st_size)


class ParserTests(unittest.TestCase):
    def test_08_commentary_parsed(self):
        got = extract_visible_event(response("进行中", "commentary"), "s")
        self.assertEqual((got.phase, got.text), ("commentary", "进行中"))

    def test_09_final_answer_parsed(self):
        got = extract_visible_event(response("完成", "final_answer"), "s")
        self.assertEqual((got.phase, got.turn_id), ("final_answer", "turn-1"))

    def test_10_tool_call_and_result_excluded(self):
        for typ in ("custom_tool_call", "custom_tool_call_output"):
            record = {"type": "response_item", "payload": {"type": typ, "output": "secret"}}
            self.assertIsNone(extract_visible_event(record, "s"))

    def test_11_analysis_and_reasoning_excluded(self):
        self.assertIsNone(extract_visible_event(response("hidden", "analysis"), "s"))
        self.assertIsNone(extract_visible_event({"type": "response_item", "payload": {"type": "reasoning"}}, "s"))

    def test_12_subagent_message_excluded(self):
        self.assertIsNone(extract_visible_event(response("internal", recipient="subagent-1"), "s"))

    def test_13_complete_and_partial_memory_citation_removed(self):
        complete = "可见\n<oai-mem-citation><citation_entries>secret</citation_entries></oai-mem-citation>"
        partial = "可见\n<oai-mem-citation><citation_entries>secret"
        self.assertEqual(sanitize_visible_text(complete), "可见")
        self.assertEqual(sanitize_visible_text(partial), "可见")

    def test_14_ui_directives_removed(self):
        text = "前文\n::code-comment{title=\"x\" body=\"secret\"}\n后文\n::created-thread{threadId=\"1\"}"
        cleaned = sanitize_visible_text(text)
        self.assertIn("前文", cleaned)
        self.assertIn("后文", cleaned)
        self.assertNotIn("secret", cleaned)
        self.assertNotIn("threadId", cleaned)

    def test_15_mixed_chinese_english_retained(self):
        text = "请启动 GPT Monitor，然后使用 OpenAI API 和 file_name.py。"
        self.assertEqual(sanitize_visible_text(text), text)

    def test_16_visible_markdown_text_retained(self):
        text = "# 标题\n查看 [OpenAI 文档](https://openai.com) 和 `GPT Monitor`。"
        cleaned = sanitize_visible_text(text)
        self.assertIn("标题", cleaned)
        self.assertIn("OpenAI 文档", cleaned)
        self.assertIn("GPT Monitor", cleaned)
        self.assertNotIn("https://", cleaned)

    def test_17_raw_json_excluded(self):
        self.assertEqual(sanitize_visible_text('{"secret":"value"}'), "")


class TurnStateTests(unittest.TestCase):
    def test_18_same_message_id_deduplicated(self):
        state = TurnSpeechState()
        e = extract_visible_event(response("正文", "commentary"), "s")
        self.assertEqual(state.accept(e), "正文")
        self.assertEqual(state.accept(e), "")

    def test_19_realtime_body_not_repeated_at_final(self):
        body = "这是已经实时朗读的较长正文。" * 20
        state = TurnSpeechState()
        self.assertEqual(state.accept(extract_visible_event(response(body, "commentary", message_id="c"), "s")), body)
        self.assertEqual(state.accept(extract_visible_event(response(body, "final_answer", message_id="f"), "s")), "")

    def test_20_short_progress_does_not_suppress_final(self):
        state = TurnSpeechState()
        state.accept(extract_visible_event(response("我正在检查。", "commentary", message_id="c"), "s"))
        final = "检查完成，这是实际答案。"
        self.assertEqual(state.accept(extract_visible_event(response(final, "final_answer", message_id="f"), "s")), final)

    def test_21_long_prefix_only_reads_suffix(self):
        prefix = "已确认的正文。" * 30
        suffix = "最后补充。"
        state = TurnSpeechState()
        state.accept(extract_visible_event(response(prefix, "commentary", message_id="c"), "s"))
        self.assertEqual(state.accept(extract_visible_event(response(prefix + suffix, "final_answer", message_id="f"), "s")), suffix)


class MonitorTests(unittest.TestCase):
    def test_22_startup_does_not_read_history(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = root / "old.jsonl"
            write_jsonl(p, [event("task_started"), response("历史")])
            os.utime(p, (time.time() - 5, time.time() - 5))
            out = []
            mon = SessionMonitor([root], 16, 900, out.append, lambda: None, LOG)
            mon.scan_once()
            self.assertEqual(out, [])
            with p.open("a", encoding="utf-8") as f:
                f.write(json.dumps(response("新内容", message_id="new"), ensure_ascii=False) + "\n")
            mon.scan_once()
            self.assertEqual(out[0]["text"], "新内容")

    def test_23_new_session_is_read_from_start(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out = []
            mon = SessionMonitor([root], 16, 900, out.append, lambda: None, LOG)
            mon.scan_once()
            p = root / "new.jsonl"
            write_jsonl(p, [event("task_started"), response("新会话")])
            mon.scan_once()
            self.assertEqual(out[0]["text"], "新会话")

    def test_24_explicit_attention_only(self):
        self.assertTrue(explicit_attention_event(event("request_user_input")))
        self.assertFalse(explicit_attention_event(event("mcp_tool_call_end")))
        self.assertFalse(explicit_attention_event(event("token_count")))

    def test_25_demand_copy_prefers_latest_complete_final(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = root / "x.jsonl"
            old = response("完整答案", "final_answer", turn="old", message_id="old")
            old["timestamp"] = "2026-08-17T00:00:02Z"
            generating = response("正在生成", "commentary", turn="new", message_id="new")
            generating["timestamp"] = "2026-08-17T00:00:03Z"
            write_jsonl(p, [old, event("task_started", "new"), generating])
            self.assertEqual(latest_complete_reply([root]), "完整答案")

    def test_26_copy_fallback_requires_completed_turn(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = root / "x.jsonl"
            completed = response("旧的完整可见正文", "commentary", turn="old", message_id="old")
            completed["timestamp"] = "2026-08-17T00:00:02Z"
            current = response("新回复还在生成", "commentary", turn="new", message_id="new")
            current["timestamp"] = "2026-08-17T00:00:03Z"
            write_jsonl(p, [event("task_started", "old"), completed, event("task_complete", "old"), event("task_started", "new"), current])
            self.assertEqual(latest_complete_reply([root]), "旧的完整可见正文")

    def test_27_copy_is_exact_and_leaves_no_reply_file(self):
        original = read_unicode()
        marker = "中英混合 GPT Monitor\n第二行。"
        try:
            self.assertEqual(copy_unicode(marker), len(marker))
            self.assertEqual(read_unicode(), marker)
        finally:
            copy_unicode(original)
        self.assertFalse((Path.home() / "Library/Application Support/OpenClose/GPT Monitor/latest_reply.txt").exists())

    def test_28_new_turn_is_announced_once(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            starts = []
            mon = SessionMonitor([root], 16, 900, lambda m: None, lambda: None, LOG, on_reply_start=starts.append)
            mon.scan_once()
            p = root / "new.jsonl"
            write_jsonl(p, [event("task_started", "turn-new"), event("task_started", "turn-new")])
            mon.scan_once()
            mon.scan_once()
            self.assertEqual(len(starts), 1)
            self.assertTrue(starts[0].endswith(":turn-new"))


class AudioAndHotkeyTests(unittest.TestCase):
    class DummyConfig(dict):
        def integer(self, key, *args): return int(self.get(key, 1))
        def number(self, key, *args): return float(self.get(key, 1.0))
        def bool(self, key): return bool(self.get(key, True))

    def test_29_pause_resume_preserves_online_position(self):
        class Player:
            def __init__(self): self.play_calls = 0; self.pause_calls = 0
            def currentTime(self): return 12.75
            def pause(self): self.pause_calls += 1
            def play(self): self.play_calls += 1
        with tempfile.TemporaryDirectory() as td:
            engine = MacAudioEngine(self.DummyConfig(), Path(td), LOG)
            engine.current = SpeechJob("r", "s", "x")
            engine.state = PlaybackState.SPEAKING
            player = Player()
            engine._online_player = player
            self.assertEqual(engine.toggle_pause(), PlaybackState.PAUSED)
            self.assertEqual(engine._online_position, 12.75)
            self.assertEqual(engine.toggle_pause(), PlaybackState.SPEAKING)
            self.assertEqual((player.pause_calls, player.play_calls), (1, 1))

    def test_30_skip_removes_only_current_reply(self):
        with tempfile.TemporaryDirectory() as td:
            engine = MacAudioEngine(self.DummyConfig(), Path(td), LOG)
            engine.current = SpeechJob("r1", "s1", "current")
            engine.queue.extend([SpeechJob("r1", "s2", "same"), SpeechJob("r2", "s3", "next")])
            self.assertEqual(engine.skip_current_reply(), "r1")
            self.assertEqual([x.reply_id for x in engine.queue], ["r2"])

    def test_31_double_click_cancels_single(self):
        calls = []
        hotkeys = GlobalHotkeys(
            lambda: calls.append("single"), lambda: calls.append("double"),
            lambda: None, lambda: calls.append("master"), LOG, 0.05,
        )
        hotkeys._slash_press()
        hotkeys._slash_press()
        time.sleep(0.08)
        self.assertEqual(calls, ["double"])

    def test_31a_exact_master_hotkey_is_single_key_registration(self):
        self.assertEqual(ExactMasterHotkey.M_KEYCODE, 46)
        self.assertEqual(
            ExactMasterHotkey.COMMAND_MODIFIER | ExactMasterHotkey.CONTROL_MODIFIER,
            4352,
        )

    def test_32_online_failure_falls_back_local(self):
        class Engine(MacAudioEngine):
            def _synthesize_online(self, job): raise TimeoutError()
            def _speak_local(self, text): self.fallback = text
        with tempfile.TemporaryDirectory() as td:
            engine = Engine(self.DummyConfig(low_latency=False), Path(td), LOG)
            engine.start()
            engine.enqueue(SpeechJob("r", "s", "fallback text"))
            deadline = time.time() + 2
            while not hasattr(engine, "fallback") and time.time() < deadline:
                time.sleep(0.02)
            engine.stop()
            self.assertEqual(engine.fallback, "fallback text")

    def test_33_low_latency_uses_local_without_online_wait(self):
        class Engine(MacAudioEngine):
            def _synthesize_online(self, job):
                raise AssertionError("online synthesis must not run in low-latency mode")
            def _speak_local(self, text):
                self.spoken = text
        with tempfile.TemporaryDirectory() as td:
            engine = Engine(self.DummyConfig(low_latency=True), Path(td), LOG)
            engine.start()
            engine.enqueue(SpeechJob("r", "s", "立即朗读"))
            deadline = time.time() + 1
            while not hasattr(engine, "spoken") and time.time() < deadline:
                time.sleep(0.01)
            engine.stop()
            self.assertEqual(engine.spoken, "立即朗读")

    def test_34_new_reply_discards_stale_queue(self):
        with tempfile.TemporaryDirectory() as td:
            engine = MacAudioEngine(self.DummyConfig(), Path(td), LOG)
            engine.queue.extend([SpeechJob("old", "old:1", "旧内容"), SpeechJob("new", "new:1", "新内容")])
            engine.begin_reply("new", announce=True, prefer_latest=True)
            self.assertEqual([job.reply_id for job in engine.queue], ["new", "new"])
            self.assertEqual(engine.queue[0].text, "正在回复")
            self.assertIn("old", engine._skipped)

    def test_34a_local_say_uses_configured_voice_and_speed(self):
        class Process:
            returncode = 0
            def poll(self): return 0
        with tempfile.TemporaryDirectory() as td:
            engine = MacAudioEngine(
                self.DummyConfig(local_voice="Tingting", local_wpm=800, local_volume=0.7), Path(td), LOG
            )
            calls = []
            original = mac_audio_module.subprocess.Popen
            try:
                mac_audio_module.subprocess.Popen = lambda command, **kwargs: calls.append(command) or Process()
                engine._speak_local("高速测试")
            finally:
                mac_audio_module.subprocess.Popen = original
            self.assertEqual(calls[0][:6], [
                "/usr/bin/say", "-v", "Tingting", "-r", "800", "[[volm 0.700]]高速测试"
            ])

    def test_34b_audio_worker_survives_one_failed_job(self):
        calls = []
        completed = threading.Event()

        def backend(job, engine):
            calls.append(job.text)
            if job.text == "失败一次":
                raise RuntimeError("simulated speech failure")
            completed.set()

        with tempfile.TemporaryDirectory() as td:
            engine = MacAudioEngine(self.DummyConfig(), Path(td), LOG, audio_backend=backend)
            engine.start()
            engine.enqueue(SpeechJob("r1", "s1", "失败一次"))
            engine.enqueue(SpeechJob("r2", "s2", "继续朗读"))
            self.assertTrue(completed.wait(1))
            self.assertTrue(engine.worker_alive)
            engine.stop()
            self.assertEqual(calls, ["失败一次", "继续朗读"])

    def test_34c_master_mute_pauses_current_clears_queue_and_persists(self):
        class Player:
            def __init__(self): self.play_calls = 0; self.pause_calls = 0
            def currentTime(self): return 8.5
            def pause(self): self.pause_calls += 1
            def play(self): self.play_calls += 1
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            flag = root / "muted.flag"
            engine = MacAudioEngine(self.DummyConfig(), root / "cache", LOG, mute_state_path=flag)
            engine.queue.extend([SpeechJob("old", "s1", "旧内容")])
            engine.current = SpeechJob("current", "s0", "正在朗读")
            engine.state = PlaybackState.SPEAKING
            player = Player()
            engine._online_player = player
            self.assertTrue(engine.set_master_muted(True))
            self.assertTrue(flag.exists())
            self.assertEqual(engine.queue_depth, 0)
            self.assertEqual(engine.state, PlaybackState.PAUSED)
            self.assertEqual(player.pause_calls, 1)
            engine.enqueue(SpeechJob("ignored", "s2", "不应排队"))
            engine.begin_reply("ignored", announce=True, prefer_latest=True)
            self.assertEqual(engine.queue_depth, 0)
            self.assertFalse(engine.set_master_muted(False))
            self.assertEqual(engine.state, PlaybackState.SPEAKING)
            self.assertEqual(player.play_calls, 1)
            self.assertFalse(flag.exists())
            restored = MacAudioEngine(self.DummyConfig(), root / "cache2", LOG, mute_state_path=flag)
            self.assertFalse(restored.master_muted)
            restored.begin_reply("new", announce=False, prefer_latest=True)
            restored.enqueue(SpeechJob("new", "s3", "恢复后的新回复"))
            self.assertEqual(restored.queue_depth, 1)


class ProcessAndLaunchTests(unittest.TestCase):
    def test_35_pid_reuse_detected(self):
        rec = process_record("controller")
        self.assertTrue(validate_pid_record(rec, "controller"))
        rec["create_time"] -= 100
        self.assertFalse(validate_pid_record(rec, "controller"))

    def test_36_controller_and_listener_locks_are_atomic(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "controller.lock"
            a, b = InstanceLock(p), InstanceLock(p)
            self.assertTrue(a.acquire())
            self.assertFalse(b.acquire())
            a.release()
            self.assertTrue(b.acquire())
            b.release()

    def test_37_launch_agent_payload_valid(self):
        payload = launch_agent_payload("/Applications/GPT Monitor.app/Contents/MacOS/GPT Monitor")
        encoded = plistlib.dumps(payload)
        decoded = plistlib.loads(encoded)
        self.assertTrue(decoded["RunAtLoad"])
        self.assertTrue(decoded["KeepAlive"])
        self.assertEqual(decoded["Label"], "com.openclose.gptmonitor")
        self.assertIn("--daemon", decoded["ProgramArguments"])

    def test_38_speech_segmentation_bounded_and_lossless(self):
        text = "一句中文。" * 500
        pieces = split_for_speech(text, 200)
        self.assertTrue(all(len(x) <= 201 for x in pieces))
        self.assertEqual("".join(pieces), text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
