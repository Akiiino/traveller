# traveller — backlog

Prioritized leftovers from the SQLite/multi-guide rewrite and the test/lint
session. Items higher in each tier are higher impact-per-effort. None of
these is urgent — the app is working and tested.

## High value, modest effort

1. **Tighter validation feedback on the edit form.** Bad coordinates / bad
   timestamps are currently silently dropped (the field reverts to its
   prior value). Echo the form back with a per-field error class, similar
   to the conflict path. Same machinery: build an `attempted` POI from
   `request.form`, render the edit form with an error flag.

2. **Feed category colors from the server to JS.** Currently hardcoded in
   two places: server-side `DEFAULT_CATEGORIES` (in `views.py` or
   `storage.py`) and `categoryColors` in `static/js/main.js`. The
   `/api/guide/<id>/categories` endpoint already exists; just consume it
   from `main.js` and drop the hardcoded map. Stops the two from drifting.

3. **`datetime.utcnow()` → `datetime.now(datetime.UTC)`.** Python 3.12+
   deprecation; pytest output shows ~128 warnings. Affects
   `traveller/storage.py`, `traveller/gpx.py`, `traveller/models.py`. Pure
   mechanical replacement. Keep them naive at the boundary or move to
   tz-aware in one shot (see #6).

4. **Vendor frontend deps** (Bootstrap, Leaflet, htmx, marker icons).
   Enables offline use when travelling on flaky SIM. User has marked this
   as "deferred / out of scope for now"; reconfirm before doing.
   Map *tiles* are the harder part — leave for a separate effort
   (mbtiles + leaflet-tilelayer-mbtiles is the proper answer).

## Medium

5. **Per-guide category management UI.** Schema + storage already support
   it; today every new guide gets the same default 7 categories with no
   way to add/edit/remove from the UI.

6. **Timezone-aware datetimes.** Needs a UX call first: per-guide TZ?
   browser's TZ? naive-as-local? Without a decision this stays as naive.
   Storage migration is non-trivial — coordinate with #3.

7. **CSRF tokens on POST endpoints.** Proper fix is `Flask-WTF`'s
   `CSRFProtect`. Fine to defer on a trusted-VPN deployment but cheap to
   add.

8. **Per-process connection caching on `flask.g`.** Each request currently
   opens a fresh sqlite connection. Trivially fast for 2-3 users; only
   touch this if profiling shows it matters.

## Low / cosmetic

9. **Template consolidation.** Collapse `card.j2.html` and `row.j2.html`
   into one partial that picks layout via CSS. Would require dropping the
   `<table>` layout for the desktop view, so non-trivial.

10. **`utils.make_element` is barely worth its own module.** Could be
    inlined into `gpx.py` and the file deleted.

11. **Auto-fit map bounds + colored markers** still hardcoded in `main.js`
    to a Korea-centric default. Should use the geojson bounds.

12. **`__main__.py` mutates `sys.argv`** to inject gunicorn args. Harmless
    but ugly; could pass args directly to gunicorn's app object.

13. **Authentication.** Only matters if the VPN ACL ever loosens; the
    proper answer is oauth2-proxy or tailscale-nginx-auth in front.
    Don't bake it into the app.

14. **Backups / export-all.** Per-guide GPX export exists. A one-shot
    "export everything" (sqlite dump, or zip-of-GPX, or a JSON
    round-trippable through `migrate.py`) would be a nice safety net.

15. **Migrations story.** Schema changes today rely on the importer +
    manual care. If you start iterating on the SQLite schema, add either
    Alembic or a tiny `schema_version` table + `if version < N: ALTER …`
    blocks at startup.

16. **Importer coverage.** Only the legacy `guide.zip` shape is exercised.
    GPX/KML import would be new ground.

17. **Delete `korea.zip` from repo root** when no longer needed as a
    sample/migration fixture.

18. **`templates/types.j2.html` is unused** — left in place to avoid
    unrelated cleanup, but could be removed.

## Out of scope (per user)

- Internetless functionality as a *primary feature* — though vendoring
  CDN deps (#4) is still a good hedge.
- "Production" hardening beyond the obvious (no rate limiting, no
  observability stack, etc.).
