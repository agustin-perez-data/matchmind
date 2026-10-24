"""The commentator's voice: Azure AI Speech neural text-to-speech, cached per line.

The Foundry resource is a multi-service Azure AI Services account, so the same key
speaks: Speech lives at the regional endpoint. Every narration line is synthesised
once and kept as MP3 under <data>/cache/tts, so a replay served from the agent cache
costs no Speech calls either.

    GET /tts?text=...&lang=es|en  ->  audio/mpeg

Voices: Spanish is rioplatense (es-AR), English is a British broadcast voice.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path
from xml.sax.saxutils import escape

import httpx

log = logging.getLogger("matchmind.tts")

VOICES = {"es": "es-AR-TomasNeural", "en": "en-GB-RyanNeural"}
LOCALES = {"es": "es-AR", "en": "en-GB"}
OUTPUT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"
MAX_CHARS = 600


def speech_config() -> dict | None:
    """Key and region, or None when Speech is not configured."""
    key = os.environ.get("AZURE_SPEECH_KEY") or os.environ.get("AZURE_OPENAI_API_KEY")
    region = os.environ.get("AZURE_SPEECH_REGION", "eastus2")
    return {"key": key, "region": region} if key else None


def ssml(text: str, lang: str) -> str:
    lang = lang if lang in VOICES else "en"
    text = re.sub(r"\s+", " ", text.strip())[:MAX_CHARS]
    excited = bool(re.search(r"GO+L|GOAL|¡|!", text))
    rate, pitch = ("1.12", "+6%") if excited else ("1.06", "+0%")
    return (
        f"<speak version='1.0' xml:lang='{LOCALES[lang]}'>"
        f"<voice name='{VOICES[lang]}'><prosody rate='{rate}' pitch='{pitch}'>{escape(text)}</prosody></voice></speak>"
    )


def cache_path(cache_dir: Path, text: str, lang: str) -> Path:
    digest = hashlib.sha1(f"{lang}:{VOICES.get(lang, VOICES['en'])}:{text.strip()}".encode("utf-8")).hexdigest()
    return cache_dir / f"{digest}.mp3"


class Speaker:
    """Synthesises lines through Azure Speech with a disk cache. `transport` is injectable for tests."""

    def __init__(self, cache_dir: Path, transport: httpx.AsyncBaseTransport | None = None):
        self.cache_dir = cache_dir
        self.transport = transport
        self.calls = 0

    async def say(self, text: str, lang: str) -> bytes | None:
        cfg = speech_config()
        if cfg is None or not text.strip():
            return None
        path = cache_path(self.cache_dir, text, lang)
        if path.is_file():
            return path.read_bytes()
        url = f"https://{cfg['region']}.tts.speech.microsoft.com/cognitiveservices/v1"
        headers = {"Ocp-Apim-Subscription-Key": cfg["key"], "Content-Type": "application/ssml+xml",
                   "X-Microsoft-OutputFormat": OUTPUT_FORMAT, "User-Agent": "matchmind"}
        self.calls += 1
        async with httpx.AsyncClient(transport=self.transport, timeout=20) as client:
            r = await client.post(url, headers=headers, content=ssml(text, lang).encode("utf-8"))
        if r.status_code != 200 or not r.content:
            log.warning("speech synthesis failed: %s %s", r.status_code, r.text[:120])
            return None
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_bytes(r.content)
        except OSError as exc:
            log.warning("could not cache speech %s: %r", path, exc)
        return r.content
