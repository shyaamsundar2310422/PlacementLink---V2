# PlacementLink deployment guide

## Architecture choice

PlacementLink currently uses one Flask application for authentication, Flask sessions, Jinja-rendered student/admin/mentor pages, static assets, uploads, and database-backed workflows. A separate Vercel static frontend would require converting those server-rendered flows into a client application and API. That is not necessary for deployment.

The included setup keeps Flask on Render and configures Vercel as a same-origin reverse proxy to it. The Vercel project forwards page, form, upload, and static requests to the Render service. Flask remains responsible for rendering every page and maintaining login sessions. This avoids React migration and cross-origin credential/CORS changes. The Vercel project is a proxy layer, not an independently built frontend.

| Component | Deployment |
|---|---|
| Flask/Jinja application | Render Web Service, one worker, 2 GB RAM |
| Vercel entry URL | Vercel project using `vercel.json` rewrite to Render |
| Relational data | External managed MySQL, with TLS enabled by provider URL or CA |
| Uploaded resumes/JDs and model cache | Render persistent disk mounted at `/var/data` |
| Semantic matching | Existing CPU SentenceTransformer `all-MiniLM-L6-v2`; cached under `/var/data/huggingface` |
| Placement AI / resume review | Optional remotely reachable Ollama endpoint; local `localhost` is not reachable from Render |

Render does not offer a managed MySQL product. Use a MySQL provider such as DigitalOcean Managed MySQL or Aiven, and keep it in a region near the Render service. This deployment configuration does not create a database or move any data.

## Accounts and services

You will need:

1. A Git provider account with this repository and permission to select `deployment/vercel-render`.
2. A Render account for the Flask service and persistent disk.
3. A managed MySQL account and an empty or separately prepared PlacementLink database.
4. A Vercel account if you want the Vercel URL/proxy layer. Vercel is optional; the Render URL serves the full app directly.
5. Optional hosted Ollama service and SMTP account. Neither is required for login, uploads, semantic matching, or non-email workflows.

Do not copy the local `.env` file to either hosting service. Set its values in the provider secret/environment-variable interface.

## Render setup

1. In the Render dashboard, create a Blueprint from this repository and select branch `deployment/vercel-render`.
2. Review `render.yaml`. It specifies Python 3.11.9, the `1c-2g` web plan, Singapore region, Gunicorn, `/healthz`, and a 2 GB persistent disk at `/var/data`.
3. Supply `DATABASE_URL` as a secret. It must be a MySQL URL of the form:

   ```text
   mysql://USER:URL_ENCODED_PASSWORD@HOST:3306/DATABASE?ssl-mode=VERIFY_IDENTITY
   ```

   URL-encode reserved characters in the username/password. If your provider requires a CA certificate, add it as a Render secret file and set `DB_SSL_CA` to the mounted file path. A CA file enables certificate and hostname verification. Otherwise set `DB_SSL_MODE=required` (encrypted connection with system CA verification) or use the SSL mode/query string supplied by your provider. Use `disabled` only for trusted private-network MySQL that does not support TLS.

   Add the Render service's outbound IP addresses to the managed database's trusted-source/allowlist configuration, then verify the provider hostname, port, database name, and TLS settings. Keep the database private to those sources where the provider allows it.

4. Render generates `SECRET_KEY` from `render.yaml`. Keep it secret and stable across deploys so user sessions remain valid.
5. Set `OLLAMA_URL` only to a reachable Ollama-compatible `/api/generate` endpoint. Set `OLLAMA_MODEL` to a model already available there. If omitted/unavailable, the app's existing local feedback paths report AI service unavailability. `http://localhost:11434` means the Render container itself and will not reach a workstation Ollama process.
6. Configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_USE_TLS`, and `MAIL_FROM` only if outbound email is desired. The deployment setup does not send test emails.
7. Review the Blueprint diff and deploy only after you approve the public service and any provider costs. This repository change does not create a service or initiate a deploy.

The app uses `UPLOAD_FOLDER=/var/data/uploads`; the route `/static/uploads/<filename>` continues to serve the file URLs already stored by the application. The model cache uses `HF_HOME=/var/data/huggingface`. The first semantic request downloads MiniLM once; later requests reuse the cache. The model is not downloaded at every page request.

The application runs its existing idempotent `ensure_*` calls during startup. On a fresh MySQL database, initialize the base tables from `database/schema.sql` using a database administrator or migration operator. The runtime database user must be able to perform the existing additive startup migrations (CREATE/ALTER) for the app's additional columns and audit table. Do not run seed scripts against production as part of deployment.

## Vercel setup

1. Import the same repository into Vercel and select `deployment/vercel-render`.
2. Set **Root Directory** to `vercel-frontend` and use the **Other** framework preset. There is no frontend build command or output directory; `vercel-frontend/vercel.json` forwards requests to `https://placementlink-backend.onrender.com`. Keeping this small proxy root separate prevents Vercel from detecting/bundling the Flask app and its PyTorch dependencies.
3. If Render assigns a different service hostname, edit the `destination` in `vercel.json` to that exact HTTPS service URL before deploying the Vercel project.
4. No CORS setting is needed: browser requests use the Vercel origin and are proxied to Flask on that same origin. Flask sessions use secure cookies in production. Do not add a separate browser API origin without introducing and reviewing explicit CORS and CSRF protections.
5. After the Render service is ready, deploy the Vercel project only when you approve publishing it. Verify the Vercel domain and direct Render domain both use HTTPS.

If you do not need a Vercel domain, skip Vercel and use the Render service URL. The Flask pages and static assets are already served by Render.

## Environment variables

