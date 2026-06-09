# StoneLink Monte Carlo Simulation Backend

Django REST API for portfolio Monte Carlo simulation.

## Architecture

- `backend/stonelink_backend/`: Django project settings and URL routing.
- `backend/simulation/views.py`: API views for simulation and health checks.
- `backend/simulation/serializers.py`: DRF request validation and bounded inputs.
- `backend/simulation/engine.py`: Monte Carlo engine and numerical aggregation.
- `backend/simulation/ingestion.py`: Excel ingestion with file-mtime caching.
- `backend/simulation/audit.py`: optional expensive self-audit routines.
- `backend/simulation/model_metadata.py`: model version, disclaimer, and limitation metadata.
- `backend/simulation/logging_utils.py`: request ID middleware and JSON logging.
- `backend/simulation/benchmarks.py`: benchmark portfolio and golden regression fixtures.
- `backend/simulation/tests.py`: API, validation, throttling, cache, and numerical regression tests.

## Governance Documents

- `MODEL_METHODOLOGY.md`
- `VALIDATION_FRAMEWORK.md`
- `PRODUCTION_DEPLOYMENT_CHECKLIST.md`
- `ARCHITECTURE.md`
- `OPERATIONAL_RUNBOOK.md`
- `SCALABILITY_ASSESSMENT.md`

## Configuration

Copy `backend/.env.example` into your deployment environment and set the values there. Production must set:

- `DJANGO_DEBUG=false`
- `DJANGO_SECRET_KEY`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CORS_ALLOWED_ORIGINS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`

Inline audit simulations are disabled by default with `SIMULATION_RUN_AUDIT_INLINE=false`. Send `include_audit=true` only when an expensive synchronous audit is explicitly needed.

## Production Deployment — Railway

The primary production backend host is **Railway**.

### Repository structure

```
/ (repo root)
├── railway.json           ← Railway build/start config
├── runtime.txt            ← Python version (python-3.12)
├── backend/
│   ├── Procfile           ← Procfile (used when root dir = backend/)
│   ├── manage.py
│   ├── requirements.txt
│   ├── simulation/
│   │   └── portfolio_data.xlsx   ← committed asset data
│   └── stonelink_backend/
│       ├── settings.py
│       └── wsgi.py
```

### Railway setup

1. Create a Railway project.
2. Connect GitHub repo: `mashok21/stonelink-monte-carlo-simulation`
3. Deploy from branch: `main`
4. **Root directory**: leave as repo root (Railway uses `railway.json` automatically).
5. Railway auto-detects `railway.json`. No manual build/start command needed.

### Railway environment variables

Set these in Railway → Service → Variables:

```text
DJANGO_DEBUG=false
DJANGO_SECRET_KEY=<generate: python -c "import secrets; print(secrets.token_urlsafe(60))">
DJANGO_ALLOWED_HOSTS=<your-service>.up.railway.app,localhost,127.0.0.1
DJANGO_CORS_ALLOWED_ORIGINS=https://stonelink-monte-carlo-simulation-fr.vercel.app
DJANGO_CORS_ALLOWED_ORIGIN_REGEXES=^https://.*\.vercel\.app$
DJANGO_CSRF_TRUSTED_ORIGINS=https://stonelink-monte-carlo-simulation-fr.vercel.app,https://<your-service>.up.railway.app
DJANGO_SECURE_SSL_REDIRECT=true
DJANGO_SESSION_COOKIE_SECURE=true
DJANGO_CSRF_COOKIE_SECURE=true
DJANGO_SECURE_HSTS_SECONDS=31536000
DJANGO_SQLITE_PATH=/tmp/db.sqlite3
SIMULATION_RUN_AUDIT_INLINE=false
DJANGO_LOG_LEVEL=INFO
OBSERVABILITY_ENABLED=true
ERROR_TRACKING_DSN=
```

Replace `<your-service>` with the Railway-generated public domain.

### API endpoints

```text
GET  /health          → Health check (no auth required)
POST /simulation/     → Run Monte Carlo simulation
POST /api/simulate/   → Alternate simulation path
```

### Frontend connection

The Vercel frontend connects via:

```text
VITE_API_BASE_URL=https://<your-service>.up.railway.app
```

Set this in Vercel → Settings → Environment Variables → Production.
Redeploy Vercel after updating the variable.

### Rotating DJANGO_SECRET_KEY

1. Generate a new key: `python -c "import secrets; print(secrets.token_urlsafe(60))"`
2. Update `DJANGO_SECRET_KEY` in Railway Variables.
3. Railway restarts the service automatically. No redeploy required.
   Note: all active sessions will be invalidated (no user sessions in this API).

### Inspecting Railway logs

```bash
# Install Railway CLI
npm install -g @railway/cli
railway login
railway logs --service <service-name>
```

Or use the Railway dashboard → Service → Logs tab.

### Rollback on Railway

Railway dashboard → Deployments → click any previous deployment → **Redeploy**.

## Legacy: Vercel Deployment

This repository also contains a Vercel serverless configuration (`vercel.json`, `api/index.py`) used for the original backend hosting. Railway is now the primary backend host. The Vercel config is retained for reference but the Vercel backend deployment is no longer the production target.

## Local Development

```bash
cd backend
pip install -r requirements.txt
DJANGO_DEBUG=true python manage.py runserver
```

## Running Tests

```bash
cd backend
DJANGO_DEBUG=true DJANGO_SECRET_KEY=dev python manage.py test simulation
```

## Deploy Check

```bash
cd backend
DJANGO_DEBUG=false \
  DJANGO_SECRET_KEY=<50-char-key> \
  DJANGO_ALLOWED_HOSTS=localhost \
  python manage.py check --deploy
```
