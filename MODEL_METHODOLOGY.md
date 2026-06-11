# StoneLink Model Methodology

Model version: `2026.06.09-v1`

This document describes the current StoneLink Monte Carlo Sustainability Model. It is intended for investor, operator, and reviewer diligence. The model is an educational analytical engine, not financial, investment, tax, legal, or fiduciary advice.

## Scope

The model estimates portfolio sustainability across stochastic annual return paths. It supports contributions, distributions, inflation adjustment, reserve thresholds, portfolio allocation presets, stress-mode return behavior, and multiple success definitions.

## Inputs

Primary request inputs:

- `initial_portfolio_value`: starting asset value.
- `years`: projection horizon in annual steps.
- `contribution_rate`: annual contribution percentage applied before withdrawal commencement.
- `distribution_rate`: annual distribution percentage applied after withdrawal commencement.
- `withdrawal_start_year`: first year after which distributions begin.
- `inflation_rate`: annual inflation assumption.
- `num_trials`: Monte Carlo path count.
- `portfolio_type`: allocation preset from the workbook.
- `environment_mode`: `STANDARD_CRUISE` or `MARKET_STRESS`.
- `target_mode`: `default` or `custom`.
- `target_hurdle`: custom success hurdle when `target_mode=custom`.
- `min_reserve_threshold_ratio`: reserve floor as a percentage of initial assets.
- `success_framework`: success definition.
- `enable_hard_liquidation`: whether paths are absorbed when reserve threshold is breached.
- `use_fixed_seed`: reproducibility toggle.

## Portfolio Data

Portfolio assumptions are loaded from `backend/simulation/portfolio_data.xlsx` through `simulation.ingestion`.

The workbook provides:

- asset names
- expected annual returns
- annual volatility assumptions
- correlation matrix
- asset categories/classes
- portfolio allocation presets
- private asset unsmoothing factor

The ingestion layer caches parsed workbook data by file modification time and returns defensive copies to protect the cached arrays from mutation.

## Return Generation

For each trial `i`, year `t`, and asset `j`, independent standard normal draws are generated:

```text
Z[i,t,j] ~ N(0, 1)
```

The input correlation matrix is repaired if it has negative eigenvalues. Correlated draws are produced with Cholesky factor `L`:

```text
X[i,t,:] = Z[i,t,:] * transpose(L)
```

Asset returns are then:

```text
R[i,t,j] = expected_return[j] + X[i,t,j] * adjusted_volatility[j]
```

Portfolio return for each path/year:

```text
portfolio_return[i,t] = dot(R[i,t,:], normalized_allocations)
```

## Private Asset Unsmoothing

Assets classified as `private` have volatility multiplied by the workbook unsmoothing factor:

```text
adjusted_volatility[j] = volatility[j] * unsmoothing_factor
```

This approximates the effect of stale/smoothed private-asset marks.

## Stress Modes

### STANDARD_CRUISE

Uses correlated normal draws with expected returns and adjusted volatilities.

### MARKET_STRESS

In MARKET_STRESS mode, assets classified as equity by the backend receive Student-t shocks with 4 degrees of freedom. A flat -2.0% annual crash-drag adjustment is then applied to the simulated return for those equity-classified assets.

Fixed income and private assets remain normal in the current implementation.

## Cash Flow Logic

At each year:

```text
pre_cash_value = previous_value * (1 + portfolio_return)
```

Before or at `withdrawal_start_year`:

```text
contribution = contribution_rate * pre_cash_value
distribution = 0
```

After `withdrawal_start_year`:

```text
contribution = 0
distribution = distribution_rate * pre_cash_value
```

Ending value:

```text
ending_value = max(pre_cash_value + contribution - distribution, 0)
```

Cumulative distributions are tracked in nominal and real terms.

## Real Value Adjustment

Inflation factor at year `t`:

```text
inflation_factor[t] = (1 + inflation_rate) ^ t
```

Real portfolio value:

```text
real_value[t] = nominal_value[t] / inflation_factor[t]
```

Real distributions:

```text
real_distribution[t] = nominal_distribution[t] / inflation_factor[t]
```

## Success Criteria

The model computes path-level success, not success from aggregate medians.

### terminal_assets

Success metric:

```text
TVD = terminal_assets
solvent = terminal_assets > 0
success = solvent AND TVD >= target
```

### total_value

Success metric:

```text
TVD = terminal_assets + cumulative_distributions
solvent = terminal_assets > 0
success = solvent AND TVD >= target
```

### institutional_sustainability

Success metric:

```text
TVD = terminal_assets + cumulative_distributions
reserve_floor = min_reserve_threshold_ratio * initial_assets
solvent = terminal_assets >= reserve_floor
success = solvent AND TVD >= target
```

### continuous_solvency

Success metric:

```text
running_min = min(portfolio_value[1..t])
solvent = running_min >= reserve_floor
success = solvent AND TVD >= target
```

## Targets

Default nominal target:

```text
target_nominal[t] = initial_assets * (1 + inflation_rate) ^ t
```

Default real target:

```text
target_real[t] = initial_assets
```

Custom target:

```text
target_nominal = target_hurdle
target_real = target_hurdle
```

## Model Outputs

Simulation responses include:

- percentile paths: P10, P25, P50, P75, P90
- nominal and real success rates by year
- terminal success rates
- terminal-value histogram
- reserve breach probability
- median first breach year
- median minimum assets
- asset metadata and correlation matrix
- audit report status
- model metadata and disclaimer
- request ID
- runtime metrics

## Model Versioning

The API exposes `model_version` on:

- every simulation response
- every health response
- response metadata

Current model version: `2026.06.09-v1`

Version increments are required when formulas, success criteria, stress behavior, asset data interpretation, random process behavior, or material output semantics change.

## Limitations

- Expected returns, volatility, and correlations are assumptions, not forecasts.
- The model uses annual steps and does not model intra-year path behavior.
- Stress mode is scenario-style, not calibrated to a specific historical crisis.
- Taxes, fees, liquidity gates, transaction costs, manager risk, and jurisdiction-specific constraints are excluded.
- Correlation and volatility assumptions may break down in extreme markets.
- Private asset unsmoothing is approximate.
- Results are sensitive to the input workbook and should not be interpreted without assumption review.

## Validation Approach

Validation uses:

- deterministic fixed-seed golden tests
- API contract tests
- schema/version checks
- zero-return/extinction edge cases
- stress-mode smoke tests
- path-level success validation
- regression benchmark definitions in `backend/simulation/benchmarks.py`

See `VALIDATION_FRAMEWORK.md` for the regression governance process.
