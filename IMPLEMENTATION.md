# Django on Cloudflare Workers — Implementation Checklist

**Status:** complete; deployed and torn down on 2026-10-21. No Cloudflare resources remain.

**Goal:** Run a minimal Django site with a homepage and admin on Cloudflare Workers, backed by one Durable Object, with CLI/CI-only deployment.

**Architecture:** A Python Worker forwards requests to a singleton SQLite Durable Object serving Django through `django-cf`. Django and its dependencies are vendored into `python_modules/` and uploaded by Wrangler. Worker bindings are copied into `os.environ` before Django settings load. A token-protected endpoint performed migrations and first-admin creation; it is now disabled.

**Stack:** Python 3.12, Django 5.2.6, `django-cf` 0.2.17, uv, Wrangler 4.151.3, Cloudflare CLI 1.0.0-beta.20, Node 22+, GitHub Actions.

**Spec:** `README.md`

## Global constraints

- Python dependencies: `uv` only. Lock in `pyproject.toml` / `uv.lock`.
- Deploy: `npx wrangler deploy`. `cf deploy` does not upload Python modules.
- Account/zone operations: `cf`.
- Runtime modules: root `python_modules/` only. Never under `src/`.
- Secrets: `npx wrangler secret bulk`; never commit them.
- Tests: `DJANGO_TEST=1 PYTHONPATH=src uv run python -m unittest discover -s tests -v`.
- Ignore `CF.sh`, `.dev.vars`, `python_modules/`, `staticfiles/*`, `.cloudflare/`.

## Checklist

### 1. Django scaffold and homepage — done

- [x] Write `tests/test_views.py` (homepage returns 200 and contains the title).
- [x] Confirm the test fails before the scaffold exists.
- [x] Create `pyproject.toml` with Django 5.2.6, `django-cf` 0.2.17, `tzdata`; run `uv sync`.
- [x] Create `src/manage.py`, `src/app/{__init__,settings,urls,views,wsgi}.py`, `src/app/templates/home.html`.
- [x] Configure `ALLOWED_HOSTS` including `dj.heroic.ch` and `testserver`, `STATIC_URL="/static/"`, `STATIC_ROOT=staticfiles/static`.
- [x] Empty `DATABASES` when `WORKERS_CI=1` or `DJANGO_TEST=1`; the DO backend cannot import outside the Workers runtime.
- [x] Run tests and `manage.py check`; both pass.
- [x] Commit.

### 2. Token-protected bootstrap endpoints — done

- [x] Write `tests/test_bootstrap.py`: disabled returns 404, missing/wrong token 401, GET 405, valid migrate calls `call_command`, admin is idempotent.
- [x] Confirm tests fail before the routes exist.
- [x] Add `src/app/bootstrap.py` with `hmac.compare_digest`, `BOOTSTRAP_ENABLED`, and `BOOTSTRAP_TOKEN` checks.
- [x] Add `/__bootstrap/migrate/` and `/__bootstrap/admin/` to `src/app/urls.py`.
- [x] Run tests; 10 pass.
- [x] Commit.

### 3. Worker configuration, vendoring, and bindings — done

- [x] Create `.gitignore`, `package.json`, and `wrangler.jsonc`.
- [x] Pin `cf` 1.0.0-beta.20 and `wrangler` 4.151.3; run `npm install`.
- [x] Add `staticfiles/.gitkeep`; Wrangler validates the assets directory before running `collectstatic`.
- [x] Create `src/index.py` with `DjangoDO` and `Default`.
- [x] Copy `BOOTSTRAP_*` and `DJANGO_*` bindings from `self.env` into `os.environ` inside `DjangoDO.get_app()` **before** importing `app.wsgi`.
- [x] Create `scripts/vendor.sh`: copy `src/app` into root `python_modules/` and `uv pip install --target python_modules` from the exported lock.
- [x] Build with `collectstatic` (`WORKERS_CI=1`), keeping static output under `staticfiles/`.
- [x] Run `npx wrangler deploy --dry-run`; confirm the `DO_STORAGE` binding.
- [x] Run `npx wrangler dev`; homepage returns 200 on `localhost:8787`.
- [x] Commit.

