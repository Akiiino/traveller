# traveller — backlog

Prioritized leftovers from the SQLite/multi-guide rewrite and the test/lint
session. Items higher in each tier are higher impact-per-effort. None of
these is urgent — the app is working and tested.

## Bugfixes
- On desktop, if any of the description fields contain a long string that can't
  be broken into multiple lines (e.g. a URL), the table gets wide and the map gets
  unusably narrow.

## High value, modest effort

- **Tighter validation feedback on the edit form.** Bad coordinates / bad
  timestamps are currently silently dropped (the field reverts to its
  prior value). Echo the form back with a per-field error class, similar
  to the conflict path. Same machinery: build an `attempted` POI from
  `request.form`, render the edit form with an error flag.

- **Feed category colors from the server to JS.** Currently hardcoded in
  two places: server-side `DEFAULT_CATEGORIES` (in `views.py` or
  `storage.py`) and `categoryColors` in `static/js/main.js`. The
  `/api/guide/<id>/categories` endpoint already exists; just consume it
  from `main.js` and drop the hardcoded map. Stops the two from drifting.

- **`datetime.utcnow()` → `datetime.now(datetime.UTC)`.** Python 3.12+
  deprecation; pytest output shows ~128 warnings. Affects
  `traveller/storage.py`, `traveller/gpx.py`, `traveller/models.py`. Pure
  mechanical replacement.

- **Vendor frontend deps** (Bootstrap, Leaflet, htmx, marker icons).
  Enables offline use when travelling on flaky SIM.
  Map *tiles* are the harder part — leave for a separate effort
  (mbtiles + leaflet-tilelayer-mbtiles is the proper answer).

- **Surface unexpected htmx errors.** With 409 now opting in to a normal
  swap, other 4xx/5xx still fail silently — same UX failure mode as the
  conflict bug. A small toast on `htmx:responseError` would catch future
  bugs faster instead of letting them die in the console.

## Medium

- **Better conflict UX.** The banner tells the user to "save again to
  overwrite" but gives no view of what the *other* version contained, so
  they're discarding someone else's save blind. A small inline diff or
  preview of the on-disk version next to their typed values would let
  them make an informed decision (or copy bits across).

- **Per-guide category management UI.** Schema + storage already support
  it; today every new guide gets the same default 7 categories with no
  way to add/edit/remove from the UI.

- **CSRF tokens on POST endpoints.** Proper fix is `Flask-WTF`'s
  `CSRFProtect`.

## Low / cosmetic

- **Template consolidation.** Collapse `card.j2.html` and `row.j2.html`
  into one partial that picks layout via CSS. Would require dropping the
  `<table>` layout for the desktop view, so non-trivial.

- **`utils.make_element` is barely worth its own module.** Could be
  inlined into `gpx.py` and the file deleted.

- **Auto-fit map bounds + colored markers** still hardcoded in `main.js`
  to a Korea-centric default. Should use the geojson bounds.

- **`__main__.py` mutates `sys.argv`** to inject gunicorn args. Harmless
  but ugly; could pass args directly to gunicorn's app object.

- **Backups / export-all.** Per-guide GPX export exists. A one-shot
  "export everything" (sqlite dump, or zip-of-GPX, or a JSON
  round-trippable through `migrate.py`) would be a nice safety net.

- **Migrations story.** Schema changes today rely on the importer +
  manual care. If you start iterating on the SQLite schema, add either
  Alembic or a tiny `schema_version` table + `if version < N: ALTER …`
  blocks at startup.

- **Map app selection.**  nmap:// URL schema is hardcoded for Naver Maps.
  The map URL type should be selectable per-device (and persisted in cookies/local
  storage) between at least:
  - the web OpenStreetMaps version (https://www.openstreetmap.org/);
  - Organic Maps (om:// or geo:);
  - Google Maps;

- **Zip guide import.** When creating a new guide, it should be possible to
  initialize it with a legacy ZIP file.

- **Remove hover-to-focus.** Add a "Show on map" button like in the mobile UI instead.

## Larger scope / long-shot

- **Real JS testing.** Today's only JS regression test greps `main.js`
  for substrings via the Flask test client — brittle and can't catch
  behavioral bugs (the conflict-swap bug would have passed). A small
  Playwright or jsdom harness would let us exercise htmx flows
  end-to-end.

- **Consolidate mobile and desktop UI.** As it is, the UI is quite different —
  some differences make sense for UX, but button names, UI style, etc. should
  be consistent. Part of this: mobile tab-switching uses inline `style.display`
  in JS, which means the desktop layout has to `!important`-override it per
  pane to recover from a resize. Class-based visibility (e.g. a `.hidden-mobile`
  class toggled via `classList`) would let CSS own the breakpoint logic and
  drop the overrides.

- **Live GPS.** Show the current location on the map; helpful for using
  the app on the go without going through the GPX export.

- **Full offline functionality.** Proper offline-usable PWA implementation,
  for flaky/nonexistent internet connection abroad.

## Out of scope (per user)

- "Production" hardening beyond the obvious (no rate limiting, no
  observability stack, etc.).
