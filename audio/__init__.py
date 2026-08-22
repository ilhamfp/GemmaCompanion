"""Offline microphone, speech recognition, and speech synthesis APIs."""

from .mic import record_until_silence
from .speaker import play_audio
from .stt import transcribe
from .tts import speak

__all__ = ["play_audio", "record_until_silence", "speak", "transcribe"]
