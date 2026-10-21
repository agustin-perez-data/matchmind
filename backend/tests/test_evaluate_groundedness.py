"""Groundedness harness plumbing with a fake evaluator (the SDK's model-based evaluator is not called)."""

from __future__ import annotations

import json

from matchmind.agents.evaluate_groundedness import cached_insights, context_text, contexts_for, items_to_score, score_items, summarize
from matchmind.generate_match import write_match


class FakeEvaluator:
    def __init__(self):
        self.calls = []

    def __call__(self, *, query, context, response):
        self.calls.append((query, context, response))
        score = 5 if "Okafor" in response or "fake" in response else 2
        return {"groundedness": float(score), "gpt_groundedness": float(score), "groundedness_reason": "fake reason", "groundedness_result": "pass"}


def test_contexts_are_rebuilt_per_key_event_and_cached_insights_are_read(match, tmp_path):
    events, meta = match
    write_match(events, meta, out_dir=tmp_path)
    meta2, contexts = contexts_for(meta["match_id"], tmp_path)
    assert meta2["match_id"] == meta["match_id"] and contexts
    assert all("teams" in c and "moment" in c for c in contexts.values())
    some_id = next(iter(contexts))
    cache = {f"insight:{some_id}:analyst:en:-": {"analyst": {"headline": "fake head", "why_it_matters": "w", "tactical_read": "t", "key_stat": "k"},
                                                "viewers": {"analyst:en:-": {"narration": {"text": "fake line about Okafor"}}}},
             "coach:risk_alert:THU-1:50": {"proposal": None}}
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / f"{meta['match_id']}.json").write_text(json.dumps(cache), encoding="utf-8")
    rows = cached_insights(tmp_path / "cache", meta["match_id"])
    assert rows == [("analyst:en:-", some_id, cache[f"insight:{some_id}:analyst:en:-"])]
    assert cached_insights(tmp_path / "cache", "NOPE") == []

    items = items_to_score(contexts, rows)
    assert [i["agent"] for i in items] == ["analyst", "narrator"]
    assert items[0]["response"].startswith("fake head.") and items[1]["response"] == "fake line about Okafor"
    ctx_json = json.loads(items[0]["context"])
    assert "teams" in ctx_json and "analyst_track_record" not in ctx_json  # facts only, no bookkeeping
    assert context_text(contexts[some_id]) == items[0]["context"]

    ev = FakeEvaluator()
    scored = score_items(ev, items)
    assert len(ev.calls) == 2 and ev.calls[0][0].startswith("Explain") and ev.calls[1][0].startswith("Narrate")
    assert [s["groundedness"] for s in scored] == [5.0, 5.0]
    report = summarize(scored, meta["match_id"], "test")
    assert report["agents"]["analyst"]["mean"] == 5.0 and report["agents"]["narrator"]["distribution"]["5"] == 1
    json.dumps(report)


def test_evaluator_errors_do_not_stop_the_run():
    class Broken:
        def __call__(self, **_):
            raise RuntimeError("quota")

    scored = score_items(Broken(), [{"agent": "narrator", "profile": "p", "event_id": 1, "clock": "01:00", "response": "x", "context": "{}"}])
    assert scored[0]["groundedness"] is None and "quota" in scored[0]["reason"]
    report = summarize(scored, "M", "t")
    assert report["agents"]["narrator"]["n"] == 0 and report["agents"]["narrator"]["mean"] is None
