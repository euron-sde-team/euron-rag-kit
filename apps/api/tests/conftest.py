"""Fixtures shared by every suite."""

from __future__ import annotations

from pathlib import Path

import pytest

SAMPLES = Path(__file__).resolve().parents[3] / "samples"


@pytest.fixture(scope="session")
def samples_dir() -> Path:
    assert SAMPLES.is_dir(), f"sample corpus missing: {SAMPLES}"
    return SAMPLES
