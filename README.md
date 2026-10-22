# Django on Cloudflare Workers

A proof of concept for running a minimal Django site on Cloudflare Workers. The site will have a homepage and Django admin, use a Durable Object as its database, and be available at `dj.heroic.ch`.

This README is the implementation plan. The repository is currently just getting started; the steps below describe the intended setup, not a completed deployment.

## Goals

- Run Django on a Python Worker using Cloudflare's [`django-cf`](https://github.com/cloudflare/workers-py/tree/main/packages/django-cf) package.
- Serve a basic homepage and Django admin.
- Persist Django data in one SQLite-backed Durable Object.
- Deploy to `dj.heroic.ch` without Cloudflare dashboard configuration.
- Use `uv` for Python dependencies and automate future deployments with GitHub Actions.
- Use the Cloudflare CLI (`cf`) for deployment, account, and resource operations.

## Planned architecture

- **Worker runtime:** Python Workers with the `python_workers` compatibility flag. `src/index.py` forwards requests to one named Durable Object instance. The `DjangoDO` class, based on `DjangoCFDurableObject`, serves the Django WSGI application.
- **Django:** Django 5.2 with `django-cf`. The initial site contains a simple homepage and Django admin, with no additional application features.
- **Database:** The `django_cf.db.backends.do` backend uses SQLite storage in the singleton Durable Object. The backend does not support transactions, and some Django admin ORM operations may be limited.
- **Static files:** `collectstatic` writes under `staticfiles/` and is served at `/static/` by Workers Static Assets. This keeps admin CSS and JavaScript in the same deployment without requiring an R2 bucket. R2 can be considered later for user-uploaded or independently updated files.
- **Domain:** Configure `dj.heroic.ch` as a custom domain in the Worker configuration and deploy it. Set `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` for the hostname. Cloudflare must host the `heroic.ch` zone, and the domain must not have a conflicting record.
- **Access:** The initial PoC is publicly reachable. Django admin remains protected by Django authentication; bootstrap endpoints are protected separately as described below.

## Tooling

- Python dependencies and lockfile: `pyproject.toml` and `uv.lock`.
- Dependency bundling: `uv export --format requirements-txt --no-dev --no-emit-project --no-hashes`, then `uv pip install --target src/vendor --no-compile -r <exported-file>`. The Worker entrypoint adds the absolute `src/vendor` path to `sys.path`. Do not commit vendored packages.
- Worker build, local development, and deployment: Cloudflare CLI (`cf`), using `cloudflare.config.ts` plus `wrangler.config.ts` (generated once by `cf migrate`).
- Node.js: required by `cf`; pin `cf` and `wrangler` as development dependencies.
- Cloudflare account tasks: `cf` for account checks, zone checks, logs, and supported resource operations.
- GitHub Actions: run the same locked dependencies and `cf` commands used locally.

The Cloudflare CLI is in beta. The spike below shows it builds and validates this Python Worker correctly; remote deployment still needs verification with an API token.

## Implementation plan

### 1. Spike results (complete)

Environment: macOS, `cf` 1.0.0-beta.20, Wrangler 4.151.3, `uv` 0.13.4, Node 26.12.0. Tested on a disposable, git-initialized copy of the upstream Durable Objects template.

**Migration (`cf migrate`)**

- Preconditions: a clean git worktree including untracked files, a local Wrangler 4.136.0 or newer, and a local `cf` dependency. The migration updated `package.json` and its lockfile to add `cf`.
- Converted correctly: worker name, compatibility date, `python_workers` flag, `main: src/index.py`, `python_modules` exclusions, the `collectstatic` build command, `assets.directory`, observability, and the Durable Object binding.
- Generated two files: `cloudflare.config.ts` (entrypoint, compatibility flag, `env.DO_STORAGE` as `bindings.durableObject`) and `wrangler.config.ts` (`pythonModules`, `build`, `assetsDirectory`).
- Durable Object migrations are unsupported. The replacement is `exports: { DjangoDO: exports.durableObject({ storage: "sqlite" }) }`.
- The migration inserts a top-level `throw` and TODO comments. `cf dev`, `cf build`, and `cf deploy` fail with `Migration incomplete` until they are removed.

**Dependency bundling**

