"""The groundedness guardrail: off by default, never blocks, and its verdict lands in the moment's trace."""

from __future__ import annotations

import asyncio

from matchmind.agents import guardrails

RESULT = {"analyst": {"headline": "x"}, "viewers": {"commentator:es:-": {"narration": {"text": "¡Gol de Ferrant!"}},
                                                     "analyst:en:-": {"narration": None}},
          "trace": [{"t": 10, "kind": "stage", "agent": None, "stage": "fan-out"}]}


def test_narration_lines_only_for_viewers_with_text():
    assert guardrails.narration_lines(RESULT) == [("commentator:es:-", "¡Gol de Ferrant!")]


def test_disabled_by_default_is_a_no_op(monkeypatch):
    monkeypatch.delenv("MATCHMIND_GUARDRAILS", raising=False)
    result = {**RESULT, "trace": list(RESULT["trace"])}
    assert asyncio.run(guardrails.check_moment(result, "{}")) == []
    assert result["trace"] == RESULT["trace"]


def test_enabled_appends_a_guardrail_entry_and_survives_errors(monkeypatch):
    monkeypatch.setenv("MATCHMIND_GUARDRAILS", "1")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://x.cognitiveservices.azure.com/")
    calls = []

    def fake_detect(text, sources):
        calls.append((text, sources))
        return {"ungroundedDetected": True, "ungroundedPercentage": 0.25, "ungroundedDetails": [{"text": "de Ferrant"}]}

    monkeypatch.setattr(guardrails, "detect_groundedness", fake_detect)
    result = {**RESULT, "trace": list(RESULT["trace"])}
    entries = asyncio.run(guardrails.check_moment(result, '{"clock": "12:00"}'))
    assert len(entries) == 1 and entries[0]["kind"] == "guardrail" and entries[0]["checked"] and entries[0]["grounded"] is False
    assert entries[0]["ungrounded_percentage"] == 0.25 and entries[0]["ungrounded_text"] == ["de Ferrant"]
    assert result["trace"][-1] is entries[0] and calls[0][1] == ['{"clock": "12:00"}']

    def broken(text, sources):
        raise RuntimeError("503")

    monkeypatch.setattr(guardrails, "detect_groundedness", broken)
    result = {**RESULT, "trace": []}
    entries = asyncio.run(guardrails.check_moment(result, "{}"))
    assert entries[0]["checked"] is False and "503" in entries[0]["error"]


def test_context_text_keeps_only_the_facts():
    ctx = {"clock": "10:00", "score": {"A": 1}, "viewer_profile": {"mode": "fan"}, "moment": {"kind": "goal"}}
    text = guardrails.context_text(ctx)
    assert "viewer_profile" not in text and '"clock": "10:00"' in text
