"""Shared fixtures: one deterministic synthetic match generated in-memory."""

from __future__ import annotations

import pytest

from matchmind.generate_match import generate


@pytest.fixture(scope="session")
def match():
    """(events, meta) for THU vs NBF, seed 42 — the canonical demo match."""
    return generate(home="THU", away="NBF", seed=42)


@pytest.fixture(scope="session")
def events(match):
    return match[0]


@pytest.fixture(scope="session")
def meta(match):
    return match[1]