- `cf build` delegates to Wrangler and does not read `.venv`. Without vendoring, the output was a 189-byte bundle containing only `index.py`.
- It does include Python modules under the entrypoint directory (`src/`). Installing dependencies into `src/vendor` produced 1,146 modules, 6.0 MiB, including Django 5.2.6, `django-cf` 0.2.17, asgiref 3.12.1, sqlparse 0.6.0, tzdata 2026.5, and `workers-runtime-sdk` 1.9.5 (pulled in by `django-cf`).
- The exploratory command was `uv pip install --target src/vendor --no-compile django==5.2.6 django-cf tzdata`. The implementation should export the lock instead of repeating pins: `uv export --format requirements-txt --no-dev --no-emit-project --no-hashes`, then install that file into `src/vendor`.
- Imports require an absolute path. `sys.path.insert(0, "vendor")` failed. The working form is `sys.path.insert(0, os.path.join(os.path.dirname(__file__), "vendor"))`, executed before importing Django or the app.
- `python_modules.exclude` removes `*.css`, `*.js`, and images from the Python bundle; those files are served from the assets directory instead.

**Local and deploy validation**

- `cf dev` used the Wrangler bundler (no Vite), listened on `http://localhost:8787`, and returned `django 5.2.6` after the `sys.path` fix.
- `cf deploy --dry-run` validated a 6,018 KiB upload (1,332.78 KiB gzip) and recognized the `DO_STORAGE` Durable Object binding. It made no API requests and needed no credentials.
- A real remote deploy was not tested because no API token was available. That remains the main open verification.

**`pywrangler` limitation**

- `uv run pywrangler sync` first failed because `uv` installed the Pyodide Python under `~/Library/Application Support/uv/...`; the space in that path breaks the Node-based shim. Setting `UV_PYTHON_INSTALL_DIR` to a space-free path allowed the interpreter install.
- It then failed while fetching the dependency index: TCP reached `index.pyodide.org`, but TLS connections were reset (`Broken pipe`). `pyodide.org` failed similarly; PyPI and Cloudflare documentation worked. This is specific to the current network.
- `pywrangler` remains the documented Python Worker tool, but it cannot be used here. The vendoring step avoids both its bundling step and the unreachable index.

Decision: use `cf` for build/deploy and replace `pywrangler` dependency bundling with the vendoring step described above.

### 2. Create the minimal Django Worker

Start from the upstream `django-cf` Durable Objects template and trim it to this PoC. Use `uv` rather than `pip` for dependency management. Keep the upstream Worker entrypoint and settings conventions unless the spike or local tests show a necessary change.

Two changes are required by the spike:

- `src/index.py` must add `src/vendor` to `sys.path` before importing the Django app or any dependency.
- Change the migrated build command in `wrangler.config.ts` to use the uv environment while keeping the template's `WORKERS_CI=1` guard that empties `DATABASES` for collectstatic: `WORKERS_CI=1 uv run --locked python src/manage.py collectstatic --noinput`.

Expected project structure:

```text
.github/workflows/deploy.yml   GitHub Actions deployment
scripts/deploy.sh              Repeatable local deploy/bootstrap command
scripts/vendor.sh              Export the lock and install runtime deps into src/vendor
src/index.py                   Python Worker and singleton DO entrypoint
src/app/                       Django project, homepage, settings, and URLs
src/vendor/                    Vendored runtime dependencies; generated, not committed
staticfiles/                   collectstatic output; generated, not committed
.cloudflare/                   cf Build Output and generated types; gitignored
pyproject.toml                 Python dependencies and tool configuration
uv.lock                        Locked Python dependencies
cloudflare.config.ts           Worker entrypoint, bindings, and DO exports
wrangler.config.ts             Python modules, build command, and assets directory
```

`wrangler.jsonc` exists only long enough to run `cf migrate` once; delete it after the migration is committed. Pin Django, `django-cf`, `cf`, and Wrangler to tested versions. Commit the `uv.lock` file and both generated TypeScript config files.

### 3. Add safe first-run setup

The upstream template describes HTTP endpoints for Django migrations and superuser creation. Its sample protection assumes a superuser already exists, so it cannot bootstrap the first account securely as-is.

Implement token-protected setup endpoints for applying Django migrations and creating the initial admin account:

- Require a `BOOTSTRAP_TOKEN` secret in the `Authorization: Bearer` header; compare tokens in constant time.
- Return `404` when the secret is absent and `401` for an invalid token.
- Read the initial admin username, email, and password from deployment secrets; never commit them or print them in logs.
- Make the setup operation safe to repeat, and disable or remove the endpoints after bootstrap.
- Upload secrets with `cf deploy --secrets-file <PATH>`. The deploy script builds that file from environment variables in a temporary location and deletes it afterwards.

