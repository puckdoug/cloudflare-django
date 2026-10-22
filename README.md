# Django on Cloudflare Workers

A proof of concept for running a minimal Django site on Cloudflare Workers. The site will have a homepage and Django admin, use a Durable Object as its database, and be available at `dj.heroic.ch`.

This README is the implementation plan. The repository is currently just getting started; the steps below describe the intended setup, not a completed deployment.

## Goals

- Run Django on a Python Worker using Cloudflare's [`django-cf`](https://github.com/cloudflare/workers-py/tree/main/packages/django-cf) package.
- Serve a basic homepage and Django admin.
- Persist Django data in one SQLite-backed Durable Object.
- Deploy to `dj.heroic.ch` without Cloudflare dashboard configuration.
- Use `uv` for Python dependencies and automate future deployments with GitHub Actions.
- Use the Cloudflare CLI (`cf`) for account and resource operations where it supports the task.

## Planned architecture

- **Worker runtime:** Python Workers with the `python_workers` compatibility flag. `src/index.py` forwards requests to one named Durable Object instance. The `DjangoDO` class, based on `DjangoCFDurableObject`, serves the Django WSGI application.
- **Django:** Django 5.2 with `django-cf`. The initial site contains a simple homepage and Django admin, with no additional application features.
- **Database:** The `django_cf.db.backends.do` backend uses SQLite storage in the singleton Durable Object. The backend does not support transactions, and some Django admin ORM operations may be limited.
- **Static files:** `collectstatic` writes to `staticfiles/`; Workers Static Assets serves those files with the Worker. This keeps admin CSS and JavaScript in the same deployment without requiring an R2 bucket. R2 can be considered later for user-uploaded or independently updated files.
- **Domain:** Configure `dj.heroic.ch` as a custom domain in the Worker configuration and deploy it. Cloudflare must host the `heroic.ch` zone, and the domain must not have a conflicting record.
- **Access:** The initial PoC is publicly reachable. Django admin remains protected by Django authentication; bootstrap endpoints are protected separately as described below.

## Tooling

- Python dependencies and lockfile: `pyproject.toml` and `uv.lock`.
- Python Worker packaging, local development, and deployment: `workers-py` / `pywrangler`, following the current Python Workers documentation and the `django-cf` Durable Objects template.
- Node.js: required by the Python Worker toolchain; pin the Wrangler dependency used by `pywrangler`.
- Cloudflare account tasks: prefer `cf` commands when available, including account/zone checks and resource operations.
- GitHub Actions: run the same locked dependencies and deployment command used locally.

The Cloudflare CLI is in beta. Its current project migration and deployment flow is not documented for Python Workers. `pywrangler` is the documented Python Worker tool, so it remains the deployment path unless the spike below proves that `cf` can build and deploy this project correctly.

## Implementation plan

### 1. Test whether `cf` can replace `pywrangler`

Use a disposable copy of the upstream Durable Objects template; do not modify the project during this test.

1. Run `cf migrate --dry-run` against its Wrangler configuration and inspect how it handles Python Worker settings and the Durable Object class migration.
2. If migration is viable, test `cf build` and inspect the resulting Worker bundle for Django and its Python dependencies.
3. Record the result here. Use `cf` for build/deploy only if the test confirms the deployed bundle includes the Django app and the DO configuration works. Otherwise, keep `pywrangler` for build/deploy and use `cf` for supported account-level tasks.

### 2. Create the minimal Django Worker

Start from the upstream `django-cf` Durable Objects template and trim it to this PoC. Use `uv` rather than `pip` for dependency management. Keep the upstream Worker entrypoint and settings conventions unless the spike or local tests show a necessary change.

Expected project structure:

```text
.github/workflows/deploy.yml   GitHub Actions deployment
scripts/deploy.sh              Repeatable local deploy/bootstrap command
src/index.py                   Python Worker and singleton DO entrypoint
src/app/                       Django project, homepage, settings, and URLs
staticfiles/                   collectstatic output; generated, not committed
pyproject.toml                 Python dependencies and tool configuration
uv.lock                        Locked Python dependencies
wrangler.jsonc                 Python Worker, DO, static assets, and domain config
```

Pin Django, `django-cf`, `workers-py`, the runtime SDK, and Node tooling to tested versions. Commit the `uv.lock` file.

### 3. Add safe first-run setup

The upstream template describes HTTP endpoints for Django migrations and superuser creation. Its sample protection assumes a superuser already exists, so it cannot bootstrap the first account securely as-is.

Implement token-protected setup endpoints for applying Django migrations and creating the initial admin account:

- Require a `BOOTSTRAP_TOKEN` secret in the `Authorization: Bearer` header; compare tokens in constant time.
- Return `404` when the secret is absent and `401` for an invalid token.
- Read the initial admin username, email, and password from deployment secrets; never commit them or print them in logs.
- Make the setup operation safe to repeat, and disable or remove the endpoints after bootstrap. Verify the exact request flow and secret-setting command against the pinned `pywrangler` version before finalizing the script.

The local deployment script should check prerequisites and authentication, verify the `heroic.ch` zone using `cf`, sync Python dependencies, deploy the Worker, wait for the domain to answer, then call the protected setup endpoints. It should report errors and stop rather than continue after a failed step.

### 4. Automate deployment

Create the GitHub repository and add a GitHub Actions workflow that deploys on pushes to `main`. The workflow should:

1. Check out the repository and install the pinned Node.js and `uv` versions.
2. Run `uv sync --locked` and the project's checks.
3. Deploy with `pywrangler` (or `cf` only if the spike validates that path).
4. Run the protected initial migration/admin bootstrap using GitHub Actions secrets.

Configure repository secrets for `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `BOOTSTRAP_TOKEN`, and the initial Django admin credentials. Use a narrowly scoped Cloudflare API token. Do not expose deployment secrets to untrusted pull-request jobs. Keep any bootstrap operation repeatable and safe on later deployments; do not recreate or reset the admin password on each push.

Create the repository and configure its secrets through command-line tooling where possible. Minting a Cloudflare API token is a one-time account credential setup; no routine deployment should require dashboard changes.

## Local development and verification

The intended local development command is:

```sh
uv sync --locked
uv run pywrangler dev
```

Verify the local Worker before deploying:

- Django's system check passes.
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
- `cf` is beta and its Python Worker support is not documented. Keep the tested `pywrangler` deployment path until `cf` passes the spike.
- Custom domain deployment depends on the `heroic.ch` zone being active in the target Cloudflare account and free of conflicting DNS records.
- Pin the Python and Node tool versions used by local development and CI; update them deliberately after testing.

## References

- [django-cf package and templates](https://github.com/cloudflare/workers-py/tree/main/packages/django-cf)
- [Cloudflare Python Workers](https://developers.cloudflare.com/workers/languages/python/)
- [Python Workers packages and Pywrangler](https://developers.cloudflare.com/workers/languages/python/packages/)
- [Cloudflare CLI](https://developers.cloudflare.com/cf/)
- [`cf` in CI](https://developers.cloudflare.com/cf/ci/)
