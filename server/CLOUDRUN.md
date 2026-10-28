# Deploying the GreenSearch backend to Google Cloud Run

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

## Deploy, step by step

Replace `YOUR_PROJECT_ID` with your project id throughout.

```bash
# 1. Point gcloud at your project, enable the services.
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com secretmanager.googleapis.com \
  artifactregistry.googleapis.com cloudbuild.googleapis.com

# 2. Create the secret from your OpenRouter key.
#    Type or paste the key when prompted; it is not echoed into history
#    if you use --data-file=- with stdin, and it is never committed.
printf '%s' 'YOUR_OPENROUTER_KEY' | \
  gcloud secrets create greensearch-api-key --data-file=-

# 3. Build and deploy from the repo root (the folder with Dockerfile).
#    --allow-unauthenticated makes the demo public, which is what a
#    demo wants. Remove it if you want a private service instead.
#    The first deploy does NOT yet know its own URL, so CORS is set
#    to localhost only for now; step 5 fixes that.
gcloud run deploy greensearch \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-secrets GREENSEARCH_API_KEY=greensearch-api-key:latest \
  --set-env-vars GREENSEARCH_MODEL=openrouter/free \
  --set-env-vars GREENSEARCH_BACKEND_ORIGIN=http://localhost:8000,http://127.0.0.1:8000
```

Note the deploy command for the URL it prints, e.g.
`https://greensearch-abc123-uc.a.run.app`.

```bash
# 4. Check health. It must say "configured": true.
curl https://greensearch-abc123-uc.a.run.app/api/health

# 5. Add the hosted URL to the CORS allowlist, then redeploy the
#    env var only (no rebuild needed for an env change, but
#    `gcloud run deploy` with the same source is the simple path).
gcloud run services update greensearch --region us-central1 \
  --set-env-vars GREENSEARCH_BACKEND_ORIGIN=https://greensearch-abc123-uc.a.run.app,http://localhost:8000,http://127.0.0.1:8000
```

## Using the hosted demo

Open the printed URL in a browser. Live mode is off by default on every
page load. Flip it on: on a `*.run.app` URL the live backend URL field
now defaults to the same origin (`<your-service-url>/api/chat`), so on
the hosted site you should not need to edit it. Ask a
question and check the LIVE metadata row: model that answered, tokens,
latency, and whether a fallback was used.

If the page shows a CORS error ("This page's origin is not allowed"),
step 5 was missed or the URL has a typo — the allowlist must match the
service URL exactly, with no trailing slash.

## Costs and limits to watch

- OpenRouter cost is separate from Cloud Run cost: free models cost
  nothing but are rate-limited and rotate; paid models spend the credits
  in your OpenRouter account, not your Google bill.
- The server is stateless: session cache and rate limiting are
  in-memory per container instance, so they reset on restart and are not
  shared across instances. That is fine for a demo and is not a
  production session store.
- If you rotate the OpenRouter key, update the secret
  (`gcloud secrets versions add greensearch-api-key --data-file=-`) and
  redeploy; the container never holds the old key after that.
- To take the demo down: `gcloud run services delete greensearch
  --region us-central1`.