The local deployment script should check prerequisites and authentication, verify the `heroic.ch` zone using `cf`, run `uv sync --locked`, vendor the runtime dependencies, deploy the Worker, wait for the domain to answer, then call the protected setup endpoints. It should report errors and stop rather than continue after a failed step.

### 4. Automate deployment

Create the GitHub repository and add a GitHub Actions workflow that deploys on pushes to `main`. The workflow should:

1. Check out the repository and install the pinned Node.js and `uv` versions.
2. Run `uv sync --locked`, vendor the runtime dependencies, and run the project's checks.
3. Build and deploy with `cf`: `cf build`, then `cf deploy --prebuilt --secrets-file <PATH>`. The Wrangler bundler records no mode, so do not pass `--mode`.
4. Run the protected initial migration/admin bootstrap using GitHub Actions secrets.

Configure repository secrets for `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `BOOTSTRAP_TOKEN`, and the initial Django admin credentials. Use a narrowly scoped Cloudflare API token. Do not expose deployment secrets to untrusted pull-request jobs. Keep any bootstrap operation repeatable and safe on later deployments; do not recreate or reset the admin password on each push.

Create the repository and configure its secrets through command-line tooling where possible. Minting a Cloudflare API token is a one-time account credential setup; no routine deployment should require dashboard changes.

## Local development and verification

The intended local development commands are:

```sh
uv sync --locked
./scripts/vendor.sh
cf dev
```

Use a local `.dev.vars` file for `BOOTSTRAP_TOKEN` and admin credentials when testing bootstrap. Do not commit it. `cf dev` serves on `http://localhost:8787` by default; confirm `.dev.vars` loading on the pinned `cf` version.

Verify the local Worker before deploying:

- Django's system check passes.
- `cf build` completes and `cf deploy --dry-run` reports the `DO_STORAGE` binding and a bundle containing Django.
- `/` returns `200` and displays the PoC homepage.
- `/admin/` renders and its CSS/JavaScript load from Workers Static Assets.
- The admin login works and persists Django data through the Durable Object backend.
- Bootstrap endpoints return `404` without a configured token and `401` with an invalid token.
- A valid bootstrap request applies migrations and creates the initial administrator exactly once.

Add automated tests for the homepage and bootstrap authorization behavior. Exercise the real Worker locally as part of verification because Django's ordinary test runner may not reproduce Workers bindings or the Durable Object backend.

## Deployment verification

After the first deployment:

- Confirm the GitHub Actions deployment succeeds and `https://dj.heroic.ch/` returns `200`.
- Confirm `/admin/` loads with static assets, and that an administrator can sign in.
- Confirm data persists across requests and a subsequent Worker deployment.
- Confirm the bootstrap endpoints are unavailable after bootstrap or when the bootstrap secret is removed.
- Confirm a later push to `main` deploys without manual Cloudflare dashboard changes.

## Known limitations and risks

- The DO database backend disables transactions. Django features that rely on transactional behavior may not work, and some admin operations may be unsupported.
- One singleton Durable Object serializes this PoC's database work; this is acceptable for a basic site, not a scaling design.
- Django startup and request CPU use must be checked on the Workers Paid plan. The upstream package notes that Django may exceed free-plan CPU limits.
- `cf` is beta. The spike verified build, dev, and dry-run deploy locally, but a real remote deploy still needs verification with an API token.
- Vendoring works for pure-Python packages. If a dependency gains a compiled or non-Pyodide-compatible component, dependency bundling must be revisited.
- `index.pyodide.org` is unreachable from the current network, so `pywrangler sync` cannot be used here. The vendoring step avoids it.
- Custom domain deployment depends on the `heroic.ch` zone being active in the target Cloudflare account and free of conflicting DNS records.
- Pin the Python and Node tool versions used by local development and CI; update them deliberately after testing.

## References

- [django-cf package and templates](https://github.com/cloudflare/workers-py/tree/main/packages/django-cf)
- [Cloudflare Python Workers](https://developers.cloudflare.com/workers/languages/python/)
- [Cloudflare CLI](https://developers.cloudflare.com/cf/)
- [`cf` in CI](https://developers.cloudflare.com/cf/ci/)
- [Migrate a Wrangler project](https://developers.cloudflare.com/cf/wrangler/migrate/)
