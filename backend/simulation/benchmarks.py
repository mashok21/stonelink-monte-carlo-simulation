import numpy as np


TWO_ASSET_GOLDEN_CASE = {
    "name": "deterministic_two_asset_institutional_sustainability",
    "description": "Small fixed-seed two-asset case used to detect numerical drift.",
    "params": {
        "initial_portfolio_value": 100000,
        "years": 3,
        "contribution_rate": 0.02,
        "distribution_rate": 0.03,
        "withdrawal_start_year": 1,
        "inflation_rate": 0.02,
        "allocations": np.array([0.6, 0.4]),
        "num_trials": 100,
        "expected_returns": np.array([0.07, 0.03]),
        "volatilities": np.array([0.12, 0.04]),
        "correlation_matrix": np.array([[1.0, 0.2], [0.2, 1.0]]),
        "use_fixed_seed": True,
        "success_framework": "institutional_sustainability",
        "min_reserve_threshold_ratio": 0.2,
    },
    "expected": {
        "median_terminal_nominal": 111408.53944820625,
        "median_tvd_nominal": 118310.16488327438,
        "success_rate_terminal_nominal": 83.0,
        "prob_reserve_breach": 0.0,
    },
}


BENCHMARK_PORTFOLIOS = {
    "capital_preservation": {
        "description": "Low-risk preservation benchmark for solvency sensitivity.",
        "allocations": np.array([0.2, 0.8]),
        "expected_returns": np.array([0.055, 0.03]),
        "volatilities": np.array([0.10, 0.035]),
        "correlation_matrix": np.array([[1.0, 0.15], [0.15, 1.0]]),
    },
    "balanced_growth": {
        "description": "Balanced benchmark for investor-demo regression comparisons.",
        "allocations": np.array([0.6, 0.4]),
        "expected_returns": np.array([0.07, 0.03]),
        "volatilities": np.array([0.12, 0.04]),
        "correlation_matrix": np.array([[1.0, 0.2], [0.2, 1.0]]),
    },
    "stress_sensitive_growth": {
        "description": "Higher-volatility benchmark used to verify stress-mode behavior.",
        "allocations": np.array([0.85, 0.15]),
        "expected_returns": np.array([0.085, 0.025]),
        "volatilities": np.array([0.18, 0.035]),
        "correlation_matrix": np.array([[1.0, 0.1], [0.1, 1.0]]),
    },
}
