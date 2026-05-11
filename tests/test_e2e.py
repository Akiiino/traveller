"""End-to-end browser tests for the edit-form flow.

These cover the bugs that grep-style "does main.js contain this string"
tests cannot catch: real htmx swap timing, real HTML5 form validation,
real datetime-local widget quirks, and the conflict/409 round-trip.

Slower than the rest of the suite (a few seconds per test) — kept in
their own file so they can be skipped with `-k "not e2e"` when iterating.
"""

from __future__ import annotations

import os
from datetime import datetime

import pytest

from traveller.models import POI


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    """Make Chromium survive the network-less Nix sandbox.

    `--disable-dev-shm-usage` avoids crashes when /dev/shm is too small
    or unavailable; `--no-sandbox` skips Chromium's user-namespace
    sandbox (we're already inside Nix's). No effect in the devshell
    where these args are harmless redundancies.
    """
    return {
        **browser_type_launch_args,
        "args": ["--no-sandbox", "--disable-dev-shm-usage"],
    }


@pytest.fixture(autouse=True)
def _log_console(page, capsys):
    """Echo console + page errors to stdout so they show up on test failure."""
    page.on("console", lambda msg: print(f"[console.{msg.type}] {msg.text}"))
    page.on("pageerror", lambda err: print(f"[pageerror] {err}"))
    page.on(
        "requestfailed",
        lambda req: print(f"[requestfailed] {req.url} {req.failure}"),
    )
    yield


@pytest.fixture(autouse=True)
def _stub_cdn(page):
    """Intercept the CDN assets the templates load.

    The Nix sandbox has no network, so htmx must come from a locally
    vendored copy (path injected via TRAVELLER_HTMX_JS, fetched as a FOD
    in flake.nix). Other CDN assets (Bootstrap, Leaflet) are stubbed with
    empty bodies — the edit-form tests don't depend on them. Missing
    Leaflet causes main.js to throw at L.map(...), but only AFTER both
    htmx event handlers are registered, so the flows we test still work.
    """
    htmx_path = os.environ.get("TRAVELLER_HTMX_JS")
    if htmx_path is None:
        # Outside Nix: let the real CDN respond.
        yield
        return
    with open(htmx_path, "rb") as f:
        htmx_body = f.read()

    def handler(route):
        url = route.request.url
        if "htmx" in url:
            route.fulfill(
                status=200,
                body=htmx_body,
                content_type="application/javascript",
            )
        elif "127.0.0.1" in url:
            route.continue_()
        else:
            ct = (
                "text/css"
                if url.rstrip("/").endswith(".css")
                else "application/javascript"
            )
            route.fulfill(status=200, body=b"", content_type=ct)

    page.route("**/*", handler)
    yield


def _open_edit(page, base_url: str, guide_id: int, uuid: str) -> None:
    """Navigate to the guide page and put the row for `uuid` into edit mode."""
    page.goto(f"{base_url}/guide/{guide_id}")
    page.locator(f"#row-poi-{uuid} .btn-edit").click()
    # Wait until htmx has swapped the row into the editing variant.
    page.locator(f"#row-poi-{uuid}.editing").wait_for()


def test_e2e_successful_edit_updates_row(live_server, page, storage):
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="orig"))

    _open_edit(page, live_server, g.id, poi.uuid)
    page.locator(f"#row-poi-{poi.uuid} input[name=name]").fill("renamed")
    page.locator(f"#row-poi-{poi.uuid} .btn-primary").click()

    # Row re-renders in read-only mode with the new name; storage updated.
    page.locator(f"#row-poi-{poi.uuid}:not(.editing)").wait_for()
    assert storage.get_point(g.id, poi.uuid).name == "renamed"


