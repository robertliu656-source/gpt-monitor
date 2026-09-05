from __future__ import annotations

from i18n import message

from collections import deque
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import asyncio
import logging
import os
import signal
import subprocess
import tempfile
import threading
import time


class PlaybackState(str, Enum):
    RUNNING = "RUNNING"
    SPEAKING = "SPEAKING"
    PAUSED = "PAUSED"
    SKIPPING_CURRENT = "SKIPPING_CURRENT"
    STOPPING = "STOPPING"


@dataclass(frozen=True)
class SpeechJob:
    reply_id: str
    segment_id: str
    text: str
    local_only: bool = False


class MacAudioEngine:
    def __init__(
        self, config, cache_dir: Path, logger: logging.Logger, audio_backend=None,
        mute_state_path: Path | None = None,
    ) -> None:
        self.config = config
        self.cache_dir = cache_dir
        self.logger = logger
        self.queue: deque[SpeechJob] = deque()
        self.condition = threading.Condition()
        self.state = PlaybackState.RUNNING
        self.current: SpeechJob | None = None
        self._online_player = None
        self._local_synth = None
        self._local_process: subprocess.Popen | None = None
        self._skipped: set[str] = set()
        self._stop = False
        self._thread: threading.Thread | None = None
        self._backend = audio_backend
        self._online_position = 0.0
        self._mute_state_path = mute_state_path
        self.muted = bool(mute_state_path and mute_state_path.exists())

    @property
    def is_speaking(self) -> bool:
        with self.condition:
            return self.current is not None and self.state in {PlaybackState.SPEAKING, PlaybackState.PAUSED}

    @property
    def paused(self) -> bool:
        with self.condition:
            return self.state == PlaybackState.PAUSED

    @property
    def master_muted(self) -> bool:
        with self.condition:
            return self.muted

    @property
    def current_reply_id(self) -> str | None:
        with self.condition:
            return self.current.reply_id if self.current else None

    @property
    def worker_alive(self) -> bool:
        with self.condition:
            return bool(self._thread and self._thread.is_alive())

    @property
    def queue_depth(self) -> int:
        with self.condition:
            return len(self.queue)

    def _ensure_worker_locked(self) -> None:
        if self._stop:
            return
        if not self._thread or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._worker, name="gpt-monitor-audio", daemon=True)
            self._thread.start()
            self.logger.info("audio_worker_started")

    def start(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        with self.condition:
            self._ensure_worker_locked()

    def enqueue(self, job: SpeechJob) -> None:
        with self.condition:
            if self.muted or job.reply_id in self._skipped:
                return
            self._ensure_worker_locked()
            self.queue.append(job)
            self.condition.notify_all()

    def announce_local(self, phrase: str, event_id: str = "announcement") -> None:
        self.enqueue(SpeechJob(event_id, f"{event_id}:{time.time_ns()}", phrase, local_only=True))

    def begin_reply(self, reply_id: str, announce: bool = True, prefer_latest: bool = True) -> None:
        """Prioritize a newly-started turn and optionally announce it without cloud delay."""
        with self.condition:
            if self.muted:
                self._skipped.add(reply_id)
                self.queue.clear()
                self.condition.notify_all()
                self.logger.info("reply_ignored master_muted=true reply_id_hash=%s", hash(reply_id))
                return
            if prefer_latest:
                stale = {job.reply_id for job in self.queue if job.reply_id != reply_id}
                if self.current is not None and self.current.reply_id != reply_id:
                    stale.add(self.current.reply_id)
                self._skipped.update(stale)
                self.queue = deque(job for job in self.queue if job.reply_id == reply_id)
                if self.current is not None and self.current.reply_id != reply_id:
                    self.state = PlaybackState.SKIPPING_CURRENT
                    if self._online_player is not None:
                        try:
                            self._online_player.stop()
                        except Exception:
                            pass
                    if self._local_synth is not None:
                        try:
                            from AVFoundation import AVSpeechBoundaryImmediate
                            self._local_synth.stopSpeakingAtBoundary_(AVSpeechBoundaryImmediate)
                        except Exception:
                            pass
                    self._terminate_local_process()
            self._skipped.discard(reply_id)
            if announce and not any(job.segment_id.endswith(":reply-start") for job in self.queue):
                self.queue.appendleft(SpeechJob(
                    reply_id,
                    f"{reply_id}:reply-start",
                    message(self.config, "reply_start"),
                    local_only=True,
                ))
            self.condition.notify_all()
        self.logger.info(
            "reply_priority reply_id_hash=%s announce=%s prefer_latest=%s",
            hash(reply_id), announce, prefer_latest,
        )

    def toggle_pause(self) -> PlaybackState:
        with self.condition:
            if self.muted:
                self.state = PlaybackState.RUNNING
                self.logger.info("playback_state state=%s master_muted=true", self.state.value)
                return self.state
            if self.state == PlaybackState.PAUSED:
                if self._online_player is not None:
                    try:
                        self._online_player.play()
                    except Exception:
                        pass
                if self._local_synth is not None:
                    try:
                        self._local_synth.continueSpeaking()
                    except Exception:
                        pass
                if self._local_process is not None and self._local_process.poll() is None:
                    try:
                        self._local_process.send_signal(signal.SIGCONT)
                    except Exception:
                        pass
                self.state = PlaybackState.SPEAKING if self.current else PlaybackState.RUNNING
            elif self.current is not None:
                if self._online_player is not None:
                    try:
                        self._online_position = float(self._online_player.currentTime())
                        self._online_player.pause()
                    except Exception:
                        pass
                if self._local_synth is not None:
                    try:
                        from AVFoundation import AVSpeechBoundaryImmediate
                        self._local_synth.pauseSpeakingAtBoundary_(AVSpeechBoundaryImmediate)
                    except Exception:
                        pass
                if self._local_process is not None and self._local_process.poll() is None:
                    try:
                        self._local_process.send_signal(signal.SIGSTOP)
                    except Exception:
                        pass
                self.state = PlaybackState.PAUSED
            self.condition.notify_all()
            self.logger.info("playback_state state=%s", self.state.value)
            return self.state

    def set_master_muted(self, muted: bool) -> bool:
        muted = bool(muted)
        with self.condition:
            self.muted = muted
            if muted:
                self.queue.clear()
                if self.current is not None:
                    if self._online_player is not None:
                        try:
                            self._online_position = float(self._online_player.currentTime())
                            self._online_player.pause()
                        except Exception:
                            pass
                    if self._local_synth is not None:
                        try:
                            from AVFoundation import AVSpeechBoundaryImmediate
                            self._local_synth.pauseSpeakingAtBoundary_(AVSpeechBoundaryImmediate)
                        except Exception:
                            pass
                    if self._local_process is not None and self._local_process.poll() is None:
                        try:
                            self._local_process.send_signal(signal.SIGSTOP)
                        except Exception:
                            pass
                    self.state = PlaybackState.PAUSED
                else:
                    self.state = PlaybackState.RUNNING
            elif self.current is not None and self.state == PlaybackState.PAUSED:
                if self._online_player is not None:
                    try:
                        self._online_player.play()
                    except Exception:
                        pass
                if self._local_synth is not None:
                    try:
                        self._local_synth.continueSpeaking()
                    except Exception:
                        pass
                if self._local_process is not None and self._local_process.poll() is None:
                    try:
                        self._local_process.send_signal(signal.SIGCONT)
                    except Exception:
                        pass
                self.state = PlaybackState.SPEAKING
            elif self.current is None:
                self.state = PlaybackState.RUNNING
            self.condition.notify_all()
        if self._mute_state_path is not None:
            self._mute_state_path.parent.mkdir(parents=True, exist_ok=True)
            if muted:
                self._mute_state_path.write_text("muted\n", encoding="utf-8")
            else:
                self._mute_state_path.unlink(missing_ok=True)
        self.logger.info("master_mute changed=true muted=%s", muted)
        return muted

    def toggle_master_mute(self) -> bool:
        return self.set_master_muted(not self.master_muted)

    def resume_if_paused(self) -> None:
        if self.paused:
            self.toggle_pause()

    def skip_current_reply(self) -> str | None:
        with self.condition:
            reply_id = self.current.reply_id if self.current else None
            if not reply_id:
                return None
            self.state = PlaybackState.SKIPPING_CURRENT
            self._skipped.add(reply_id)
            self.queue = deque(job for job in self.queue if job.reply_id != reply_id)
            if self._online_player is not None:
                try:
                    self._online_player.stop()
                except Exception:
                    pass
            if self._local_synth is not None:
                try:
                    from AVFoundation import AVSpeechBoundaryImmediate
                    self._local_synth.stopSpeakingAtBoundary_(AVSpeechBoundaryImmediate)
                except Exception:
                    pass
            self._terminate_local_process()
            self.condition.notify_all()
            self.logger.info("reply_skipped reply_id_hash=%s", hash(reply_id))
            return reply_id

    def stop(self) -> None:
        with self.condition:
            self._stop = True
            self.state = PlaybackState.STOPPING
            if self._online_player is not None:
                try:
                    self._online_player.stop()
                except Exception:
                    pass
            if self._local_synth is not None:
                try:
                    self._local_synth.stopSpeakingAtBoundary_(0)
                except Exception:
                    pass
            self._terminate_local_process()
            self.condition.notify_all()
        if self._thread:
            self._thread.join(timeout=5)
        self._cleanup_cache()

    def play_alert(self, sound: Path, count: int = 1) -> None:
        if self.master_muted:
            return
        if not sound.exists():
            self.logger.error("alert_sound_missing file=%s", sound.name)
            return
        def run() -> None:
            for _ in range(max(1, count)):
                try:
                    subprocess.run(["/usr/bin/afplay", str(sound)], timeout=30, check=False)
                except Exception as exc:
                    self.logger.warning("alert_play_failed reason=%s", type(exc).__name__)
        threading.Thread(target=run, name="gpt-monitor-alert", daemon=True).start()

    def _worker(self) -> None:
        while True:
            with self.condition:
                while not self.queue and not self._stop:
                    if self.state != PlaybackState.PAUSED:
                        self.state = PlaybackState.RUNNING
                    self.condition.wait(timeout=1)
                if self._stop:
                    return
                job = self.queue.popleft()
                if self.muted or job.reply_id in self._skipped:
                    continue
                self.current = job
                self.state = PlaybackState.SPEAKING
            temp_path: Path | None = None
            try:
                if self._backend is not None:
                    self._backend(job, self)
                elif job.local_only or self.config.bool("low_latency"):
                    if not job.local_only:
                        self.logger.info("low_latency_local segment_id_hash=%s", hash(job.segment_id))
                    self._speak_local(job.text)
                else:
                    try:
                        temp_path = self._synthesize_online(job)
                        self._play_online(temp_path, job.reply_id)
                    except Exception as exc:
                        self.logger.warning(
                            "online_voice_failed segment_id_hash=%s reason=%s fallback=local",
                            hash(job.segment_id), type(exc).__name__,
                        )
                        self._speak_local(job.text)
            except Exception as exc:
                self.logger.exception(
                    "audio_job_failed segment_id_hash=%s reason=%s continue=true",
                    hash(job.segment_id), type(exc).__name__,
                )
            finally:
                if temp_path:
                    try:
                        temp_path.unlink(missing_ok=True)
                    except OSError:
                        pass
                with self.condition:
                    self._online_player = None
                    self._local_synth = None
                    self._local_process = None
                    self.current = None
                    if self.state != PlaybackState.STOPPING:
                        self.state = PlaybackState.RUNNING
                    self.condition.notify_all()

    def _synthesize_online(self, job: SpeechJob) -> Path:
        import edge_tts
        fd, name = tempfile.mkstemp(prefix="gptm_", suffix=".mp3", dir=self.cache_dir)
        os.close(fd)
        path = Path(name)

        async def synthesize() -> None:
            communicator = edge_tts.Communicate(
                job.text,
                voice=self.config["voice"],
                rate=self.config["edge_rate"],
                volume=self.config["edge_volume"],
            )
            await communicator.save(str(path))

        try:
            asyncio.run(asyncio.wait_for(synthesize(), timeout=35))
        except Exception:
            path.unlink(missing_ok=True)
            raise
        if not path.exists() or path.stat().st_size < 100:
            path.unlink(missing_ok=True)
            raise RuntimeError("no_audio")
        return path

    def _play_online(self, path: Path, reply_id: str) -> None:
        from AVFoundation import AVAudioPlayer
        from Foundation import NSURL
        result = AVAudioPlayer.alloc().initWithContentsOfURL_error_(NSURL.fileURLWithPath_(str(path)), None)
        player = result[0] if isinstance(result, tuple) else result
        if player is None:
            raise RuntimeError("player_init_failed")
        player.prepareToPlay()
        with self.condition:
            self._online_player = player
            while self.state == PlaybackState.PAUSED and not self._stop and reply_id not in self._skipped:
                self.condition.wait(timeout=0.2)
            if self._stop or reply_id in self._skipped:
                return
        if not player.play():
            raise RuntimeError("player_start_failed")
        while True:
            with self.condition:
                if self._stop or reply_id in self._skipped:
                    player.stop()
                    return
                paused = self.state == PlaybackState.PAUSED
            if not paused and not player.isPlaying():
                return
            time.sleep(0.03)

    def _speak_local(self, text: str) -> None:
        if self.master_muted:
            return
        voice = self.config["local_voice"] or "Tingting"
        if voice == "auto_zh_CN":
            voice = "Tingting"
        wpm = self.config.integer("local_wpm", 120, 900)
        volume = self.config.number("local_volume", 0.0, 1.0)
        spoken_text = f"[[volm {volume:.3f}]]{text}"
        last_error: Exception | None = None
        for attempt in (1, 2):
            process: subprocess.Popen | None = None
            try:
                process = subprocess.Popen(
                    ["/usr/bin/say", "-v", voice, "-r", str(wpm), spoken_text],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                with self.condition:
                    self._local_process = process
                    if self.state == PlaybackState.PAUSED:
                        try:
                            process.send_signal(signal.SIGSTOP)
                        except Exception:
                            pass
                while process.poll() is None:
                    with self.condition:
                        if self._stop or (self.current and self.current.reply_id in self._skipped):
                            self._terminate_local_process()
                            return
                    time.sleep(0.03)
                if process.returncode not in {0, None}:
                    raise RuntimeError(f"local_say_failed_{process.returncode}")
                return
            except Exception as exc:
                last_error = exc
                if self.master_muted:
                    return
                if attempt == 1:
                    self.logger.warning(
                        "local_voice_retry reason=%s attempt=2", type(exc).__name__
                    )
                    time.sleep(0.15)
            finally:
                with self.condition:
                    if self._local_process is process:
                        self._local_process = None
        assert last_error is not None
        raise last_error

    def _terminate_local_process(self) -> None:
        process = self._local_process
        if process is None or process.poll() is not None:
            return
        try:
            process.send_signal(signal.SIGCONT)
        except Exception:
            pass
        try:
            process.terminate()
            process.wait(timeout=1)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    def _cleanup_cache(self) -> None:
        for path in self.cache_dir.glob("gptm_*.mp3"):
            try:
                path.unlink()
            except OSError:
                pass
