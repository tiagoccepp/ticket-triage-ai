"""Free-model rotation: fallbacks on removed/rate-limited models, abstain if all fail."""
from __future__ import annotations

import io
import json
import os
import sys
import urllib.request
from urllib.error import HTTPError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.classifier import FREE_POOL, OpenAICompatibleBackend, rotation_list  # noqa: E402
from src.config import Settings  # noqa: E402


def _settings(**kw) -> Settings:
    base = dict(llm_provider="openai", llm_api_key="dummy",
                llm_base_url="http://x", llm_model="gone")
    base.update(kw)
    return Settings(**base)


class _Resp:
    def __init__(self, payload: dict) -> None:
        self._raw = json.dumps(payload).encode()

    def __enter__(self):  # noqa: ANN204
        return self

    def __exit__(self, *a):  # noqa: ANN001
        return False

    def read(self) -> bytes:
        return self._raw


def _canned(label: str = "billing") -> dict:
    inner = json.dumps({"label": label, "confidence": 0.99,
                        "runner_up": "general_inquiry", "reason": "t"})
    return {"choices": [{"message": {"content": inner}}]}


def test_rotation_list() -> None:
    assert rotation_list("beam-free", "")[0] == "beam-free"
    assert rotation_list("x", "a,b,a") == ["x", "a", "b"]
    assert "beam-free" in FREE_POOL


def test_classify_falls_back_on_404(monkeypatch) -> None:
    calls: list = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001, ANN202
        model = json.loads(req.data.decode())["model"]
        calls.append(model)
        if model == "gone":
            raise HTTPError(req.full_url, 404, "nope", {}, None)
        return _Resp(_canned())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    b = OpenAICompatibleBackend(_settings(llm_fallback_models="beam-free"))
    r = b.classify("charged twice please refund")
    assert r.label == "billing"
    assert r.abstained is False
    assert calls == ["gone", "beam-free"]
    assert r.reasoning.startswith("[fallback:beam-free]")


def test_classify_retries_400_model_gone_not_param_error(monkeypatch) -> None:
    calls: list = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001, ANN202
        model = json.loads(req.data.decode())["model"]
        calls.append(model)
        if model == "gone":
            raise HTTPError(req.full_url, 400, "Model is unavailable", {}, None)
        return _Resp(_canned())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    b = OpenAICompatibleBackend(_settings(llm_fallback_models="beam-free"))
    r = b.classify("charged twice please refund")
    assert r.label == "billing"
    assert calls == ["gone", "beam-free"]

    calls2: list = []

    def fake_urlopen2(req, timeout=None):  # noqa: ANN001, ANN202
        calls2.append(1)
        raise HTTPError(req.full_url, 400, "invalid temperature", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen2)
    b2 = OpenAICompatibleBackend(_settings())
    r2 = b2.classify("charged twice please refund")
    assert r2.abstained is True
    assert len(calls2) == 1


def test_classify_no_retry_on_401(monkeypatch) -> None:
    calls: list = []

    def fake_urlopen(req, timeout=None):  # noqa: ANN001, ANN202
        calls.append(1)
        raise HTTPError(req.full_url, 401, "bad key", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    b = OpenAICompatibleBackend(_settings())
    r = b.classify("charged twice please refund")
    assert r.abstained is True
    assert len(calls) == 1


def test_classify_abstains_when_all_fail(monkeypatch) -> None:
    def fake_urlopen(req, timeout=None):  # noqa: ANN001, ANN202
        raise HTTPError(req.full_url, 429, "slow down", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    b = OpenAICompatibleBackend(_settings(llm_fallback_models="m2"))
    r = b.classify("charged twice please refund")
    assert r.abstained is True
    assert "all models failed" in r.reasoning
