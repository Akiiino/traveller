# traveller — project notes for Claude

A small Flask app for managing points-of-interest on a trip. Runs on Nika's
mesh VPN for 2-3 trusted users. Not internet-facing; "production"
requirements explicitly do not apply, but data loss does — the app stores
people's actual trip planning.

See `TODO.md` for the prioritized backlog.

## Stack

- Flask + HTMX UI; Bootstrap (no UIKit anymore); Leaflet map
- SQLite (WAL, FK on, busy_timeout=5000) — single file at `$STATE_DIRECTORY/traveller.db`
- Gunicorn (default 2 workers; safe under WAL)
- Packaged as a Nix flake; deployed as a NixOS systemd service
- Python ≥ 3.12 (uses PEP 604 `X | None`, `datetime.UTC`, etc.)

## Layout

```
traveller/
  app.py            # create_app(); reads STATE_DIRECTORY env
  __main__.py       # gunicorn entrypoint
  models.py         # POI, Guide, Category dataclasses (pure data, no parsing)
  storage.py        # Storage class + ConflictError; all SQL lives here
  migrate.py        # one-shot legacy guide.zip importer (renames to .imported)
  gpx.py            # GPX serialization
  utils.py          # tiny XML helper used by gpx.py
  blueprints/
    views.py        # HTML routes (HTMX); conflict detection; URL allowlist
    apis.py         # /api/... JSON + GPX export
  templates/        # Jinja (.j2.html) — djlint-managed
  static/           # css, js, vendored or CDN frontend deps
tests/              # pytest; runs in ~3s via Flask test client
flake.nix           # package + NixOS module + checks (pytest/treefmt/djlint)
pyproject.toml      # source of truth for deps + tool config
```

## Routing

All POI work is guide-scoped: `/guide/<guide_id>/...`. Index `/` lists guides.
Card vs row layout is dispatched by inspecting the `HX-Target` header
(`row-poi-…` vs `card-poi-…`) — never User-Agent.

## Conflict detection (important — easy to break)

Every point edit form carries a hidden `modified_at` field. On PUT,
`Storage.update_point` raises `ConflictError(current=on_disk_poi)` if the
on-disk `modified_at` doesn't match. The view catches this and returns 409
with the edit form re-rendered using the **user's submitted values** (built
into an `attempted` POI from `request.form`), plus a conflict banner. The
on-disk row is *not* overwritten until the user resubmits.

Test coverage for this is in `tests/test_views.py::test_put_point_conflict_returns_409_with_user_input`.
If you change the conflict path, run that test.

## Security posture

- URL scheme allowlist for the `link` field: `http`, `https`, `mailto` only.
  `javascript:` etc. coerced to NULL. See `_sanitize_link` in views.py.
- `href` attributes in templates are quoted.
- `StrictUndefined` on the Jinja env — typo'd template vars are loud.
- No CSRF, no auth — intentional for this deployment. Listed in TODO.

## Storage gotchas

- `(0, 0)` is now a *valid* coordinate, not a sentinel. Missing coords are NULL.
- Legacy `link="None"` (string) from the old CSV format is normalized to NULL by `migrate.py`.
- `update_point` raises `KeyError(uuid)` for missing rows, `ConflictError` for stale `modified_at`.
- Per-request `Storage.connect()` opens a fresh sqlite connection. Fine for 2-3 users.

## Tooling conventions

- **Run tests**: `nix develop --command pytest` (or `pytest` inside the devshell)
- **Format**: `nix develop --command treefmt`
- **Lint templates**: `nix develop --command djlint --check --lint traveller/templates`
- **All checks at once**: `nix flake check` — runs pytest, treefmt --ci, djlint
- **Run the app locally**: `nix run .` (gunicorn; `STATE_DIRECTORY=$PWD/data` to control state)

## Treefmt + djlint coexistence

Prettier doesn't understand `{{ … }}` inside HTML attributes and would mangle
Jinja templates. `flake.nix` sets
`settings.formatter.prettier.excludes = ["*.j2.html"]` so djlint owns those
files. There's also a `.prettierignore` for non-flake invocations. djlint
config lives in `pyproject.toml` under `[tool.djlint]` — `profile = "jinja"`,
ignoring `H030,H031,J018,T028`.

## Nix flake gotcha

The flake source is filtered to git-tracked files. Newly created files
(tests, configs) are invisible to `nix flake check` until they're in the
git index. Use `git add -N <path>` (intent-to-add) to make them visible
without staging content for an unintended commit.

## Coding conventions observed in the codebase

- Dataclasses with `field(default_factory=...)` for mutable defaults
- All SQL stays in `storage.py`; views/apis call `storage.*` methods
- Views use small `_helpers` (`_render_edit`, `_sanitize_link`, `_is_card_request`)
- Templates use CSS classes, not inline `style=`
- Literal Unicode (✏️ ✔️ — ←) instead of HTML entity references
- `{% include "name.j2.html" %}` — double quotes (T002)

## Workflow

This repo lives at `~/git/traveller/` per the glabrata convention. Use the
standard `git mkpatch` / `git syncup` flow described in the global CLAUDE.md.
Don't auto-commit unless asked.
