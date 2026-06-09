# Operational Runbook

## Health Check

Endpoint:

```text
GET /health
```

Expected fields:

- `backend_version`
- `build_date`
- `schema_version`
- `model_version`
- `observability.request_ids`
- `observability.structured_logging`
- `observability.error_tracking_configured`
- `disclaimer`

## Incident: Frontend Cannot Reach API

Check:

1. Frontend `VITE_API_BASE_URL`.
2. Backend `DJANGO_ALLOWED_HOSTS`.
3. Backend `DJANGO_CORS_ALLOWED_ORIGINS`.
4. Browser network errors.
5. Backend logs for matching `X-Request-ID`.

## Incident: Simulation 500 Errors

Check:

1. Response body `request_id`.
2. Platform logs for the same `request_id`.
3. Workbook availability at `backend/simulation/portfolio_data.xlsx`.
4. Input payload bounds.
5. Correlation matrix repair errors.
6. Function timeout or memory pressure.

## Incident: High Latency

Check:

1. `metadata.runtime_ms.simulation`.
2. `metadata.runtime_ms.total_request`.
3. `num_trials` and `years` in request.
4. Whether `include_audit=true` was used.
5. Serverless platform duration limits.

Mitigation:

- reduce `SIMULATION_THROTTLE_RATE`
- lower request bounds
- keep `SIMULATION_RUN_AUDIT_INLINE=false`
- move simulation to async worker architecture

## Incident: Unexpected Model Result

Check:

1. `model_version`.
2. request payload.
3. workbook effective data.
4. fixed seed status.
5. benchmark test output.
6. whether model methodology changed without version bump.

## Error Tracking Integration

Set:

```text
ERROR_TRACKING_DSN=<provider-dsn>
```

The current code exposes integration points and health metadata. A provider adapter should capture unhandled exceptions and include `request_id`, `model_version`, and route path.

## Release Procedure

1. Run backend tests.
2. Run deploy check.
3. Run frontend lint/tests/build.
4. Confirm methodology/version changes.
5. Deploy backend.
6. Smoke test `/health`.
7. Deploy frontend.
8. Smoke test simulation request from browser.
9. Record release evidence in deployment notes.
