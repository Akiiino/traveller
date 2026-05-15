"""Shared pytest fixtures: an isolated state directory + Flask app per test."""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest
from werkzeug.serving import make_server


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def app(state_dir: Path, monkeypatch):
    monkeypatch.setenv("STATE_DIRECTORY", str(state_dir))
    # `create_app` hard-fails without TRAVELLER_VENDOR_DIR. Inside `nix
    # flake check` the env var is set by the derivation; outside Nix we
    # fall back to an empty tmp dir so non-e2e tests don't require the
    # full vendor tree (those tests don't load static assets).
    if not os.environ.get("TRAVELLER_VENDOR_DIR"):
        monkeypatch.setenv("TRAVELLER_VENDOR_DIR", str(state_dir))
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


@pytest.fixture
def live_server(app):
    """Run the Flask app on a real socket for browser-driven e2e tests.

    Yields the base URL. The Flask test client (used by the rest of the
    suite) bypasses the network entirely; Playwright needs an actual
    listening port to drive Chromium against.
    """
    # threaded=True so the browser can fetch HTML + multiple static
    # assets in parallel without serializing on a single worker.
    server = make_server("127.0.0.1", 0, app, threaded=True)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)
