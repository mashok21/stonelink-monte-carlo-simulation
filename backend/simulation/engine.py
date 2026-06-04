import numpy as np

def run_portfolio_simulation(
    initial_portfolio_value=100000,
    years=30,
    contribution_rate=0.03,
    distribution_rate=0.04,
    withdrawal_start_year=15,
    inflation_rate=0.025,
    allocations=None, # NumPy weight vector corresponding to the assets
    num_trials=1000,
    expected_returns=None,
    volatilities=None,
    correlation_matrix=None,
    target_hurdle=None,
    environment_mode='STANDARD_CRUISE',
    asset_classes=None,
    unsmoothing_factor=1.4,
    use_fixed_seed=True
):
    seed_value = 42 if use_fixed_seed else None
    rng = np.random.default_rng(seed_value)
    
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
        if asset_classes is None:
            asset_classes = ['equity', 'fixed_income', 'fixed_income', 'equity']
            
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

    # --- VOLATILITY UNSMOOTHING FOR PRIVATE ASSETS ---
    vols_adjusted = volatilities.copy()
    if asset_classes is not None:
        for i, ac in enumerate(asset_classes):
            if ac == 'private':
                vols_adjusted[i] *= unsmoothing_factor

    # Ensure correlation matrix is positive semi-definite (PSD)
    eigvals, eigvecs = np.linalg.eigh(correlation_matrix)
    if np.any(eigvals < 0):
        eigvals = np.maximum(eigvals, 1e-8)
        correlation_matrix = eigvecs @ np.diag(eigvals) @ eigvecs.T
        d = np.sqrt(np.diag(correlation_matrix))
        correlation_matrix = correlation_matrix / d[:, None] / d[None, :]

    # Compute Cholesky decomposition factor L (where L @ L.T = Correlation Matrix)
    # This factor is used to inject correlation into independent random draws.
    L = np.linalg.cholesky(correlation_matrix)
    
    # Generate joint returns based on simulation environment mode
    # Draw independent standard normal random variables
    Z = rng.normal(0, 1, size=(num_trials, years, num_assets))
    
    # Transform independent standard normals to correlated standard normals
    # X_ij = sum_k Z_ik * L_jk
    # We flatten Z to (num_trials * years, num_assets) for fast matrix multiplication
    Z_flat = Z.reshape(-1, num_assets)
    X_flat = Z_flat @ L.T
    X = X_flat.reshape(num_trials, years, num_assets)
    
    # Apply distribution branching logic based on the environment mode
    if environment_mode == 'MARKET_STRESS':
        # Apply Multivariate Student-t Distribution (df=4) to Liquid Equities
        # Generate independent Chi-Squared random variables: W ~ Chi2(df=4)
        W = rng.chisquare(df=4, size=(num_trials, years, 1))
        # Protect against division by zero
        W = np.maximum(W, 1e-6)
        scale_factors = np.sqrt(W / 4.0) # shape: (num_trials, years, 1)
        
        # Branching per asset: equities divide by scale factor (Student-t),
        # bonds and private assets remain normal.
        for j in range(num_assets):
            a_class = asset_classes[j] if (asset_classes is not None and j < len(asset_classes)) else 'equity'
            if a_class == 'equity':
                X[:, :, j] = X[:, :, j] / scale_factors[:, :, 0]
                # Inject a slight downward shift/drift during Stress Test to simulate a market crash
                # Let's subtract a small crash premium of 2.0% pa to stress test the portfolios
                X[:, :, j] -= 0.02

    # Scale to expected returns and adjusted volatilities
    sim_returns = expected_returns + X * vols_adjusted
    
    # Matrix to store portfolio values over time (years 0 to years)
    # Shape: (num_trials, years + 1)
    portfolio_paths = np.zeros((num_trials, years + 1))
    portfolio_paths[:, 0] = initial_portfolio_value
    
    active_mask = np.ones(num_trials, dtype=bool)
    failure_years = np.zeros(num_trials)
    
    for t in range(1, years + 1):
        year_idx = t - 1
        
        prev_vals = portfolio_paths[:, t - 1]
        
        # Apply returns based on asset allocation to calculate pre-cash-flow year-end values
        returns_t = sim_returns[:, year_idx, :]
        growth_factors = 1.0 + (returns_t @ allocations)
        vals_pre_cash_flow = np.where(active_mask, prev_vals * growth_factors, 0.0)
        
        # Calculate contributions (only if t <= withdrawal_start_year)
        if t <= withdrawal_start_year:
            contrib = contribution_rate * vals_pre_cash_flow
        else:
            contrib = 0.0
            
        # Calculate distributions (only if t > withdrawal_start_year)
        if t > withdrawal_start_year:
            distrib = distribution_rate * vals_pre_cash_flow
        else:
            distrib = 0.0
            
        # Update ending assets
        final_vals_t = np.where(active_mask, vals_pre_cash_flow + contrib - distrib, 0.0)
        final_vals_t = np.maximum(final_vals_t, 0.0)
        
        # Update masks
        newly_failed = active_mask & (final_vals_t == 0)
        failure_years[newly_failed] = t
        active_mask = active_mask & (final_vals_t > 0)
        
        portfolio_paths[:, t] = final_vals_t

    # --- AGGREGATION & STATISTICS ---
    if target_hurdle is None:
        target_hurdle = initial_portfolio_value

    # Compute Nominal Success rates
    success_rates_nominal = np.mean(portfolio_paths >= target_hurdle, axis=0) * 100.0
    
    # Calculate inflation-adjusted paths for real spending power
    inflation_factors = (1.0 + inflation_rate) ** np.arange(years + 1)
    real_portfolio_paths = portfolio_paths / inflation_factors
    
    # Compute Real Success rates
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
        'success_rates': success_rates_nominal.tolist(),
        'success_rates_nominal': success_rates_nominal.tolist(),
        'success_rates_real': success_rates_real.tolist(),
        'success_rate_terminal': float(success_rates_real[-1]),
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
