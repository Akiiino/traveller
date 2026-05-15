"""End-to-end browser tests for the guide page.

These exercise real htmx swap timing, real HTML5 form validation, real
datetime-local widget quirks, and the conflict/409 round-trip — bugs the
grep-style JS tests can't catch.

CRUD smoke tests are parametrized across three "views":
- desktop-chromium  (default desktop viewport, Chromium)
- desktop-firefox   (default desktop viewport, Firefox)
- mobile-chromium   (Pixel-5 viewport + touch + mobile UA, Chromium)
Mobile-Firefox is skipped — Playwright's mobile emulation needs
``is_mobile``, which Firefox doesn't support.

The narrower bug-replay tests (HTML5 validation specifics, 409 handling)
stay on desktop-chromium only via ``@pytest.mark.only_browser``.

Slower than the rest of the suite (a few seconds per case) — kept in
their own file so they can be skipped with ``-k "not e2e"`` when iterating.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pytest

from traveller.models import POI

# --- Browser launch ---------------------------------------------------------


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    """Make Chromium survive the network-less Nix sandbox.

    ``--disable-dev-shm-usage`` avoids crashes when /dev/shm is too small
    or unavailable; ``--no-sandbox`` skips Chromium's user-namespace
    sandbox (we're already inside Nix's). Both are no-ops for Firefox
    (Playwright filters them) so this is safe to leave session-scoped.
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


# --- View parametrize (layout × browser) ------------------------------------


@dataclass(frozen=True)
class View:
    """One concrete layout the smoke tests run against."""

    layout: str  # "desktop" or "mobile"

    @property
    def is_mobile(self) -> bool:
        return self.layout == "mobile"

    def item(self, uuid: str) -> str:
        """CSS selector for the read-only row/card of POI ``uuid``."""
        prefix = "card-poi-" if self.is_mobile else "row-poi-"
        return f"#{prefix}{uuid}"

    def editing(self, uuid: str) -> str:
        """CSS selector for the same row/card while it's in edit mode."""
        return f"{self.item(uuid)}.editing"

    @property
    def container(self) -> str:
        """The visible-on-this-viewport container that holds POI rows/cards."""
        return ".mobile-view" if self.is_mobile else ".desktop-view"

    def new_editing(self) -> str:
        """Selector for *any* item currently in edit mode under the container."""
        suffix = ".poi-card.editing" if self.is_mobile else "tr.editing"
        return f"{self.container} {suffix}"

    def uuid_from_id(self, dom_id: str) -> str:
        prefix = "card-poi-" if self.is_mobile else "row-poi-"
        assert dom_id.startswith(prefix), dom_id
        return dom_id[len(prefix) :]


@pytest.fixture(params=["desktop", "mobile"])
def layout(request):
    return request.param


@pytest.fixture
def browser_context_args(browser_context_args, layout, browser_name, playwright):
    """Switch to a mobile context for the mobile layout.

    Playwright's mobile emulation needs ``is_mobile`` + touch, which
    Firefox doesn't implement — skip those combos.
    """
    if layout == "mobile":
        if browser_name == "firefox":
            pytest.skip("mobile emulation needs is_mobile, unsupported by Firefox")
        return {**browser_context_args, **playwright.devices["Pixel 5"]}
    return browser_context_args


@pytest.fixture
def view(layout) -> View:
    return View(layout=layout)


@pytest.fixture
def desktop_only(layout):
    """Mark a test as desktop-only.

    Because ``browser_context_args`` depends on ``layout``, every test
    using ``page`` is implicitly parametrized over layouts. Bug-replay
    tests with hard-coded desktop selectors opt out via this fixture.
    """
    if layout != "desktop":
        pytest.skip("desktop-only test")


# --- Helpers ----------------------------------------------------------------


def _open_guide(page, base_url: str, guide_id: int, view: View) -> None:
    """Navigate to the guide page in the given viewport.

    On mobile, ``#table-container`` starts hidden and the user reveals it
    by clicking the List View tab. Drive the same tab click here so the
    list is visible before the test interacts with it.
    """
    page.goto(f"{base_url}/guide/{guide_id}")
    if view.is_mobile:
        page.locator('.view-tab[data-target="table-container"]').click()
        page.locator("#table-container").wait_for(state="visible")


def _open_edit(page, base_url: str, view: View, guide_id: int, uuid: str) -> None:
    """Navigate to the guide and put POI ``uuid`` into edit mode."""
    _open_guide(page, base_url, guide_id, view)
    page.locator(f"{view.item(uuid)} .btn-edit").click()
    page.locator(view.editing(uuid)).wait_for()


