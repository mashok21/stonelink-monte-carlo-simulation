import numpy as np

def run_portfolio_simulation(
    initial_portfolio_value=100000,
    years=30,
    annual_contribution=5000,
    annual_contribution_growth=0.03,
    annual_withdrawal=12000,
    withdrawal_start_year=15,
    inflation_rate=0.025,
    allocations=None, # NumPy weight vector corresponding to the assets
    num_trials=1000,
    expected_returns=None,
    volatilities=None,
    correlation_matrix=None,
    target_hurdle=None
):
    # Fallback to standard 4 assets if not provided dynamically
    if expected_returns is None or volatilities is None or correlation_matrix is None:
        expected_returns = np.array([0.090, 0.045, 0.025, 0.065])
        volatilities = np.array([0.160, 0.060, 0.010, 0.090])
        correlation_matrix = np.array([
            [1.0, 0.1, 0.0, 0.4],
            [0.1, 1.0, 0.2, 0.1],
            [0.0, 0.2, 1.0, 0.0],
            [0.4, 0.1, 0.0, 1.0]
        ])
        if allocations is None:
            allocations = np.array([0.60, 0.30, 0.05, 0.05])
    
    num_assets = len(expected_returns)
    
    if allocations is None:
        allocations = np.ones(num_assets) / num_assets
    else:
        allocations = np.array(allocations)
        
    total_weight = np.sum(allocations)
    if total_weight == 0:
        allocations = np.ones(num_assets) / num_assets
    else:
        allocations = allocations / total_weight

    # Ensure correlation matrix is positive semi-definite (PSD)
    eigvals, eigvecs = np.linalg.eigh(correlation_matrix)
    if np.any(eigvals < 0):
        eigvals = np.maximum(eigvals, 1e-8)
        correlation_matrix = eigvecs @ np.diag(eigvals) @ eigvecs.T
        d = np.sqrt(np.diag(correlation_matrix))
        correlation_matrix = correlation_matrix / d[:, None] / d[None, :]

    # Construct Covariance Matrix
    cov_matrix = np.diag(volatilities) @ correlation_matrix @ np.diag(volatilities)
    
    # Generate joint returns
    sim_returns = np.random.multivariate_normal(expected_returns, cov_matrix, size=(num_trials, years))
    
    portfolio_paths = np.zeros((num_trials, years + 1))
    portfolio_paths[:, 0] = initial_portfolio_value
    
    active_mask = np.ones(num_trials, dtype=bool)
    failure_years = np.zeros(num_trials)
    
    for t in range(1, years + 1):
        year_idx = t - 1
        inflation_multiplier = (1.0 + inflation_rate) ** year_idx
        
        # Contribution (at start of the year)
        if t <= withdrawal_start_year:
            contrib = annual_contribution * ((1.0 + annual_contribution_growth) ** year_idx)
        else:
            contrib = 0.0
            
        # Withdrawal (at end of the year, adjusted for inflation)
        if t > withdrawal_start_year:
            withdr = annual_withdrawal * inflation_multiplier
        else:
            withdr = 0.0
            
        prev_vals = portfolio_paths[:, t - 1]
        vals_after_contrib = np.where(active_mask, prev_vals + contrib, 0.0)
        
        # Apply returns based on asset allocation
        returns_t = sim_returns[:, year_idx, :]
        growth_factors = 1.0 + (returns_t @ allocations)
        
        vals_after_growth = vals_after_contrib * growth_factors
        
        # Deduct withdrawals
        final_vals_t = np.where(active_mask, vals_after_growth - withdr, 0.0)
        final_vals_t = np.maximum(final_vals_t, 0.0)
        
        # Update masks
        newly_failed = active_mask & (final_vals_t == 0)
        failure_years[newly_failed] = t
        active_mask = active_mask & (final_vals_t > 0)
        
        portfolio_paths[:, t] = final_vals_t

    # --- AGGREGATION & STATISTICS ---
    # Set default target hurdle for Capital Preservation Goal
    if target_hurdle is None:
        target_hurdle = initial_portfolio_value

    # Compute Nominal Success rates (paths meeting/exceeding nominal target hurdle)
    success_rates_nominal = np.mean(portfolio_paths >= target_hurdle, axis=0) * 100.0
    
    # Calculate inflation-adjusted paths for real spending power
    inflation_factors = (1.0 + inflation_rate) ** np.arange(years + 1)
    real_portfolio_paths = portfolio_paths / inflation_factors
    
    # Compute Real Success rates (paths meeting/exceeding real target hurdle)
    success_rates_real = np.mean(real_portfolio_paths >= target_hurdle, axis=0) * 100.0
    
    percentiles = [10, 25, 50, 75, 90]
    paths_percentiles = {}
    for p in percentiles:
        paths_percentiles[f'p{p}'] = np.percentile(portfolio_paths, p, axis=0)
        
    real_percentiles = {}
    for p in percentiles:
        real_percentiles[f'p{p}'] = np.percentile(real_portfolio_paths, p, axis=0)
        
    terminal_values = portfolio_paths[:, -1]
    
    non_zero_terminal = terminal_values[terminal_values > 0]
    if len(non_zero_terminal) > 0:
        hist, bin_edges = np.histogram(non_zero_terminal, bins=20)
        hist_data = [
            {'bin_start': float(bin_edges[i]), 'bin_end': float(bin_edges[i+1]), 'count': int(hist[i])}
            for i in range(len(hist))
        ]
    else:
        hist_data = []

    beating_inflation = np.mean(real_portfolio_paths[:, -1] > initial_portfolio_value) * 100.0
    
    failed_indices = ~active_mask
    if np.any(failed_indices):
        avg_failure_year = float(np.mean(failure_years[failed_indices]))
    else:
        avg_failure_year = None
        
    return {
        'years_list': list(range(years + 1)),
        'success_rates': success_rates_nominal.tolist(), # Backward compatibility
        'success_rates_nominal': success_rates_nominal.tolist(),
        'success_rates_real': success_rates_real.tolist(),
        'success_rate_terminal': float(success_rates_real[-1]), # Default terminal is real success
        'success_rate_terminal_nominal': float(success_rates_nominal[-1]),
        'success_rate_terminal_real': float(success_rates_real[-1]),
        'beating_inflation_rate': float(beating_inflation),
        'avg_failure_year': avg_failure_year,
        'nominal_paths': {k: v.tolist() for k, v in paths_percentiles.items()},
        'real_paths': {k: v.tolist() for k, v in real_percentiles.items()},
        'histogram': hist_data,
        'summary': {
            'initial_value': initial_portfolio_value,
            'target_hurdle': target_hurdle,
            'median_terminal_nominal': float(paths_percentiles['p50'][-1]),
            'median_terminal_real': float(real_percentiles['p50'][-1]),
            'p10_terminal_nominal': float(paths_percentiles['p10'][-1]),
            'p90_terminal_nominal': float(paths_percentiles['p90'][-1]),
        }
    }
