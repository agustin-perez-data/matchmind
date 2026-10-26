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

# Defaults, both picked by ear: HD voices in a permanent excited style, Mexican for Spanish and American for English. Override per language with MATCHMIND_VOICE_ES / _EN
# (any voice from the region's list; HD voices ignore prosody, expressive voices take a style on goals).
DEFAULT_VOICES = {"es": "es-MX-Alejo:MAI-Voice-2", "en": "en-US-Ethan:MAI-Voice-2"}
LOCALES = {"es": "es-AR", "en": "en-GB"}
# Voices that always speak in a style (a commentator is excited by trade), and voices that only get it on goals.
ALWAYS_STYLE = {"es-MX-Alejo:MAI-Voice-2": "excited", "es-MX-Alejo:MAI-Voice-2-Flash": "excited",
                "en-US-Ethan:MAI-Voice-2": "excited", "en-US-Ethan:MAI-Voice-2-Flash": "excited"}
EXCITED_STYLE = {"en-US-DavisNeural": "excited", "en-US-JasonNeural": "excited", "en-US-GuyNeural": "excited"}
OUTPUT_FORMAT = "audio-48khz-96kbitrate-mono-mp3"
MAX_CHARS = 600


def voice_for(lang: str) -> str:
    lang = lang if lang in DEFAULT_VOICES else "en"
    return os.environ.get(f"MATCHMIND_VOICE_{lang.upper()}") or DEFAULT_VOICES[lang]


def speech_config() -> dict | None:
    """Key and region, or None when Speech is not configured."""
    key = os.environ.get("AZURE_SPEECH_KEY") or os.environ.get("AZURE_OPENAI_API_KEY")
    region = os.environ.get("AZURE_SPEECH_REGION", "eastus2")
    return {"key": key, "region": region} if key else None


def ssml(text: str, lang: str) -> str:
    lang = lang if lang in DEFAULT_VOICES else "en"
    voice = voice_for(lang)
    locale = voice.split("-")[0] + "-" + voice.split("-")[1] if voice.count("-") >= 2 else LOCALES[lang]
    text = re.sub(r"\s+", " ", text.strip())[:MAX_CHARS]
    excited = bool(re.search(r"GO+L|GOAL|¡|!", text))
    hd = "DragonHD" in voice or "MAI-Voice" in voice  # HD voices do their own prosody
    inner = escape(text)
    style = ALWAYS_STYLE.get(voice) or (EXCITED_STYLE.get(voice) if excited else None)
    if style:
        inner = f"<mstts:express-as style='{style}'>{inner}</mstts:express-as>"
    elif not hd:
        rate, pitch = ("1.12", "+6%") if excited else ("1.06", "+0%")
        inner = f"<prosody rate='{rate}' pitch='{pitch}'>{inner}</prosody>"
    return (
        f"<speak version='1.0' xmlns:mstts='https://www.w3.org/2001/mstts' xml:lang='{locale}'>"
        f"<voice name='{voice}'>{inner}</voice></speak>"
    )


def cache_path(cache_dir: Path, text: str, lang: str) -> Path:
    digest = hashlib.sha1(f"{lang}:{voice_for(lang)}:{text.strip()}".encode()).hexdigest()
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
