"""Commentator voice: SSML, caching and the /tts route, with Azure Speech mocked."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from matchmind.api.app import create_app
from matchmind.api.tts import Speaker, cache_path, ssml
from tests.test_api import data_dir


def fake_speech(status=200, body=b"ID3fake-mp3"):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, content=body, headers={"content-type": "audio/mpeg"})

    return httpx.MockTransport(handler), seen


def test_ssml_picks_the_rioplatense_voice_and_gets_excited_on_goals(monkeypatch):
    monkeypatch.delenv("MATCHMIND_VOICE_ES", raising=False)
    monkeypatch.delenv("MATCHMIND_VOICE_EN", raising=False)
    es = ssml("¡GOOOL de Northbridge! Vantham la clavó.", "es")
    assert "es-MX-Alejo:MAI-Voice-2" in es and "xml:lang='es-MX'" in es and "<mstts:express-as style='excited'>" in es
    assert "express-as style='excited'" in ssml("Pase largo de Thames.", "es")  # the commentator is always excited
    monkeypatch.setenv("MATCHMIND_VOICE_ES", "es-AR-TomasNeural")
    tomas = ssml("¡GOOOL!", "es")
    assert "es-AR-TomasNeural" in tomas and "rate='1.12'" in tomas and "express-as" not in tomas
    monkeypatch.delenv("MATCHMIND_VOICE_ES")
    en = ssml("A quiet spell for Thames, 55% of the ball.", "en")
    assert "en-US-Ethan:MAI-Voice-2" in en and "express-as style='excited'" in en and "prosody" not in en and "&" not in en
    monkeypatch.setenv("MATCHMIND_VOICE_EN", "en-GB-Ryan:DragonHDLatestNeural")
    assert "prosody" not in ssml("x", "en") and "express-as" not in ssml("x", "en")  # HD voices without a style: nothing added
    monkeypatch.delenv("MATCHMIND_VOICE_EN")
    assert "&lt;b&gt;" in ssml("x <b> y", "en")  # markup is escaped, never injected
    assert ssml("hi", "xx").count("en-US") == 2  # unknown language falls back to English
    # an English voice with a goal-only style gets it on goals, nothing otherwise
    monkeypatch.setenv("MATCHMIND_VOICE_EN", "en-US-DavisNeural")
    assert "<mstts:express-as style='excited'>" in ssml("GOAL!", "en")
    assert "express-as" not in ssml("A quiet spell.", "en") and "prosody" in ssml("A quiet spell.", "en")


def test_speaker_calls_speech_once_and_serves_the_cache_after(tmp_path, monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "k")
    monkeypatch.setenv("AZURE_SPEECH_REGION", "eastus2")
    transport, seen = fake_speech()
    sp = Speaker(tmp_path, transport=transport)
    first = asyncio.run(sp.say("¡Gol!", "es"))
    again = asyncio.run(sp.say("¡Gol!", "es"))
    assert first == again == b"ID3fake-mp3" and len(seen) == 1 and sp.calls == 1
    assert cache_path(tmp_path, "¡Gol!", "es").is_file()
    assert seen[0].url.host == "eastus2.tts.speech.microsoft.com" and seen[0].headers["Ocp-Apim-Subscription-Key"] == "k"
    assert asyncio.run(sp.say("¡Gol!", "en")) == b"ID3fake-mp3" and len(seen) == 2  # another voice is another line
    assert asyncio.run(sp.say("   ", "es")) is None and len(seen) == 2


def test_speaker_is_quiet_without_a_key_and_on_errors(tmp_path, monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_SPEECH_KEY", raising=False)
    assert asyncio.run(Speaker(tmp_path, transport=fake_speech()[0]).say("x", "en")) is None
    monkeypatch.setenv("AZURE_SPEECH_KEY", "k")
    transport, _ = fake_speech(status=429, body=b"slow down")
    assert asyncio.run(Speaker(tmp_path, transport=transport).say("x", "en")) is None
    assert not list(tmp_path.glob("*.mp3"))


@pytest.fixture()
def tts_client(data_dir, tmp_path, monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "k")
    transport, seen = fake_speech()
    app = create_app(data_dir=data_dir, enable_agents=False, cache=False, speech_transport=transport)
    with TestClient(app) as c:
        yield c, seen


def test_tts_route_streams_mp3_and_caches(tts_client):
    client, seen = tts_client
    r = client.get("/tts", params={"text": "¡Gol de Thames!", "lang": "es"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("audio/mpeg") and r.content == b"ID3fake-mp3"
    assert "max-age" in r.headers.get("cache-control", "")
    client.get("/tts", params={"text": "¡Gol de Thames!", "lang": "es"})
    assert len(seen) == 1
    assert client.get("/tts", params={"text": "", "lang": "es"}).status_code == 422
    assert client.get("/tts", params={"text": "x" * 2000, "lang": "en"}).status_code == 422
    assert client.get("/health").json()["speech"] is True