### 4. Deploy script — done

- [x] Create `scripts/deploy.sh`: validate env, optional non-blocking zone check, `uv sync --locked`, `npm ci`, vendor, `wrangler deploy`, `wrangler secret bulk`, wait for the site, bootstrap.
- [x] Create `.dev.vars.example`; keep real `.dev.vars` ignored.
- [x] Verify `bash -n` and a full local deploy.
- [x] Commit.

### 5. GitHub Actions — done

- [x] Create `.github/workflows/deploy.yml`: checkout, Node 22, uv, `uv sync --locked`, `npm ci`, tests, vendor, `wrangler deploy`, `wrangler secret bulk`, bootstrap, secret-file cleanup.
- [x] Set repository secrets: `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `DJANGO_SECRET_KEY`, `BOOTSTRAP_TOKEN`, `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_EMAIL`, `DJANGO_SUPERUSER_PASSWORD`.
- [x] Validate the workflow YAML and push.
- [x] Confirm the workflow succeeds: https://github.com/puckdoug/cloudflare-django/actions/runs/39704539814
- [x] Commit.

### 6. First deploy and verification — done

- [x] Confirm `heroic.ch` is active in the account.
- [x] Deploy with `wrangler`; custom domain `dj.heroic.ch` attached automatically.
- [x] Upload secrets; run migrations; create the admin.
- [x] `https://dj.heroic.ch/` returns 200.
- [x] `/admin/login/` returns 200; admin sign-in reaches “Site administration”.
- [x] `/static/admin/css/base.css` returns 200.
- [x] Admin user and session data persist across requests and redeploys.
- [x] Disable bootstrap: set `BOOTSTRAP_ENABLED=0`, delete the `BOOTSTRAP_TOKEN` secret, redeploy.
- [x] Confirm `/__bootstrap/migrate/` returns 404.
- [x] CI deploy after disabling bootstrap succeeds: https://github.com/puckdoug/cloudflare-django/actions/runs/39704661495

### 7. Documentation — done

- [x] Update `README.md` with the working setup and verification results.
- [x] Record deviations and the corrected commands in this checklist.
- [x] Commit.

## Corrections discovered during implementation

1. **`cf deploy` cannot deploy this Worker.** It uploads only `index.py`; `python_modules` never reaches the runtime. Wrangler is required for deployment.
2. **`python_modules` must be at the project root.** A `python_modules` directory inside `src/` makes Wrangler fail with “cannot exist in your module root”.
3. **Secrets are not in `os.environ`.** Python Workers expose bindings through `self.env`; they must be copied before Django settings import.
4. **Empty secrets cannot reliably clear deployed values.** Use the explicit `BOOTSTRAP_ENABLED` flag to disable bootstrap.
5. **`staticfiles/` must exist before `wrangler deploy`.** Wrangler validates the assets directory before `collectstatic` runs; `.gitkeep` handles fresh clones.
6. **Tests need `DJANGO_TEST=1`.** Loading `django_cf.db.backends.do` outside Workerd fails because the `workers` SDK imports runtime-only modules.
7. **`__pycache__` was committed before `.gitignore` existed.** It is now untracked and ignored.

## Follow-ups

- Re-enable bootstrap temporarily for future schema changes: set `BOOTSTRAP_ENABLED=1`, restore the `BOOTSTRAP_TOKEN` secret, deploy, run migrations, then disable again.
- Cold starts after idle take about 9 seconds; warm requests are ~0.1–0.3s.
- GitHub warns that `actions/checkout@v4`, `actions/setup-node@v4`, and `astral-sh/setup-uv@v5` use Node 20. Update when their Node 24 releases are pinned.
- No staging environment or automated post-deploy smoke test yet.
