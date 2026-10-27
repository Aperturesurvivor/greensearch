# Self-hosting the GreenSearch demo

The demo is a single file, `website/index.html`. There is no build step, no dependencies, and no backend. It uses system fonts only and makes no network requests.

## Open it directly

Double-click `website/index.html`, or open it from your browser's File → Open. Everything works from `file://`, including localStorage persistence and Markdown export. Depending on the browser, clipboard copy may fall back to a "copy manually" message on `file://`. Serving over http(s) avoids that.

## Serve it locally

From the repo root:

```sh
cd website
python3 -m http.server 8000
```

Then open http://localhost:8000/. Any static file server works.

## GitHub Pages

1. Create a repository (or use an existing one) for the site.
2. Upload `website/index.html` as `index.html` at the root of the branch you will publish (for example `main`). No other files are needed and there is nothing to build.
3. In the repository, go to **Settings → Pages**. Under **Build and deployment**, set **Source** to **Deploy from a branch**, pick that branch and the `/ (root)` folder, then **Save**.
4. After a minute or two the site appears at `https://<user>.github.io/<repo>/`.

To update, upload a new `index.html`. If the browser shows an old copy, hard-refresh it. Saved chats are stored per site address, so a chat saved at `localhost` won't appear on the Pages URL.

Any static host (Netlify, Cloudflare Pages, an S3 bucket, a plain web server) works the same way: serve the one file.

## What hosting does not change

Hosting this page does not make it a live model. Wherever it is served from, it still gives the same canned answers for 95 topics with estimated token counts, and it still runs entirely in the visitor's browser. A live version would need a backend holding an API key, a real tokenizer, and measured results. It is a different project, not a different hosting choice.
