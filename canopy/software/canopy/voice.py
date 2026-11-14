"""Voice interface: wake word or push-to-talk -> speech-to-text -> Claude -> text-to-speech.

Everything runs locally except the Claude call.  Backends are injectable so the pipeline is testable without audio
hardware; the default backends need the optional packages listed in pyproject [voice].
"""
from __future__ import annotations
import logging, subprocess, tempfile, wave

log = logging.getLogger("canopy.voice")
RATE = 16000


class WhisperSTT:
    def __init__(self, model="base.en"):
        from faster_whisper import WhisperModel
        self.m = WhisperModel(model, device="cpu", compute_type="int8")
    def transcribe(self, pcm16: bytes) -> str:
        import numpy as np
        audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768
        segs, _ = self.m.transcribe(audio, language="en", beam_size=1, vad_filter=True)
        return " ".join(s.text.strip() for s in segs).strip()


class PiperTTS:
    def __init__(self, voice: str, device="default"): self.voice, self.device = voice, device
    def say(self, text: str):
        with tempfile.NamedTemporaryFile(suffix=".wav") as f:
            subprocess.run(["piper", "--model", self.voice, "--output_file", f.name], input=text.encode(), check=True, timeout=60)
            subprocess.run(["aplay", "-q", "-D", self.device, f.name], check=True, timeout=120)


class Mic:
    """16 kHz mono capture from the on-board I2S microphones via ALSA (sounddevice)."""
    def __init__(self, device="default"):
        import sounddevice as sd
        self.stream = sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=1280, device=device); self.stream.start()
    def chunk(self) -> bytes: return bytes(self.stream.read(1280)[0])


class WakeWord:
    def __init__(self, name="hey_jarvis"):
        from openwakeword.model import Model
        self.m, self.name = Model(wakeword_models=[name]), name
    def heard(self, pcm16: bytes) -> bool:
        import numpy as np
        return self.m.predict(np.frombuffer(pcm16, dtype=np.int16)).get(self.name, 0) > 0.5


def rms(pcm16: bytes) -> float:
    import array, math
    a = array.array("h", pcm16)
    return math.sqrt(sum(x * x for x in a) / len(a)) if a else 0.0


class VoiceLoop:
    def __init__(self, assistant, mic, stt, tts, wake=None, button=None, max_s=12, silence_s=1.2, silence_rms=350):
        self.a, self.mic, self.stt, self.tts, self.wake, self.button = assistant, mic, stt, tts, wake, button
        self.max_chunks = int(max_s * RATE / 1280); self.sil_chunks = int(silence_s * RATE / 1280); self.sil = silence_rms

    def triggered(self, chunk: bytes) -> bool:
        return bool((self.button and self.button()) or (self.wake and self.wake.heard(chunk)))

    def record(self) -> bytes:
        buf, quiet = [], 0
        for _ in range(self.max_chunks):
            c = self.mic.chunk(); buf.append(c)
            quiet = quiet + 1 if rms(c) < self.sil else 0
            if quiet >= self.sil_chunks and len(buf) > self.sil_chunks + 3: break
        return b"".join(buf)

    def once(self) -> str | None:
        """Handle one interaction if triggered; returns the spoken reply (or None)."""
        if not self.triggered(self.mic.chunk()): return None
        text = self.stt.transcribe(self.record())
        if not text: return None
        log.info("heard: %s", text)
        try: reply = self.a.ask(text, source="voice")
        except Exception as e:
            log.warning("assistant failed: %s", e); reply = "Sorry, I can't reach the assistant right now. Automation is still running."
        self.tts.say(reply); return reply

    def run(self):
        while True:
            try: self.once()
            except Exception: log.exception("voice loop error")


def start(engine, assistant):
    import threading
    v = engine.cfg["voice"]
    loop = VoiceLoop(assistant, Mic(v["alsa_device"]), WhisperSTT(v["stt_model"]), PiperTTS(v["piper_voice"], v["alsa_device"]),
                     WakeWord(v["wake_word"]) if v.get("wake_word") else None, getattr(engine.board, "button", None))
    threading.Thread(target=loop.run, daemon=True).start(); return loop