# --- Smoke tests (run across all three views) -------------------------------


def test_smoke_create_point(live_server, page, storage, view):
    g = storage.create_guide(name="X")
    _open_guide(page, live_server, g.id, view)

    # Click whichever Add Point button is actually visible at this
    # viewport — same as what a user does. The previous bug was that
    # on mobile, the single global button appended a row to the *hidden*
    # desktop table, leaving the visible card list empty.
    page.locator(".add-poi-btn:visible").click()

    # A new editing item must appear in the *visible* container.
    new_item = page.locator(view.new_editing()).last
    new_item.wait_for(timeout=5000)
    dom_id = new_item.get_attribute("id")
    new_uuid = view.uuid_from_id(dom_id)

    # Fill name and save.
    page.locator(f"{view.item(new_uuid)} input[name=name]").fill("smoke-created")
    page.locator(f"{view.item(new_uuid)} .btn-primary").click()

    # Item leaves edit mode and shows the new name; DB row exists.
    page.locator(f"{view.item(new_uuid)}:not(.editing)").wait_for()
    saved = storage.get_point(g.id, new_uuid)
    assert saved is not None and saved.name == "smoke-created"


def test_smoke_edit_point(live_server, page, storage, view):
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="orig"))

    _open_edit(page, live_server, view, g.id, poi.uuid)
    page.locator(f"{view.item(poi.uuid)} input[name=name]").fill("renamed")
    page.locator(f"{view.item(poi.uuid)} .btn-primary").click()

    page.locator(f"{view.item(poi.uuid)}:not(.editing)").wait_for()
    assert storage.get_point(g.id, poi.uuid).name == "renamed"


def test_smoke_delete_point(live_server, page, storage, view):
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="doomed"))

    _open_guide(page, live_server, g.id, view)
    # hx-confirm shows a browser dialog; auto-accept it.
    page.on("dialog", lambda d: d.accept())
    page.locator(f"{view.item(poi.uuid)} .btn-delete").click()

    # Row/card gone from DOM, point gone from DB.
    page.locator(view.item(poi.uuid)).wait_for(state="detached")
    assert storage.get_point(g.id, poi.uuid) is None


def test_smoke_toggle_visited(live_server, page, storage, view):
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="visit me", visited=False))

    _open_guide(page, live_server, g.id, view)
    # The visited checkbox is inside the visible row/card.
    page.locator(f"{view.item(poi.uuid)} input[name=visited]").click()

    # The toggle endpoint returns 200 with no body (hx-swap="none"); poll
    # the DB until it lands rather than waiting for a DOM change.
    for _ in range(50):
        if storage.get_point(g.id, poi.uuid).visited:
            return
        page.wait_for_timeout(50)
    raise AssertionError("visited toggle never reached the DB")


# --- Bug-replay tests (desktop-chromium only) -------------------------------
#
# These poke at specific edge cases (HTML5 validation specifics, 409
# round-trip) that aren't viewport-specific. Running them once against
# the canonical engine is enough; cross-browser coverage doesn't add
# signal here.


@pytest.mark.only_browser("chromium")
def test_e2e_bad_coordinates_blocks_save_client_side(
    live_server, page, storage, desktop_only
):
    # The coordinates input has pattern="-?\d+(\.\d+)?,\s*-?\d+(\.\d+)?".
    # With our htmx:beforeRequest validator, a pattern mismatch must be
    # caught client-side: the field gets `field-error`, the request never
    # leaves the browser, and the on-disk row is unchanged.
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="orig", latitude=1.0, longitude=2.0))
    initial_modified = poi.modified_at
    view = View(layout="desktop")

    _open_edit(page, live_server, view, g.id, poi.uuid)
    page.locator(f"{view.item(poi.uuid)} input[name=coordinates]").fill("garbage")
    page.locator(f"{view.item(poi.uuid)} .btn-primary").click()

    coords = page.locator(f"{view.item(poi.uuid)} input[name=coordinates]")
    page.wait_for_function(
        "el => el.classList.contains('field-error')",
        arg=coords.element_handle(),
    )
    assert page.locator(view.editing(poi.uuid)).count() == 1

    saved = storage.get_point(g.id, poi.uuid)
    assert saved.latitude == 1.0 and saved.longitude == 2.0
    assert saved.modified_at == initial_modified


