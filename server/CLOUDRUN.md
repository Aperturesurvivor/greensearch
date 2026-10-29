# Deploying the Arboris backend to Google Cloud Run

This deploys one container that serves **both** the website (`/`) and the
API (`/api/chat`), so a visitor gets a working live demo at a single URL,
with no separate frontend host and no cross-origin split — once the CORS
allowlist below includes that URL.

**Not deployed by this document.** It is a runbook for the owner (Grant)
to run with his own Google account, billing, and OpenRouter key. No key
ever goes in the repo, in the image, or in a chat message.

## Before you start

- A Google account, a Google Cloud project with billing enabled, and
  the `gcloud` CLI installed and logged in (`gcloud auth login`).
- An OpenRouter API key. The key goes in Secret Manager only, never in
  a repo file, a Dockerfile, or a `gcloud` command that gets pasted
  anywhere public.
- Cloud Run's Always Free tier (2 million requests/month, plus CPU and
  memory allowances) should cover a low-traffic demo, but verify the
  current free-tier page before you rely on it, and set a billing alert.
  A budget alert only emails you — it does not stop spending — so keep
  the service at min-instances 0 (scale to zero, the default).

## Region

Start with `us-central1` for a US demo: it is close to the demo's
audience and is the region the free-tier examples use. Do **not** claim
Finland hosting for this deployment unless you actually deploy to
`europe-north1` and verify the cost there — the eco story is only honest
if the region matches the claim. Changing region later is just a
`--region` change and a redeploy.

Hosting region only covers this server. The model runs wherever
OpenRouter's provider runs it, which is not disclosed, so even a
europe-north1 deployment must not be described as Finland-powered
inference.

## Migrating an existing GreenSearch deployment

The project was renamed from GreenSearch to Arboris in 0.9.0. The
commands below use the new names (service `arboris`, secret
`arboris-api-key`, `ARBORIS_*` variables). A service deployed before the
rename is called `greensearch`, uses the secret `greensearch-api-key`, and
sets `GREENSEARCH_*` variables. It keeps working after you deploy the new
code: for one release the server reads each `GREENSEARCH_*` variable when
its `ARBORIS_*` twin is unset, and logs the legacy names it used at
startup.

Cloud Run cannot rename a service, and a new service gets a new URL. To
move over:

1. Create `arboris-api-key` (step 2 below) or keep using the old secret
   by naming it in `--set-secrets`.
2. Deploy a new `arboris` service (step 3), in `europe-north1` if you want
   the low-carbon hosting region; check that region's price and free tier
   first.
3. Put the new URL in `ARBORIS_BACKEND_ORIGIN` (step 5) and check
   `/api/health`.
4. Once the new URL works, delete the old service:
   `gcloud run services delete greensearch --region us-central1`.

Until then, manage the old service with its own name, for example
`gcloud run services describe greensearch --region us-central1`.

## Deploy, step by step

Replace `YOUR_PROJECT_ID` with your project id throughout.

### Env vars: use an env-vars YAML file (the default method)

Keep the non-secret settings in a local `env.yaml` next to the
Dockerfile and pass it with `--env-vars-file`. The CORS list is one
string, **commas, no spaces** (the server also accepts spaces since
Unreleased, but commas are the canonical form and survive every shell
and YAML tool). Quote every value. Trailing slashes are stripped by the
server, but write origins without one.

```yaml
# env.yaml: local deploy state. Do NOT commit it (it is git-ignored).
# Not a secret (it holds the public service URL), but it is per-deploy
# state, not repo content. The API key is NEVER in here: it is a secret.
ARBORIS_MODEL: "google/gemma-4-31b-it:free"
ARBORIS_BACKEND_ORIGIN: "http://localhost:8000,http://127.0.0.1:8000"
```

