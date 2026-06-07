# traveller — backlog

Prioritized leftovers from the SQLite/multi-guide rewrite and the test/lint
session. Items higher in each tier are higher impact-per-effort. None of
these is urgent — the app is working and tested.

## Bugfixes

- None yet.

## High value, modest effort

- **Export POI `timestamp` to GPX waypoint `<time>`.** Every waypoint
  already has a date in the UI but `_poi_to_waypoint` never sets
  `waypoint.time`. GPX consumers currently lose the per-point date.
  Once per-guide timezone lands (see Medium), this should be emitted
  with the guide's offset.

- **Surface unexpected htmx errors.** With 409 now opting in to a normal
  swap, other 4xx/5xx still fail silently — same UX failure mode as the
  conflict bug. A small toast on `htmx:responseError` would catch future
  bugs faster instead of letting them die in the console.

## Medium

- **Per-guide timezone + TZ-aware datetimes throughout.** Naive datetimes
  are intentional today (so a 10:00 plan stays 10:00 wherever you travel),
  but the timezone is implicit. Add a `timezone` field on `Guide` (IANA name,
  e.g. `Asia/Seoul`), interpret POI `timestamp` and `modified_at` against it,
  and emit GPX `<time>` with the resolved offset. Subsumes the previous
  `datetime.utcnow()` → `datetime.now(UTC)` cleanup and silences the
  Python 3.12 deprecation warnings as a side effect. Schema change — see
  the "Migrations story" item.

- **Better conflict UX.** The banner tells the user to "save again to
  overwrite" but gives no view of what the *other* version contained, so
  they're discarding someone else's save blind. A small inline diff or
  preview of the on-disk version next to their typed values would let
  them make an informed decision (or copy bits across).

- **CSRF tokens on POST endpoints.** Proper fix is `Flask-WTF`'s
  `CSRFProtect`.

## Low / cosmetic

- **`utils.make_element` is barely worth its own module.** Could be
  inlined into `gpx.py` and the file deleted.

- **Auto-fit map bounds + colored markers** still hardcoded in `main.js`
  to a Korea-centric default. Should use the geojson bounds.

- **`__main__.py` mutates `sys.argv`** to inject gunicorn args. Harmless
  but ugly; could pass args directly to gunicorn's app object.

- **Backups / export-all.** Per-guide GPX export exists. A one-shot
  "export everything" (sqlite dump, or zip-of-GPX, or a JSON
  round-trippable through `migrate.py`) would be a nice safety net.

- **Zip guide import.** When creating a new guide, it should be possible to
  initialize it with a legacy ZIP file.

## Larger scope / long-shot

- **Live GPS.** Show the current location on the map; helpful for using
  the app on the go without going through the GPX export.

- **Full offline functionality.** Proper offline-usable PWA implementation,
  for flaky/nonexistent internet connection abroad.

## Out of scope (per user)

- "Production" hardening beyond the obvious (no rate limiting, no
  observability stack, etc.).
