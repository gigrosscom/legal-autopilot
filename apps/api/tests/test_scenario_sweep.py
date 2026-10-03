"""The scenario sweep's mechanics (scripts/scenario_sweep.py) without a model: a matrix branch is played through the
app and the report holds the scenario, every reply, the card flag and the draft's first lines. The real sweep runs
the same code on the QA key."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

from .test_chat_paid_document import _agent

SPEC = importlib.util.spec_from_file_location("scenario_sweep",
                                              Path(__file__).resolve().parents[1] / "scripts" / "scenario_sweep.py")
sweep = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sweep)


def test_every_matrix_is_well_formed():
    for path in sweep.MATRICES.glob("*.yaml"):
        m = yaml.safe_load(path.read_text("utf-8"))
        assert m["domain"] == path.stem and m["cases"]
        assert all(c["id"] and c["turns"] for c in m["cases"]), path


def test_a_branch_is_played_and_reported(ctx, monkeypatch):
    monkeypatch.setenv("SWEEP_MODE", "chat")  # the chat mode's code path, on a scripted model
    ctx.container.settings.background_jobs = "inline"
    sol = "Что делать:\n1. **Подайте иск.**\n[[MORE]]\nСоставлю иск — готовый PDF и Word.\n[[DOCUMENT]]"
    ctx.container.chat_agent, ctx.container.chat_fallback_agent = _agent("Есть ли дети?", sol, sol), None
    matrix = yaml.safe_load((sweep.MATRICES / "family.yaml").read_text("utf-8"))
    result = sweep.play(ctx.client, matrix["cases"][0])
    assert len(result["log"]) == len(matrix["cases"][0]["turns"]) and result["log"][0]["bot"]
    text = sweep.report(matrix, [result])
    assert "## F1." in text and "**Клиент 1:**" in text and "Документ (черновик" in text


def test_without_a_key_the_sweep_runs_the_interview(ctx, monkeypatch):
    """No model: the server's interview, the document from the template — read as the desk does."""
    monkeypatch.delenv("QA_GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("SWEEP_MODE", "interview")
    monkeypatch.setattr(sweep, "ADMIN_TOKEN", "adm")
    ctx.container.settings.background_jobs = "inline"
    ctx.container.engine.config.approval_required_first_n = 0
    from konsilier.core import ai

    monkeypatch.setattr(ai, "qualify", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no model")))
    matrix = yaml.safe_load((sweep.MATRICES / "family.yaml").read_text("utf-8"))
    result = sweep.play_interview(ctx.client, matrix["cases"][0])
    assert result["scenario"] and "family__divorce" in result["scenario"]
    assert "чек" not in result["log"][0]["bot"].lower()  # the divorce's files, not a purchase's
    assert "ИСКОВОЕ ЗАЯВЛЕНИЕ" in result["draft"] or "заявлени" in result["draft"].lower()
