# Production Deployment Checklist

## Required Backend Environment Variables

```text
DJANGO_DEBUG=false
DJANGO_SECRET_KEY=<long-random-secret>
DJANGO_ALLOWED_HOSTS=.vercel.app,<production-api-domain>
DJANGO_CORS_ALLOWED_ORIGINS=https://<production-frontend-domain>
DJANGO_CORS_ALLOWED_ORIGIN_REGEXES=^https://.*\.vercel\.app$
DJANGO_CSRF_TRUSTED_ORIGINS=https://<production-frontend-domain>
DRF_ANON_THROTTLE_RATE=120/min
DRF_USER_THROTTLE_RATE=600/min
SIMULATION_THROTTLE_RATE=20/min
SIMULATION_RUN_AUDIT_INLINE=false
DJANGO_SECURE_SSL_REDIRECT=true
DJANGO_SESSION_COOKIE_SECURE=true
DJANGO_CSRF_COOKIE_SECURE=true
DJANGO_SECURE_HSTS_SECONDS=31536000
DJANGO_SQLITE_PATH=/tmp/db.sqlite3
SIMULATION_AUDIT_LOG_PATH=/tmp/simulation_audit.log
ERROR_TRACKING_DSN=<optional-error-tracking-dsn>
OBSERVABILITY_ENABLED=true
DJANGO_LOG_LEVEL=INFO
```

## Required Frontend Environment Variables

```text
VITE_API_BASE_URL=https://<production-api-domain>
VITE_SHOW_DIAGNOSTICS=false
```

## Pre-Deploy Checks

Backend:

```powershell
python backend\manage.py test simulation
$env:DJANGO_DEBUG='false'; $env:DJANGO_SECRET_KEY='replace-with-a-long-random-secret'; python backend\manage.py check --deploy
```

Frontend:

```powershell
npm audit --package-lock-only
npm run lint
npm test
npm run build
```

## Post-Deploy Smoke Tests

- `GET /health` returns HTTP 200.
- Health includes `model_version`, `schema_version`, and observability fields.
- `POST /simulation/` returns HTTP 200 for a small fixed-seed request.
- Response includes `metadata.request_id`, `metadata.model_version`, `metadata.disclaimer`, and runtime metrics.
- Frontend loads without console runtime errors.
- Frontend disclaimer is visible before results are interpreted.
- Browser network calls target the configured production API URL.

## Rollback Criteria

Rollback if any of the following occur:

- health endpoint fails
- simulation endpoint returns sustained 5xx errors
- model version in API differs from documented expected version
- CORS blocks production frontend
- response schema validation fails
- runtime p95 exceeds the configured serverless/function budget

## Release Evidence

Each release should record:

- git commit hash
- model version
- schema version
- workbook/data effective date
- test command output
- deployment URL
- smoke test result