@pytest.mark.only_browser("chromium")
def test_e2e_partial_datetime_blocks_save(live_server, page, storage, desktop_only):
    # The original bug: typing only the date part (no time) into a
    # datetime-local widget makes the browser submit "" — the server
    # cannot distinguish that from "user cleared the field" and silently
    # wipes the timestamp. The client-side validator catches this via
    # validity.badInput before the request goes out.
    original_ts = datetime(2024, 1, 2, 12, 0)
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="orig", timestamp=original_ts))
    view = View(layout="desktop")

    _open_edit(page, live_server, view, g.id, poi.uuid)
    ts_input = page.locator(f"{view.item(poi.uuid)} input[name=timestamp]")

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
    page.locator(f"{view.item(poi.uuid)} .btn-primary").click()

    page.wait_for_function(
        "el => el.classList.contains('field-error')",
        arg=ts_input.element_handle(),
    )
    assert page.locator(view.editing(poi.uuid)).count() == 1
    assert storage.get_point(g.id, poi.uuid).timestamp == original_ts


@pytest.mark.only_browser("chromium")
def test_e2e_stale_modified_at_shows_conflict_banner(
    live_server, page, storage, desktop_only
):
    # End-to-end version of the existing test_put_point_conflict_*: open
    # the form, have someone else save in the background, type something,
    # click save — verify the banner appears AND the typed value is still
    # in the form (not silently replaced with on-disk values).
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="orig"))
    view = View(layout="desktop")

    _open_edit(page, live_server, view, g.id, poi.uuid)
    page.locator(f"{view.item(poi.uuid)} input[name=name]").fill("user-typed")

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

    page.locator(f"{view.item(poi.uuid)} .btn-primary").click()

    page.locator(f"{view.editing(poi.uuid)}.conflict").wait_for()
    body = page.content()
    assert "Saved by someone else" in body
    name_value = page.locator(f"{view.item(poi.uuid)} input[name=name]").input_value()
    assert name_value == "user-typed"
    assert storage.get_point(g.id, poi.uuid).name == "someone-else"


@pytest.mark.only_browser("chromium")
def test_e2e_popup_xss_blocked(live_server, page, storage, desktop_only):
    # Regression: a POI name containing HTML used to be injected into
    # the map popup via innerHTML, so an `<img src=x onerror=…>` payload
    # fired on page load (innerHTML parses the img before the user even
    # opens the popup). The fix builds the popup as DOM nodes and uses
    # textContent for the name/description/category.
    g = storage.create_guide(name="X")
    storage.create_point(
        g.id,
        POI(
            name='<img src=x onerror="window.__pwn=true">',
            latitude=1.0,
            longitude=2.0,
        ),
    )
    page.add_init_script("window.__pwn = false;")
    page.goto(f"{live_server}/guide/{g.id}")
    # Wait for at least one marker to land — confirms loadPOIs() has run
    # and built the popup, which is when the payload would have fired.
    page.locator(".leaflet-marker-icon").first.wait_for()
    assert page.evaluate("window.__pwn") is False
    # And the name still round-trips literally into the popup heading
    # when the user does open it.
    page.locator(".leaflet-marker-icon").first.click()
    heading = page.locator(".leaflet-popup-content h5")
    heading.wait_for()
    assert heading.inner_text() == '<img src=x onerror="window.__pwn=true">'


@pytest.mark.only_browser("chromium")
def test_e2e_delete_confirm_no_xss(live_server, page, storage, desktop_only):
    # Regression: the guide-list delete confirm used to interpolate the
    # name into a JS string inside `onsubmit='return confirm("…");'`.
    # Jinja's HTML escape isn't sufficient in a JS context — &#34; decodes
    # back to a real `"` before the JS sees it. The fix wraps the name
    # via the `tojson` filter so it lands as a proper JS string literal.
    payload = '" + (window.__pwn=true) + "'
    storage.create_guide(name=payload)
    page.add_init_script("window.__pwn = false;")
    # Dismiss the confirm dialog without submitting the form, and record
    # the message so we can assert the payload appears as literal text.
    dialog_messages: list[str] = []

    def _on_dialog(d):
        dialog_messages.append(d.message)
        d.dismiss()

    page.on("dialog", _on_dialog)
    page.goto(f"{live_server}/")
    page.locator("form button.btn-outline-danger").first.click()
    # The confirm dialog is synchronous; once click() returns, the
    # onsubmit handler has run to completion. If the payload had been
    # evaluated as JS, __pwn would now be true.
    assert page.evaluate("window.__pwn") is False
    assert dialog_messages and payload in dialog_messages[0]
