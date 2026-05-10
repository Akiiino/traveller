"""Shared pytest fixtures: an isolated state directory + Flask app per test."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def app(state_dir: Path, monkeypatch):
    monkeypatch.setenv("STATE_DIRECTORY", str(state_dir))
    # Reload app module so module-level paths pick up the fresh STATE_DIRECTORY.
    import importlib

    import traveller.app

    importlib.reload(traveller.app)
    app = traveller.app.create_app()
    app.testing = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def storage(app):
    return app.config["storage"]
