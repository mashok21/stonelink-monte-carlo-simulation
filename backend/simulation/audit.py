import numpy as np
import datetime
import os
import json
import logging
from .engine import run_portfolio_simulation

logger = logging.getLogger(__name__)

def run_simulation_audit(params, results):
    warnings = []
    test_results = {}
    
    # Helper to run audit scenarios with 200 trials for speed
    def run_scenario(**kwargs):
        sim_params = params.copy()
        # Ensure we have copies of numpy arrays to avoid modifying original parameters
        if 'allocations' in sim_params and sim_params['allocations'] is not None:
            sim_params['allocations'] = np.array(sim_params['allocations'])
        if 'expected_returns' in sim_params and sim_params['expected_returns'] is not None:
            sim_params['expected_returns'] = np.array(sim_params['expected_returns'])
        if 'volatilities' in sim_params and sim_params['volatilities'] is not None:
            sim_params['volatilities'] = np.array(sim_params['volatilities'])
        if 'correlation_matrix' in sim_params and sim_params['correlation_matrix'] is not None:
            sim_params['correlation_matrix'] = np.array(sim_params['correlation_matrix'])
            
        sim_params.update(kwargs)
        sim_params['num_trials'] = 200
        sim_params['use_fixed_seed'] = True
        return run_portfolio_simulation(**sim_params)

    # Extract baseline info
    initial_val = params.get('initial_portfolio_value', 100000)
    inflation = params.get('inflation_rate', 0.03)
    dist_rate = params.get('distribution_rate', 0.04)
    years = params.get('years', 30)
    withdrawal_start_year = params.get('withdrawal_start_year', 15)
    
    base_success_nom = results['success_rate_terminal_nominal']
    base_target_nom = results['summary']['target_value_nominal']
    
    # ----------------------------------------------------
    # AUDIT TEST 1: INFLATION SENSITIVITY
    # ----------------------------------------------------
    test_results['test_1_inflation_sensitivity'] = 'PASS'
    if inflation > 0:
        try:
            scenario_res = run_scenario(inflation_rate=0.0)
            target_zero = scenario_res['summary']['target_value_nominal']
            success_zero = scenario_res['success_rate_terminal_nominal']
            
            # Target must be strictly lower with 0% inflation
            target_decreased = target_zero < base_target_nom
            # Success must be higher or equal with 0% inflation (lower target is easier to meet)
            success_increased_or_equal = success_zero >= base_success_nom - 0.01
            
            if not (target_decreased and success_increased_or_equal):
                test_results['test_1_inflation_sensitivity'] = 'FAIL'
                warnings.append("Inflation input may not be affecting success calculations.")
        except Exception as e:
            test_results['test_1_inflation_sensitivity'] = f'ERROR: {str(e)}'
            warnings.append(f"Audit Test 1 errored: {str(e)}")
            
    # ----------------------------------------------------
    # AUDIT TEST 2: DISTRIBUTION SENSITIVITY
    # ----------------------------------------------------
    test_results['test_2_distribution_sensitivity'] = 'PASS'
    if dist_rate > 0 and years > withdrawal_start_year:
        try:
            # We run both baseline and zero-distribution in terminal_assets mode to isolate assets impact
            base_scenario_res = run_scenario(success_mode='terminal_assets')
            zero_scenario_res = run_scenario(distribution_rate=0.0, success_mode='terminal_assets')
            
            base_succ = base_scenario_res['success_rate_terminal_nominal']
            zero_succ = zero_scenario_res['success_rate_terminal_nominal']
            
            # With zero distributions, success rate must be higher or equal
            if zero_succ < base_succ - 0.01:
                test_results['test_2_distribution_sensitivity'] = 'FAIL'
                warnings.append("Distribution parameter appears disconnected from success calculations.")
            elif abs(zero_succ - base_succ) < 0.1 and 0.1 < base_succ < 99.9:
                test_results['test_2_distribution_sensitivity'] = 'FAIL'
                warnings.append("Distribution parameter appears disconnected from success calculations.")
        except Exception as e:
            test_results['test_2_distribution_sensitivity'] = f'ERROR: {str(e)}'
            warnings.append(f"Audit Test 2 errored: {str(e)}")

    # ----------------------------------------------------
    # AUDIT TEST 3: EXTREME DISTRIBUTION TEST
    # ----------------------------------------------------
    test_results['test_3_extreme_distribution'] = 'PASS'
    try:
        # We run in terminal_assets mode to check that the portfolio assets decline significantly
        base_scenario_res = run_scenario(success_mode='terminal_assets')
        extreme_scenario_res = run_scenario(distribution_rate=0.25, contribution_rate=0.0, success_mode='terminal_assets')
        
        base_succ = base_scenario_res['success_rate_terminal_nominal']
        extreme_succ = extreme_scenario_res['success_rate_terminal_nominal']
        
        # Success should drop significantly under 25% distribution rate
        if extreme_succ >= base_succ - 2.0 and base_succ > 5.0:
            test_results['test_3_extreme_distribution'] = 'FAIL'
            warnings.append("Distribution cash flows may not be applied correctly.")
    except Exception as e:
        test_results['test_3_extreme_distribution'] = f'ERROR: {str(e)}'
        warnings.append(f"Audit Test 3 errored: {str(e)}")

    # ----------------------------------------------------
    # AUDIT TEST 4: EXTREME INFLATION TEST
    # ----------------------------------------------------
    test_results['test_4_extreme_inflation'] = 'PASS'
    try:
        scenario_res = run_scenario(inflation_rate=0.15)
        target_ext = scenario_res['summary']['target_value_nominal']
        success_ext = scenario_res['success_rate_terminal_nominal']
        
        # Target must increase dramatically and success should decrease
        target_increased = target_ext > base_target_nom
        success_decreased = success_ext <= base_success_nom + 0.01
        
        if not target_increased:
            test_results['test_4_extreme_inflation'] = 'FAIL'
            warnings.append("Inflation target adjustment not detected.")
        elif success_ext >= base_success_nom - 2.0 and base_success_nom > 5.0:
            test_results['test_4_extreme_inflation'] = 'FAIL'
            warnings.append("Inflation target adjustment not detected.")
    except Exception as e:
        test_results['test_4_extreme_inflation'] = f'ERROR: {str(e)}'
        warnings.append(f"Audit Test 4 errored: {str(e)}")

    # ----------------------------------------------------
    # AUDIT TEST 5: PROJECTION HORIZON TEST
    # ----------------------------------------------------
    test_results['test_5_projection_horizon'] = 'PASS'
    try:
        horizons = [5, 10, 20, 30]
        targets = []
        successes = []
        for h in horizons:
            res = run_scenario(years=h)
            targets.append(res['summary']['target_value_nominal'])
            successes.append(res['success_rate_terminal_nominal'])
            
        # Target values must increase with horizon (if inflation > 0)
        if inflation > 0:
            targets_ordered = all(targets[i] < targets[i+1] for i in range(len(targets)-1))
            if not targets_ordered:
                test_results['test_5_projection_horizon'] = 'FAIL'
                warnings.append("Projection horizon may not be affecting success calculations.")
                
        # Success rates should not be identical (check variance/std dev)
        if len(set(successes)) == 1 and not (successes[0] == 0.0 or successes[0] == 100.0):
            test_results['test_5_projection_horizon'] = 'FAIL'
            warnings.append("Projection horizon may not be affecting success calculations.")
    except Exception as e:
        test_results['test_5_projection_horizon'] = f'ERROR: {str(e)}'
        warnings.append(f"Audit Test 5 errored: {str(e)}")

    # ----------------------------------------------------
    # AUDIT TEST 6: PATH-LEVEL VALIDATION
    # ----------------------------------------------------
    test_results['test_6_path_level_validation'] = 'PASS'
    try:
        # If success is calculated path-by-path, a scenario where the target hurdle is set
        # exactly to the median TVD of the portfolio should result in a success rate of
        # approximately 50% (since half the paths are above the median and half below).
        # However, if success was derived from the median (e.g., success = 100% if median >= hurdle),
        # then setting the hurdle to the median would result in a binary 100% success rate.
        # We verify that the success probability is not 0% or 100% under this hurdle.
        median_tvd = results['summary']['median_tvd_nominal']
        test_res = run_scenario(target_hurdle=median_tvd, target_mode='custom')
        test_success = test_res['success_rate_terminal_nominal']
        
        if test_success <= 5.0 or test_success >= 95.0:
            test_results['test_6_path_level_validation'] = 'FAIL'
            warnings.append("Success probability appears to be derived from summary statistics rather than path-by-path outcomes.")
    except Exception as e:
        test_results['test_6_path_level_validation'] = f'ERROR: {str(e)}'
        warnings.append(f"Audit Test 6 errored: {str(e)}")

    # ----------------------------------------------------
    # AUDIT TEST 7: ZERO RETURN TEST
    # ----------------------------------------------------
    test_results['test_7_zero_return'] = 'PASS'
    try:
        # Override returns and vols to 0
        n_assets = len(params.get('expected_returns', [0]*4))
        zero_returns = np.zeros(n_assets)
        zero_vols = np.zeros(n_assets)
        
        scenario_res = run_scenario(
            expected_returns=zero_returns,
            volatilities=zero_vols,
            contribution_rate=0.0,
            distribution_rate=0.0,
            inflation_rate=0.0,
        )
        
        # Terminal portfolio value should remain exactly initial value
        term_median = scenario_res['summary']['median_terminal_nominal']
        if abs(term_median - initial_val) > 0.01:
            test_results['test_7_zero_return'] = 'FAIL'
            warnings.append("Deterministic zero-return benchmark test failed.")
            
        # Scenario runs with inflation_rate=0, contribution_rate=0, distribution_rate=0 so
        # target == initial_val and TVD == initial_val → success must be 100%
        s_nom = scenario_res['success_rate_terminal_nominal']
        if s_nom < 99.9:
            test_results['test_7_zero_return'] = 'FAIL'
            warnings.append("Deterministic zero-return benchmark test failed.")
    except Exception as e:
        test_results['test_7_zero_return'] = f'ERROR: {str(e)}'
        warnings.append(f"Audit Test 7 errored: {str(e)}")

    # ----------------------------------------------------
    # AUDIT TEST 8: EXTINCTION TEST
    # ----------------------------------------------------
    test_results['test_8_extinction'] = 'PASS'
    try:
        scenario_res = run_scenario(distribution_rate=1.0, contribution_rate=0.0)
        success_extinction = scenario_res['success_rate_terminal_nominal']
        
        # Portfolio drops to 0 in year 1 and remains solvent-failed. Success must be 0%.
        if success_extinction > 0.01:
            test_results['test_8_extinction'] = 'FAIL'
            warnings.append("Extinction Test failed: depleted portfolio success remains high.")
    except Exception as e:
        test_results['test_8_extinction'] = f'ERROR: {str(e)}'
        warnings.append(f"Audit Test 8 errored: {str(e)}")

    # Determine overall status
    has_failed = any(v == 'FAIL' or v.startswith('ERROR') for v in test_results.values())
    status = 'FAIL' if has_failed else 'PASS'
    
    audit_report = {
        'status': status,
        'warnings': warnings,
        'test_results': test_results,
        'timestamp': datetime.datetime.now().isoformat(),
        'parameters': {
            'initial_value': initial_val,
            'years': years,
            'inflation_rate': inflation,
            'distribution_rate': dist_rate,
            'success_mode': params.get('success_mode', 'total_value'),
            'target_mode': params.get('target_mode', 'default'),
            'min_reserve_threshold_ratio': params.get('min_reserve_threshold_ratio', 0.20),
            'success_framework': params.get('success_framework', 'institutional_sustainability'),
            'enable_hard_liquidation': params.get('enable_hard_liquidation', False)
        }
    }
    
    # ----------------------------------------------------
    # SECTION 6: FILE LOGGING PERSISTENCE
    # ----------------------------------------------------
    try:
        default_log_path = os.path.join('/tmp' if os.environ.get('VERCEL') else os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'simulation_audit.log')
        log_path = os.environ.get('SIMULATION_AUDIT_LOG_PATH', default_log_path)
        
        with open(log_path, 'a', encoding='utf-8') as f:
            log_entry = {
                'timestamp': audit_report['timestamp'],
                'inputs': {
                    'initial_value': initial_val,
                    'years': years,
                    'inflation_rate': inflation,
                    'contribution_rate': params.get('contribution_rate', 0.03),
                    'distribution_rate': dist_rate,
                    'success_mode': params.get('success_mode', 'total_value'),
                    'target_mode': params.get('target_mode', 'default'),
                    'min_reserve_threshold_ratio': params.get('min_reserve_threshold_ratio', 0.20),
                    'success_framework': params.get('success_framework', 'institutional_sustainability'),
                    'enable_hard_liquidation': params.get('enable_hard_liquidation', False)
                },
                'target_value': base_target_nom,
                'success_probability': base_success_nom,
                'status': status,
                'warnings': warnings,
                'details': test_results
            }
            f.write(json.dumps(log_entry) + '\n')
    except Exception as log_ex:
        logger.warning("Failed to write audit log: %s", log_ex)
        
    return audit_report
