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

Inline audit simulations are disabled by default with `SIMULATION_RUN_AUDIT_INLINE=false`. Send `include_audit=true` only when an expensive synchronous audit is explicitly needed.

## Vercel Deployment

This repository includes `vercel.json`, `api/index.py`, and a root `requirements.txt` shim so Vercel can deploy Django through the Python runtime.

Required Vercel environment variables:

- `DJANGO_DEBUG=false`
- `DJANGO_SECRET_KEY`
- `DJANGO_ALLOWED_HOSTS=.vercel.app,<your-backend-domain>`
- `DJANGO_CORS_ALLOWED_ORIGINS=https://<your-frontend-domain>`
- `DJANGO_CORS_ALLOWED_ORIGIN_REGEXES=^https://.*\.vercel\.app$` if preview deployments should call the API
- `DJANGO_SQLITE_PATH=/tmp/db.sqlite3`
- `SIMULATION_AUDIT_LOG_PATH=/tmp/simulation_audit.log`
- `ERROR_TRACKING_DSN=<optional-error-tracking-dsn>`
- `OBSERVABILITY_ENABLED=true`
- `DJANGO_LOG_LEVEL=INFO`

Keep `SIMULATION_RUN_AUDIT_INLINE=false` on Vercel unless you intentionally want slower synchronous function invocations.

## Local Development

```powershell
cd backend
python -m pip install -r backend\requirements.txt
python backend\manage.py runserver
```

## Verification

```powershell
python backend\manage.py test simulation
$env:DJANGO_DEBUG='false'; $env:DJANGO_SECRET_KEY='replace-with-a-long-random-secret'; python backend\manage.py check --deploy
```

## API

- `POST /simulation/`
- `POST /api/simulate/`
- `GET /health`

Simulation requests are validated by DRF serializers and rate-limited with the `simulation` throttle scope.
