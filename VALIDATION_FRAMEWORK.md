# Validation Framework

Model version: `2026.06.09-v1`

## Purpose

The validation framework exists to detect accidental changes in simulation behavior, response contracts, and reproducibility. It is not a guarantee of financial accuracy.

## Golden Numerical Tests

Golden tests use fixed seed inputs and exact expected summary values. The canonical case is defined in:

```text
backend/simulation/benchmarks.py
```

The current golden case is:

```text
deterministic_two_asset_institutional_sustainability
```

Locked metrics:

- median terminal nominal assets
- median total value delivered nominal
- terminal nominal success rate
- reserve breach probability

These values should only change when the model version changes and the change is documented in `MODEL_METHODOLOGY.md`.

## Benchmark Portfolios

Benchmark portfolio definitions:

- `capital_preservation`
- `balanced_growth`
- `stress_sensitive_growth`

These are implementation-ready regression fixtures for future benchmark reports and CI snapshots.

## Regression Test Categories

Required categories:

- request validation and bounds
- fixed-seed reproducibility
- random-seed variance
- non-PSD correlation repair
- path-level success probability
- zero-return deterministic benchmark
- extinction/depletion benchmark
- stress-mode execution
- API response contract
- model metadata presence
- request ID header presence
- health endpoint observability contract

## Test Commands

```powershell
python backend\manage.py test simulation
```

For production security configuration:

```powershell
$env:DJANGO_DEBUG='false'
$env:DJANGO_SECRET_KEY='replace-with-a-long-random-secret'
python backend\manage.py check --deploy
```

## Reproducibility Rules

- Use `use_fixed_seed=true` for regression and investor demo reproducibility.
- Fixed-seed simulations use NumPy `default_rng(42)`.
- Any change to RNG, distribution, path order, cash-flow timing, or success definitions requires a model version bump.
- Any workbook update used in production should record source, reviewer, and effective date.

## Acceptance Criteria

A model change is acceptable only when:

- tests pass
- golden value changes are intentional and documented
- methodology docs are updated
- model version is incremented for material behavior changes
- response schema changes are reflected in frontend compatibility checks
- deployment checks pass

## Current Gaps

- No automated benchmark report artifact is generated in CI yet.
- No independent third-party validation exists.
- No historical backtest calibration report exists.
- No signed data provenance record exists for workbook inputs.
