# Self-hosting the Arboris site

The site and package are named Arboris (renamed from GreenSearch in 0.9.0).

The site is a single file, `website/index.html`, with no build step and no dependencies. It is **live only**: every question goes to an Arboris backend, which holds the API key. The page by itself, with no backend running, shows backend errors instead of answers.

## Run it locally (recommended)

From the repo root, start the backend — it serves the site itself at `/`:

```sh
python3 server/app.py
```

Then open http://localhost:8000/. The backend URL defaults to the same origin on the hosted site and to `http://localhost:8000/api/chat` elsewhere, so this just works. See `server/README.md` for the backend's environment variables (API key, model, rate limits).

## Serve the file separately

Any static file server works for the file itself, but the page still needs a backend:

```sh
cd website
python3 -m http.server 8000
```

Then open the static URL and set the backend URL in the page's settings popover to your running backend (for example `http://localhost:8000/api/chat`). The backend's CORS allowlist must include the static page's origin, or the browser blocks the calls — see `server/README.md` for the allowlist setting.

Opening `website/index.html` directly from `file://` is not recommended: it tries the localhost backend by default, and cross-origin rules may block it.

## GitHub Pages

GitHub Pages alone has no backend, so the site there will show backend errors unless you point its backend URL (in settings) at a running backend that allows the Pages origin. To publish the file:

1. Create a repository (or use an existing one) for the site.
2. Upload `website/index.html` as `index.html` at the root of the branch you will publish (for example `main`). No other files are needed and there is nothing to build.
3. In the repository, go to **Settings → Pages**. Under **Build and deployment**, set **Source** to **Deploy from a branch**, pick that branch and the `/ (root)` folder, then **Save**.
4. After a minute or two the site appears at `https://<user>.github.io/<repo>/`.

To update, upload a new `index.html`. If the browser shows an old copy, hard-refresh it. Saved chats are stored per site address, so a chat saved at `localhost` won't appear on the Pages URL.

Any static host (Netlify, Cloudflare Pages, an S3 bucket, a plain web server) works the same way for the file — but the backend is still required for answers.
