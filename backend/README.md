# Stonelink Portfolio Risk Monitor Backend Deployment Reference

This document serves as the canonical reference for the production backend deployment of the Stonelink Portfolio Risk Monitor.

---

## 1. Production Backend Platform & URL

* **Platform**: Railway is the current production hosting platform.
* **Base URL**: 
  ```text
  https://stonelink-monte-carlo-simulation-production.up.railway.app/
  ```

---

## 2. API Endpoints

The backend exposes the following endpoints:

* **Health Handshake**:
  * **Endpoint**: `GET /health`
  * **Description**: Verifies API availability, active schema compatibility version, and backend version/build timestamps.
* **Portfolio Simulation Engine**:
  * **Endpoint**: `POST /simulation/`
  * **Description**: Accepts simulation parameters (allocation, distributions, solvency ratios) and returns paths, downside scenarios, and diagnostic metrics.

---

## 3. Integration & Network Architecture

* **Frontend Client Host**: The frontend dashboard is hosted on Vercel and initiates CORS-compliant API requests to the Railway backend URL listed above.
* **CORS Policy**: Active CORS headers permit cross-origin requests from the verified production Vercel frontend.
* **Canonical Workbook Storage**:
  * The backend loads its underlying capital market assumptions and strategic allocations directly from the Git-tracked workbook:
    ```text
    backend/simulation/portfolio_data.xlsx
    ```
  * The production runtime uses the version of `portfolio_data.xlsx` compiled and bundled with the active Git deployment package. This workbook is the single source of truth for the asset model parameters unless the database architecture is formally modified in the future.

---

## 4. Environment & Project Guardrails

To prevent regressions, the following project configurations must remain unchanged unless explicitly authorized by an approved deployment task:
* Environment variables and secrets.
* Railway project and build settings.
* Deployment configuration files (e.g., buildpacks, start commands).
* Python package requirements and library dependencies.

---

## 5. Post-Deployment Verification Checklist

Whenever changes are deployed to the backend, verify the deployment using the following checks:

1. **Verify Health Endpoint**:
   `GET https://stonelink-monte-carlo-simulation-production.up.railway.app/health` returns HTTP 200 with schema and version metadata.
2. **Verify Simulation Endpoint**:
   `POST https://stonelink-monte-carlo-simulation-production.up.railway.app/simulation/` accepts parameter payloads and successfully returns simulation results.
3. **Verify Frontend Run**:
   Perform a manual scenario run on the production Vercel frontend to confirm successful end-to-end simulation.
4. **CORS Validation**:
   Inspect the browser developer console during the manual scenario run to confirm there are no CORS or origin blockages.

## 6. Workbook Metadata Exposure

The `/health` endpoint exposes read-only metadata about the active workbook configuration. This payload includes:

```json
{
  "portfolio_workbook": {
    "filename": "portfolio_data.xlsx",
    "relative_path": "simulation/portfolio_data.xlsx",
    "sha256": "...",
    "size_bytes": 29289,
    "last_modified_utc": "...",
    "available": true
  }
}
```

This read-only metadata assists in confirming the specific workbook file version being utilized by the deployed backend. It does not validate investment assumptions, and does not represent independent model validation.

