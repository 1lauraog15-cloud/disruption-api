"""Run the real Alembic migrations on a throwaway SQLite file and compare with the models."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from disruption_api.models import Base

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def alembic_cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Config, str]:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    return cfg, url


def test_upgrade_matches_models(alembic_cfg: tuple[Config, str]) -> None:
    cfg, url = alembic_cfg
    command.upgrade(cfg, "head")
    insp = inspect(create_engine(url))
    assert set(insp.get_table_names()) - {"alembic_version"} == set(Base.metadata.tables)
    for table in Base.metadata.tables.values():
        assert {c["name"] for c in insp.get_columns(table.name)} == {c.name for c in table.columns}


def test_downgrade_to_base(alembic_cfg: tuple[Config, str]) -> None:
    cfg, url = alembic_cfg
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    assert set(inspect(create_engine(url)).get_table_names()) == {"alembic_version"}