> **Warning: `--set-env-vars` and `--env-vars-file` REPLACE the whole
> env var list; `--update-env-vars` changes only the vars you name and
> keeps the rest.** A single-var
> `gcloud run services update ... --set-env-vars ARBORIS_MODEL=...`
> once wiped `ARBORIS_BACKEND_ORIGIN` in production: the allowlist
> fell back to localhost and the hosted page got "This page's origin is
> not allowed". So: either pass the **complete** `env.yaml` (every
> non-secret var, origins and model together), or change one var with
> `--update-env-vars`. Never use `--set-env-vars` for a one-var change.
> After any env change, check with
> `gcloud run services describe arboris --region us-central1 --format='yaml(spec.template.spec.containers[0].env)'`.

```bash
# 1. Point gcloud at your project, enable the services.
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com secretmanager.googleapis.com \
  artifactregistry.googleapis.com cloudbuild.googleapis.com

# 2. Create the secret from your OpenRouter key.
#    Type or paste the key when prompted; it is not echoed into history
#    if you use --data-file=- with stdin, and it is never committed.
printf '%s' 'YOUR_OPENROUTER_KEY' | \
  gcloud secrets create arboris-api-key --data-file=-

# 3. Build and deploy from the repo root (the folder with Dockerfile).
#    --allow-unauthenticated makes the demo public, which is what a
#    demo wants. Remove it if you want a private service instead.
#    The first deploy does NOT yet know its own URL, so env.yaml lists
#    localhost only for now; step 5 fixes that.
gcloud run deploy arboris \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-secrets ARBORIS_API_KEY=arboris-api-key:latest \
  --env-vars-file env.yaml
```

Note the deploy command for the URL it prints, e.g.
`https://arboris-abc123-uc.a.run.app`.

```bash
# 4. Check health. It must say "configured": true.
curl https://arboris-abc123-uc.a.run.app/api/health

# 5. Add the hosted URL to ARBORIS_BACKEND_ORIGIN in env.yaml
#    (commas, no spaces), keep ARBORIS_MODEL in the same file, then
#    apply the whole file. No rebuild is needed for an env change.
#      ARBORIS_MODEL: "google/gemma-4-31b-it:free"
#      ARBORIS_BACKEND_ORIGIN: "https://arboris-abc123-uc.a.run.app,http://localhost:8000,http://127.0.0.1:8000"
gcloud run services update arboris --region us-central1 \
  --env-vars-file env.yaml
```

### Changing just the model later

Use `--update-env-vars`, which leaves the CORS allowlist (and every
other var) in place:

```bash
gcloud run services update arboris --region us-central1 \
  --update-env-vars ARBORIS_MODEL=google/gemma-4-31b-it:free
```

Then update `env.yaml` to match, so the next full `--env-vars-file`
apply does not silently put the old model back.

## Using the hosted demo

Open the printed URL in a browser. Live mode is off by default on every
page load. Flip it on: on a `*.run.app` URL the live backend URL field
now defaults to the same origin (`<your-service-url>/api/chat`), so on
the hosted site you should not need to edit it. Ask a
question and check the LIVE metadata row: model that answered, tokens,
latency, and whether a fallback was used.

If the page shows a CORS error ("This page's origin is not allowed"),
step 5 was missed, the URL has a typo, or a later `--set-env-vars`
replaced the env list (see the warning above). The allowlist must match
the service URL exactly (scheme, host, port). Entries may be separated
by commas and/or spaces, and a trailing slash on an entry is stripped,
so `https://x.run.app/` matches `https://x.run.app`.

## Costs and limits to watch

- OpenRouter cost is separate from Cloud Run cost: free models cost
  nothing but are rate-limited and rotate; paid models spend the credits
  in your OpenRouter account, not your Google bill.
- The server is stateless: session cache and rate limiting are
  in-memory per container instance, so they reset on restart and are not
  shared across instances. That is fine for a demo and is not a
  production session store.
- If you rotate the OpenRouter key, update the secret
  (`gcloud secrets versions add arboris-api-key --data-file=-`) and
  redeploy; the container never holds the old key after that.
- To take the demo down: `gcloud run services delete arboris
  --region us-central1`.