| Variable | Required | Purpose |
|---|---:|---|
| `APP_ENV` | Yes on Render | Set to `production`; enables secure session cookies and disables Flask debug mode. |
| `SECRET_KEY` | Yes | Long random session signing secret. Render generates one in the Blueprint. |
| `DATABASE_URL` | Yes | MySQL URL. Alternatively use `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, and `DB_NAME`. |
| `DB_SSL_MODE` | Provider-dependent | `disabled`, `required`, or `verify_identity`; URL query `ssl-mode` is also accepted. |
| `DB_SSL_CA` | Provider-dependent | Path to a mounted CA file; certificate and hostname verification are enabled. |
| `DB_CONNECT_TIMEOUT` | No | MySQL connection timeout in seconds; defaults to 10. |
| `UPLOAD_FOLDER` | Yes on Render | `/var/data/uploads`, on the persistent disk. Local default remains `static/uploads`. |
| `HF_HOME` | Yes on Render | `/var/data/huggingface`, on the persistent disk. |
| `HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE` | No | Leave `0` on first use so the model can be downloaded; set `1` only after verifying the cache is populated. |
| `OLLAMA_URL`, `OLLAMA_MODEL` | Optional | Reachable Ollama `/api/generate` endpoint and installed model name. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_USE_TLS`, `MAIL_FROM` | Optional | Existing email workflow settings. |
| `MAX_CONTENT_LENGTH` | No | Maximum request size, defaults to 16 MiB. |

`.env.example` is a local template. Never commit `.env` or enter secrets in `render.yaml`, `vercel.json`, or `DEPLOYMENT.md`.

## Local checks

From the repository root on Python 3.11:

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m compileall -q app.py config.py database models routes services ml
```

Run locally with configured MySQL and optional services:

```powershell
$env:APP_ENV = "development"
python app.py
```

`GET /healthz` confirms that Flask started. `GET /readyz` performs a database `SELECT 1` and returns 503 if MySQL cannot be reached. Both can be checked without signing in. Health checks do not validate Ollama or load the embedding model.

## Deployment verification checklist

After an approved deployment:

1. Confirm Render reports the service healthy and `https://<render-host>/healthz` returns `{"status":"ok"}`.
2. Confirm `/readyz` returns 200 and `{"status":"ready","database":"ok"}`.
3. Open `/auth/login`, sign in using an existing test account, and check the student dashboard, profile, opportunities, applications, and Placement Intelligence pages.
4. Upload a non-sensitive test PDF or DOCX from My Profile. Confirm the filename/status, reload the page, and open its file URL. Verify the file remains after a service restart/redeploy before uploading real files.
5. Sign in as an admin test account, add/edit a test job with a PDF/DOCX JD, and verify its file URL and stored extracted text. Do not send email alerts as part of this check.
6. With the embedding model available, compare a test resume against at least two JDs. Confirm scores are cosine-based, semantic ordering is sensible, and matched/missing skills and eligibility remain separate. A first run can take longer while MiniLM downloads.
7. Check Placement Intelligence and resume review. If configured Ollama is unreachable or times out, verify the existing fallback message appears. Only claim LLM integration verified after an actual successful call to the hosted endpoint.
8. Repeat login, profile and upload checks through the Vercel URL if using the proxy. Also check the direct Render URL.

Do not use real student resumes for initial verification. Uploaded files keep their existing `/static/uploads/...` URLs, but are served through an authenticated route: students can access their own documents, assigned mentors/admins can access student resumes, and signed-in users can open job descriptions.

## Current limits and service choices

- Render persistent disks are attached to a single service instance; this configuration uses one Gunicorn worker. Horizontal scaling would require moving resume/JD files to object storage and coordinating the embedding cache.
- The 2 GB service plan is selected because PyTorch and MiniLM need more memory than Render's 512 MB free plan. The first cache download also needs outbound network access.
- Ollama is not bundled or hosted by this repository. A remote model service needs its own reachable URL, model, authentication/network controls, and budget.
- The Vercel layer is a rewrite/proxy, not a React/static frontend. It is optional and may be removed by using the Render URL directly.

### Approximate monthly hosting cost

Using the configured Render `1c-2g` plan ($25/month), a 2 GB Render disk ($0.50/month), DigitalOcean Managed MySQL single-node 1 GiB ($15.15/month), and Vercel Hobby ($0 for personal projects), the starting estimate is **about $40.65/month USD**, before taxes, bandwidth overages, backups/add-ons, and any hosted Ollama or email service. Vercel Pro is listed at $20/month for professional use, which would make the comparable baseline about $60.65/month before usage adjustments. Confirm prices and account eligibility before creating services: [Render compute and disk pricing](https://render.com/pricing), [DigitalOcean MySQL pricing](https://docs.digitalocean.com/products/databases/mysql/details/pricing/), [Vercel pricing](https://vercel.com/pricing).

## Rollback

No deployment or GitHub push is performed by these instructions.

- **Local Git code:** From any branch, `git switch backup/pre-deployment-20261030` returns to the verified Phase 1 checkpoint. To undo only a later deployment-config commit, switch to `deployment/vercel-render` and use `git revert <deployment-config-commit>`; this creates a new inverse commit without resetting history. `main` remains at its original `b7bbd19` commit.
- **Render service:** In the Render service's **Deploys** page, select the last known good deploy and choose **Rollback**. This rolls back app code; it does not reset or delete MySQL data or persistent disk contents. If configuration changed, restore the prior environment values and redeploy.
- **Vercel proxy:** In the Vercel project's **Deployments** page, promote the last known good deployment. This does not affect Render data.
- **Database and uploaded files:** Never reset the database or delete the persistent disk for an application rollback. Restore database/file data only through the provider's documented backup procedure and an explicitly approved recovery plan.