def test_e2e_bad_coordinates_blocks_save_client_side(live_server, page, storage):
    # The coordinates input has pattern="-?\d+(\.\d+)?,\s*-?\d+(\.\d+)?".
    # With our htmx:beforeRequest validator, a pattern mismatch must be
    # caught client-side: the field gets `field-error`, the request never
    # leaves the browser, and the on-disk row is unchanged.
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="orig", latitude=1.0, longitude=2.0))
    initial_modified = poi.modified_at

    _open_edit(page, live_server, g.id, poi.uuid)
    page.locator(f"#row-poi-{poi.uuid} input[name=coordinates]").fill("garbage")
    page.locator(f"#row-poi-{poi.uuid} .btn-primary").click()

    # Field-error class lands on the bad input. Still in edit mode (no swap).
    coords = page.locator(f"#row-poi-{poi.uuid} input[name=coordinates]")
    page.wait_for_function(
        "el => el.classList.contains('field-error')",
        arg=coords.element_handle(),
    )
    assert page.locator(f"#row-poi-{poi.uuid}.editing").count() == 1

    # On-disk row is untouched: same coords, same modified_at.
    saved = storage.get_point(g.id, poi.uuid)
    assert saved.latitude == 1.0 and saved.longitude == 2.0
    assert saved.modified_at == initial_modified


def test_e2e_partial_datetime_blocks_save(live_server, page, storage):
    # The original bug: typing only the date part (no time) into a
    # datetime-local widget makes the browser submit "" — the server
    # cannot distinguish that from "user cleared the field" and silently
    # wipes the timestamp. The client-side validator catches this via
    # validity.badInput before the request goes out.
    original_ts = datetime(2024, 1, 2, 12, 0)
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="orig", timestamp=original_ts))

    _open_edit(page, live_server, g.id, poi.uuid)
    ts_input = page.locator(f"#row-poi-{poi.uuid} input[name=timestamp]")

    # Force a partial-input state: a value that the input itself would
    # reject (so .value === "" and validity.badInput === true) but that
    # the validator must still catch. We dispatch the input event to
    # mimic an interactively-typed partial entry.
    ts_input.evaluate(
        """el => {
            el.focus();
            el.value = '';
            // Mark the input as having bad input via a property override —
            // headless Chromium's keyboard sim for datetime-local is
            // unreliable across versions, but the validator only checks
            // checkValidity(), which we can force false the same way the
            // widget does internally.
            Object.defineProperty(el, 'validity', {
                configurable: true,
                get: () => ({
                    valid: false, badInput: true, valueMissing: false,
                    typeMismatch: false, patternMismatch: false,
                    tooLong: false, tooShort: false, rangeUnderflow: false,
                    rangeOverflow: false, stepMismatch: false,
                    customError: false,
                }),
            });
            el.checkValidity = () => false;
        }"""
    )
    page.locator(f"#row-poi-{poi.uuid} .btn-primary").click()

    # Field-error lands; still in edit mode; timestamp untouched on disk.
    page.wait_for_function(
        "el => el.classList.contains('field-error')",
        arg=ts_input.element_handle(),
    )
    assert page.locator(f"#row-poi-{poi.uuid}.editing").count() == 1
    assert storage.get_point(g.id, poi.uuid).timestamp == original_ts


def test_e2e_stale_modified_at_shows_conflict_banner(live_server, page, storage):
    # End-to-end version of the existing test_put_point_conflict_*: open
    # the form, have someone else save in the background, type something,
    # click save — verify the banner appears AND the typed value is still
    # in the form (not silently replaced with on-disk values).
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="orig"))

    _open_edit(page, live_server, g.id, poi.uuid)
    page.locator(f"#row-poi-{poi.uuid} input[name=name]").fill("user-typed")

    # Out-of-band save bumps modified_at; the form's hidden field is now stale.
    storage.update_point(
        g.id,
        poi.uuid,
        expected_modified_at=poi.modified_at,
        name="someone-else",
        description="",
        latitude=None,
        longitude=None,
        link=None,
        category="",
        timestamp=None,
    )

    page.locator(f"#row-poi-{poi.uuid} .btn-primary").click()

    # Conflict banner appears (HTTP 409 was swapped in via main.js).
    page.locator(f"#row-poi-{poi.uuid}.editing.conflict").wait_for()
    body = page.content()
    assert "Saved by someone else" in body
    # User's typed name is still in the form, not "someone-else".
    name_value = page.locator(f"#row-poi-{poi.uuid} input[name=name]").input_value()
    assert name_value == "user-typed"
    # On-disk row reflects the other save, not the rejected one.
    assert storage.get_point(g.id, poi.uuid).name == "someone-else"
