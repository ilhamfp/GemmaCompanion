"""Low-latency offline STT through one resident whisper.cpp server."""

from __future__ import annotations

import json
import mimetypes
import os
import re
import uuid
import urllib.error
import urllib.request
from pathlib import Path

from .stt import TranscriptionError, transcribe as transcribe_cli

DEFAULT_ENDPOINT = "http://127.0.0.1:8178/inference"
COMPANION_SPEECH_PROMPT = (
    "Look left. Look right. Look up. Look down. Look center. What do you see? "
    "Find my AirPods. AirPods charging case. Find my smartphone. Find my iPhone. "
    "Is this a scam? What does this say? Volume up. Volume down."
)


def _multipart(audio_path: Path) -> tuple[bytes, str]:
    boundary = f"gemma-companion-{uuid.uuid4().hex}"
    body = bytearray()

    def field(name: str, value: str) -> None:
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.extend(value.encode())
        body.extend(b"\r\n")

    field("response_format", "json")
    field("language", "en")
    field("temperature", "0")
    field("prompt", COMPANION_SPEECH_PROMPT)
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        (
            f'Content-Disposition: form-data; name="file"; filename="{audio_path.name}"\r\n'
            f"Content-Type: {mimetypes.guess_type(audio_path.name)[0] or 'audio/wav'}\r\n\r\n"
        ).encode()
    )
    body.extend(audio_path.read_bytes())
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    return bytes(body), boundary


def transcribe_fast(
    wav_path: str | os.PathLike[str],
    *,
    endpoint: str | None = None,
    fallback_to_cli: bool = True,
) -> str:
    """Transcribe one WAV using the resident Q5_1 Whisper tiny server."""

    audio_path = Path(wav_path).expanduser().resolve()
    if not audio_path.is_file():
        raise TranscriptionError(f"audio does not exist: {audio_path}")
    target = endpoint or os.environ.get("GEMMA_WHISPER_ENDPOINT", DEFAULT_ENDPOINT)
    body, boundary = _multipart(audio_path)
    request = urllib.request.Request(
        target,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        raw = str(payload.get("text") or "")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        if fallback_to_cli:
            return transcribe_cli(audio_path)
        raise TranscriptionError(f"resident whisper.cpp request failed: {exc}") from exc

    transcript = re.sub(r"\[[^]]+\]", " ", raw)
    transcript = " ".join(transcript.split()).strip()
    if not transcript:
        raise TranscriptionError("resident whisper.cpp returned an empty transcript")
    return transcript
