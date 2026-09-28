from __future__ import annotations

import os
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from docx import Document
from fastapi.testclient import TestClient

from konsilier.config import Settings
from konsilier.container import build_container
from konsilier.core.adapters.channels import RecordingChannel
from konsilier.core.documents import NullPdfConverter
from konsilier.core.llm.mock import HeuristicMockProvider
from konsilier.core.models import Base
from konsilier.main import create_app

REPO = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def packs_dir(tmp_path: Path) -> Path:
    """Real packs + the test-only XX pack, in a temp dir."""
    root = tmp_path / "packs"
    shutil.copytree(REPO / "packs", root)
    shutil.copytree(FIXTURES / "packs" / "xx", root / "xx")
    doc = Document()
    for line in ("To: {{ addressee.name }}", "{{ title }}", "{{ narrative }}", "I demand: {{ demands }}",
                 "Basis: {% for r in norm_refs %}{{ r }}{% endfor %}", "Date: {{ date }}"):
        doc.add_paragraph(line)
    (root / "xx" / "templates").mkdir(exist_ok=True)
    doc.save(root / "xx" / "templates" / "letter.docx")
    return root


@pytest.fixture
def ctx(tmp_path: Path, packs_dir: Path):
    settings = Settings(
        # set TEST_DATABASE_URL=postgresql+psycopg://... to run the suite against PostgreSQL
        database_url=os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path}/test.db", packs_dir=packs_dir,
        storage_backend="local", storage_local_dir=tmp_path / "files",
        llm_provider="mock", soffice_bin="", admin_token="adm", bot_api_secret="bot",
        approval_required_first_n=50, scheduler_interval_seconds=0, qualify_min_confidence=0.6,
        smtp_host=None, payment_mode="stub",
    )
    llm = HeuristicMockProvider()
    channels = {"web": RecordingChannel("web"), "telegram": RecordingChannel("telegram")}
    container = build_container(settings, llm=llm, pdf=NullPdfConverter(), channels=channels)
    Base.metadata.drop_all(container.engine_db)
    Base.metadata.create_all(container.engine_db)
    app = create_app(settings, container, start_scheduler=False)
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, container=container, llm=llm, channels=channels, settings=settings)
    container.engine_db.dispose()
