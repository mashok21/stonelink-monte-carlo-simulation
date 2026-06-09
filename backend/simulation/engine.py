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
    use_fixed_seed=True,
    target_mode='default',
    min_reserve_threshold_ratio=0.20,
    success_framework='institutional_sustainability',
    enable_hard_liquidation=False,
    # Old params for backward compatibility
    success_mode=None,
    solvency_policy=None
):
    # Backward compatibility translation
    if success_mode is not None or solvency_policy is not None:
        if solvency_policy == 'absorbing_barrier':
            enable_hard_liquidation = True
            success_framework = 'institutional_sustainability'
        elif solvency_policy == 'continuous_first_passage':
            enable_hard_liquidation = False
            success_framework = 'continuous_solvency'
        else: # terminal_only
            enable_hard_liquidation = False
            if success_mode == 'terminal_assets':
                success_framework = 'terminal_assets'
            else:
                success_framework = 'institutional_sustainability'
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
    try:
        L = np.linalg.cholesky(correlation_matrix)
    except np.linalg.LinAlgError:
        jitter = np.eye(correlation_matrix.shape[0]) * 1e-8
        L = np.linalg.cholesky(correlation_matrix + jitter)
    
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

    # Scale to expected returns and adjusted volatilities
    sim_returns = expected_returns + X * vols_adjusted

    # Apply flat 2% pa crash drag to equity returns in stress mode (post-scaling so drag is vol-independent)
    if environment_mode == 'MARKET_STRESS':
        for j in range(num_assets):
            a_class = asset_classes[j] if (asset_classes is not None and j < len(asset_classes)) else 'equity'
            if a_class == 'equity':
                sim_returns[:, :, j] -= 0.02
    
    # Matrix to store portfolio values over time (years 0 to years)
    # Shape: (num_trials, years + 1)
    portfolio_paths = np.zeros((num_trials, years + 1))
    portfolio_paths[:, 0] = initial_portfolio_value
    
    cumulative_distributions_nominal = np.zeros((num_trials, years + 1))
    cumulative_distributions_real = np.zeros((num_trials, years + 1))
    
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
            distrib = np.where(active_mask, distribution_rate * vals_pre_cash_flow, 0.0)
        else:
            distrib = np.zeros(num_trials)
            
        cumulative_distributions_nominal[:, t] = cumulative_distributions_nominal[:, t - 1] + distrib
        cumulative_distributions_real[:, t] = cumulative_distributions_real[:, t - 1] + (distrib / ((1.0 + inflation_rate) ** t))
            
        # Update ending assets
        final_vals_t = np.where(active_mask, vals_pre_cash_flow + contrib - distrib, 0.0)
        final_vals_t = np.maximum(final_vals_t, 0.0)
        
        # Update masks based on solvency policy (Layer 1 check)
        min_reserve_val = min_reserve_threshold_ratio * initial_portfolio_value
        if not enable_hard_liquidation or min_reserve_val <= 0:
            newly_failed = active_mask & (final_vals_t <= 0)
            active_mask = active_mask & (final_vals_t > 0)
        else: # Hard Liquidation enabled
            newly_failed = active_mask & (final_vals_t < min_reserve_val)
            active_mask = active_mask & (final_vals_t >= min_reserve_val)

        failure_years[newly_failed] = t
            
        # Zero out values for failed paths to avoid further growth or distributions
        final_vals_t = np.where(active_mask, final_vals_t, 0.0)
        portfolio_paths[:, t] = final_vals_t

    # --- AGGREGATION & STATISTICS ---
    if target_hurdle is None:
        target_hurdle = initial_portfolio_value

    # Calculate inflation-adjusted paths for real spending power
    inflation_factors = (1.0 + inflation_rate) ** np.arange(years + 1)
    real_portfolio_paths = portfolio_paths / inflation_factors

    # Compute success rates over time
    success_rates_nominal = np.zeros(years + 1)
    success_rates_real = np.zeros(years + 1)
    
    # Year 0 is 100% successful
    success_rates_nominal[0] = 100.0
    success_rates_real[0] = 100.0
    
    custom_target = target_hurdle
    
    min_reserve_val = min_reserve_threshold_ratio * initial_portfolio_value
    
    # Calculate running minimums for continuous solvency checks (Layer 2)
    if success_framework == 'continuous_solvency' and min_reserve_val > 0:
        running_min_nom = np.minimum.accumulate(portfolio_paths[:, 1:], axis=1)
        running_min_real = np.minimum.accumulate(real_portfolio_paths[:, 1:], axis=1)
        
    for t in range(1, years + 1):
        year_idx = t - 1
        
        # 1. Define solvency (Layer 2)
        if min_reserve_val <= 0:
            solvent_nom = portfolio_paths[:, t] > 0
            solvent_real = real_portfolio_paths[:, t] > 0
        elif success_framework == 'terminal_assets' or success_framework == 'total_value':
            solvent_nom = portfolio_paths[:, t] > 0
            solvent_real = real_portfolio_paths[:, t] > 0
        elif success_framework == 'continuous_solvency':
            solvent_nom = running_min_nom[:, year_idx] >= min_reserve_val
            solvent_real = running_min_real[:, year_idx] >= min_reserve_val
        else: # institutional_sustainability
            solvent_nom = portfolio_paths[:, t] >= min_reserve_val
            solvent_real = real_portfolio_paths[:, t] >= min_reserve_val
            
        # 2. Define TVD (Layer 2 / 3)
        if success_framework == 'terminal_assets':
            tvd_nom = portfolio_paths[:, t]
            tvd_real = real_portfolio_paths[:, t]
        else:
            tvd_nom = portfolio_paths[:, t] + cumulative_distributions_nominal[:, t]
            tvd_real = real_portfolio_paths[:, t] + cumulative_distributions_real[:, t]
            
        # 3. Define target hurdle (Layer 3)
        # Nominal target
        if target_mode == 'custom':
            target_nom = custom_target
        else:
            target_nom = initial_portfolio_value * ((1.0 + inflation_rate) ** t)
            
        # Real target
        if target_mode == 'custom':
            target_real = custom_target
        else:
            target_real = initial_portfolio_value
            
        success_nom_t = solvent_nom & (tvd_nom >= target_nom)
        success_real_t = solvent_real & (tvd_real >= target_real)
        
        success_rates_nominal[t] = np.mean(success_nom_t) * 100.0
        success_rates_real[t] = np.mean(success_real_t) * 100.0
    
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
        
    tvd_nominal_paths = portfolio_paths + cumulative_distributions_nominal
    tvd_real_paths = real_portfolio_paths + cumulative_distributions_real
    
    # Layer 2 Diagnostics
    # 1. Probability of Reserve Breach
    # 2. Median First Breach Year
    # 3. Median Minimum Asset Value
    # 4. Percentage of paths below threshold (at terminal year)
    
    if min_reserve_val > 0.0:
        breached_matrix = portfolio_paths[:, 1:] < min_reserve_val
        below_threshold_terminal = portfolio_paths[:, -1] < min_reserve_val
    else:
        breached_matrix = portfolio_paths[:, 1:] <= 0.0
        below_threshold_terminal = portfolio_paths[:, -1] <= 0.0
        
    any_breached = np.any(breached_matrix, axis=1)
    prob_reserve_breach = float(np.mean(any_breached) * 100.0)
    pct_paths_below_threshold = float(np.mean(below_threshold_terminal) * 100.0)
    
    first_breach_years = np.argmax(breached_matrix, axis=1) + 1
    first_breach_years_breached = first_breach_years[any_breached]
    if len(first_breach_years_breached) > 0:
        median_first_breach_year = float(np.median(first_breach_years_breached))
    else:
        median_first_breach_year = None
        
    min_assets_per_path = np.min(portfolio_paths, axis=1)
    median_minimum_assets = float(np.median(min_assets_per_path))
    
    terminal_nominal_target = custom_target if target_mode == 'custom' else initial_portfolio_value * ((1.0 + inflation_rate) ** years)
    terminal_real_target = custom_target if target_mode == 'custom' else initial_portfolio_value

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
        'prob_reserve_breach': prob_reserve_breach,
        'median_first_breach_year': median_first_breach_year,
        'median_minimum_assets': median_minimum_assets,
        'pct_paths_below_threshold': pct_paths_below_threshold,
        'summary': {
            'initial_value': initial_portfolio_value,
            'target_hurdle': target_hurdle,
            'success_mode': success_mode,
            'target_mode': target_mode,
            'min_reserve_threshold_ratio': min_reserve_threshold_ratio,
            'success_framework': success_framework,
            'enable_hard_liquidation': enable_hard_liquidation,
            'median_terminal_nominal': float(paths_percentiles['p50'][-1]),
            'median_terminal_real': float(real_percentiles['p50'][-1]),
            'p10_terminal_nominal': float(paths_percentiles['p10'][-1]),
            'p90_terminal_nominal': float(paths_percentiles['p90'][-1]),
            'median_distributions_nominal': float(np.percentile(cumulative_distributions_nominal[:, -1], 50)),
            'median_distributions_real': float(np.percentile(cumulative_distributions_real[:, -1], 50)),
            'median_tvd_nominal': float(np.percentile(tvd_nominal_paths[:, -1], 50)),
            'median_tvd_real': float(np.percentile(tvd_real_paths[:, -1], 50)),
            'target_value_nominal': float(terminal_nominal_target),
            'target_value_real': float(terminal_real_target),
            'prob_reserve_breach': prob_reserve_breach,
            'median_first_breach_year': median_first_breach_year,
            'median_minimum_assets': median_minimum_assets,
            'pct_paths_below_threshold': pct_paths_below_threshold
        }
    }
