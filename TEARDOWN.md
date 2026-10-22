# Teardown

Steps used to remove the Django-on-Cloudflare proof of concept. Deleting the Durable Object class permanently deletes its namespace and all stored data. Back up anything you need first.

## Prerequisites

- `node`/`npm`, `uv`, `wrangler`, and `cf` installed.
- `CF.sh` in the project root containing `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`.
- `gh` authenticated for the repository.
- The Worker name and hostname: `cloudflare-django`, `dj.heroic.ch`.

## 1. Delete the Durable Object namespace and data

A Worker deletion alone is not a documented way to delete Durable Object storage. Use a `deleted` tombstone deploy first.

Back up the working configuration and entrypoint:

```sh
cp src/index.py /tmp/poc-index.py
cp wrangler.jsonc /tmp/poc-wrangler.jsonc
```

Replace `src/index.py` with a stub that does not export `DjangoDO`:

```python
from workers import Response, WorkerEntrypoint


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        return Response("teardown", status=410)
```

Replace `wrangler.jsonc` with a tombstone configuration. Remove `durable_objects`, `migrations`, routes, assets, and build settings; `exports` cannot be combined with `migrations`:

```jsonc
{
  "name": "cloudflare-django",
  "main": "src/index.py",
  "compatibility_flags": ["python_workers"],
  "compatibility_date": "2026-03-08",
  "exports": {
    "DjangoDO": { "type": "durable-object", "state": "deleted" }
  }
}
```

Deploy:

```sh
set -a; . ./CF.sh; set +a
npx wrangler deploy
```

Required output:

```text
Durable Object exports reconciliation:
  Deleted: DjangoDO
```

If the deploy is rejected, the namespace still has a live class, a binding, or another Worker referencing it. Resolve that before continuing.

## 2. Delete the Worker

```sh
npx wrangler delete --force
```

Expected: `Successfully deleted cloudflare-django`.

The tombstone deployment also removed the `dj.heroic.ch` trigger because the teardown configuration had no `routes`.

## 3. Verify DNS and routes

```sh
dig +short dj.heroic.ch @1.1.1.1
npx cf dns records list --zone heroic.ch
```

Expected: no `dj` record. Public resolvers may return a cached address or `522` briefly.

If a record remains, delete it by ID:

```sh
npx cf dns records delete <RECORD_ID> --zone heroic.ch
```

Confirm the Worker is gone:

```sh
curl -s -o /dev/null -w '%{http_code}\n' https://cloudflare-django.doug-27c.workers.dev/
```

Expected: `404`.

## 4. Remove GitHub Actions deployment

Delete all repository secrets:

```sh
gh secret list --json name -q '.[].name' | while read -r name; do
  gh secret delete "$name"
done
```

Expected: `gh secret list` returns nothing.

Remove the workflow so later pushes do not attempt a deployment:

```sh
git rm .github/workflows/deploy.yml
git commit -m "chore: tear down POC resources and disable CI"
git push
```

## 5. Remove local credentials and build output

```sh
rm -f CF.sh .dev.vars
rm -rf node_modules .venv python_modules staticfiles/static .cloudflare .wrangler .wrangler-build
```

Keep `staticfiles/.gitkeep`.

## 6. Verify the teardown

```sh
curl -s -o /dev/null -w 'workers.dev=%{http_code}\n' https://cloudflare-django.doug-27c.workers.dev/
dig +short dj.heroic.ch @1.1.1.1
gh secret list
ls .github/workflows 2>/dev/null || echo "no workflow"
git status --short
git grep -nE 'CLOUDFLARE_API_TOKEN=.+' -- ':!.dev.vars.example' || echo "no tracked tokens"
```

Expected:

- `workers.dev=404`
- no DNS output
- no GitHub secrets
- no workflow
- clean working tree
- no tracked tokens

## 7. Revoke the API token

The Cloudflare API token is not deleted by wrangler. Revoke it in the dashboard if it existed only for this POC:

1. Go to **My Profile → API Tokens**.
2. Find the token used for this project.
3. Select **Delete**.

## Notes

- Durable Object deletion is permanent. There is no trash or restore.
- The Durable Object class could have been removed with a `deleted` tombstone; deleting the Worker alone was not treated as sufficient.
- No D1, R2, KV, Queue, or other billable resources were created by this POC.
- To rebuild the POC, follow `IMPLEMENTATION.md` and recreate the Cloudflare and GitHub credentials.
