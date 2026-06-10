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
    target_mode = params.get('target_mode', 'default')
    target_hurdle = params.get('target_hurdle')
    
    # Run a matched 200-trial baseline to eliminate random trial-size/seed noise
    base_res_200 = run_scenario()
    base_success_nom = base_res_200['success_rate_terminal_nominal']
    base_success_real = base_res_200['success_rate_terminal_real']
    base_target_nom = base_res_200['summary']['target_value_nominal']
    base_target_real = base_res_200['summary']['target_value_real']
    
    # ----------------------------------------------------
    # AUDIT TEST 1: INFLATION SENSITIVITY
    # ----------------------------------------------------
    test_results['test_1_inflation_sensitivity'] = 'PASS'
    if inflation > 0:
        try:
            scenario_res = run_scenario(inflation_rate=0.0)
            
            if target_mode == 'custom':
                success_zero_real = scenario_res['success_rate_terminal_real']
                success_increased_or_equal = success_zero_real >= base_success_real - 0.0001
                if not success_increased_or_equal:
                    test_results['test_1_inflation_sensitivity'] = 'FAIL'
                    warnings.append("Inflation input may not be affecting success calculations.")
            else:
                target_zero = scenario_res['summary']['target_value_nominal']
                success_zero = scenario_res['success_rate_terminal_nominal']
                target_decreased = target_zero < base_target_nom
                success_increased_or_equal = success_zero >= base_success_nom - 0.0001
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
            # We run both baseline and zero-distribution in terminal_assets mode to isolate assets impact.
            # Pin to STANDARD_CRUISE, default target mode, and terminal_assets framework to avoid stress mode volatility and custom hurdles.
            base_scenario_res = run_scenario(
                environment_mode='STANDARD_CRUISE',
                target_mode='default',
                success_framework='terminal_assets',
                success_mode='terminal_assets'
            )
            zero_scenario_res = run_scenario(
                distribution_rate=0.0,
                environment_mode='STANDARD_CRUISE',
                target_mode='default',
                success_framework='terminal_assets',
                success_mode='terminal_assets'
            )
            
            base_succ = base_scenario_res['success_rate_terminal_nominal']
            zero_succ = zero_scenario_res['success_rate_terminal_nominal']
            
            # With zero distributions, success rate must be higher or equal
            if zero_succ < base_succ - 0.0001:
                test_results['test_2_distribution_sensitivity'] = 'FAIL'
                warnings.append("Distribution parameter appears disconnected from success calculations.")
            elif abs(zero_succ - base_succ) < 0.0001 and 0.1 < base_succ < 99.9:
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
        if dist_rate >= 0.25:
            base_scenario_res = run_scenario(distribution_rate=0.04, success_mode='terminal_assets')
            extreme_scenario_res = run_scenario(contribution_rate=0.0, success_mode='terminal_assets')
        else:
            base_scenario_res = run_scenario(success_mode='terminal_assets')
            extreme_scenario_res = run_scenario(distribution_rate=0.25, contribution_rate=0.0, success_mode='terminal_assets')
            
        base_succ = base_scenario_res['success_rate_terminal_nominal']
        extreme_succ = extreme_scenario_res['success_rate_terminal_nominal']
        
        # Success should drop significantly under extreme distribution rate
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
        if inflation >= 0.15:
            standard_res = run_scenario(inflation_rate=0.03)
            extreme_res = base_res_200
        else:
            standard_res = base_res_200
            extreme_res = run_scenario(inflation_rate=0.15)
            
        if target_mode == 'custom':
            ext_success = extreme_res['success_rate_terminal_real']
            std_success = standard_res['success_rate_terminal_real']
            
            success_decreased_or_equal = ext_success <= std_success + 0.0001
            success_dropped_if_possible = True
            if std_success > 5.0:
                success_dropped_if_possible = ext_success < std_success - 2.0
                
            if not (success_decreased_or_equal and success_dropped_if_possible):
                test_results['test_4_extreme_inflation'] = 'FAIL'
                warnings.append("Inflation target adjustment not detected.")
        else:
            ext_target = extreme_res['summary']['target_value_nominal']
            std_target = standard_res['summary']['target_value_nominal']
            ext_success = extreme_res['success_rate_terminal_nominal']
            std_success = standard_res['success_rate_terminal_nominal']
            
            target_increased = ext_target > std_target
            success_decreased_or_equal = ext_success <= std_success + 0.0001
            success_dropped_if_possible = True
            if std_success > 5.0:
                success_dropped_if_possible = ext_success < std_success - 2.0
                
            if not target_increased or not (success_decreased_or_equal and success_dropped_if_possible):
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
            
        # Target values must increase with horizon (if inflation > 0 and not custom mode)
        if inflation > 0 and target_mode != 'custom':
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
        # Isolate path-level validation from solvency and cash flow depletion
        base_test_res = run_scenario(
            distribution_rate=0.0,
            contribution_rate=0.0,
            min_reserve_threshold_ratio=0.0,
            success_framework='terminal_assets'
        )
        median_tvd = base_test_res['summary']['median_tvd_nominal']
        test_res = run_scenario(
            target_hurdle=median_tvd,
            target_mode='custom',
            distribution_rate=0.0,
            contribution_rate=0.0,
            min_reserve_threshold_ratio=0.0,
            success_framework='terminal_assets'
        )
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
        
        # Pin environment_mode to STANDARD_CRUISE so that the stress/crash drag is not applied
        scenario_res = run_scenario(
            expected_returns=zero_returns,
            volatilities=zero_vols,
            contribution_rate=0.0,
            distribution_rate=0.0,
            environment_mode='STANDARD_CRUISE'
        )
        
        # Terminal portfolio value should remain exactly initial value
        term_median = scenario_res['summary']['median_terminal_nominal']
        if abs(term_median - initial_val) > 0.01:
            test_results['test_7_zero_return'] = 'FAIL'
            warnings.append("Deterministic zero-return benchmark test failed.")
            
        s_nom = scenario_res['success_rate_terminal_nominal']
        
        if target_mode == 'custom':
            hurdle = target_hurdle if target_hurdle is not None else initial_val
            if hurdle > initial_val:
                if s_nom > 0.01:
                    test_results['test_7_zero_return'] = 'FAIL'
                    warnings.append("Deterministic zero-return benchmark test failed.")
            else:
                if s_nom < 99.9:
                    test_results['test_7_zero_return'] = 'FAIL'
                    warnings.append("Deterministic zero-return benchmark test failed.")
        else:
            t_nom = scenario_res['summary']['target_value_nominal']
            if inflation > 0 and abs(t_nom - initial_val) > 0.01:
                # target should be greater than initial value
                if s_nom > 0.01: # Success must be 0% since TVD (initial_val) < Target
                    test_results['test_7_zero_return'] = 'FAIL'
                    warnings.append("Deterministic zero-return benchmark test failed.")
            elif inflation == 0:
                if s_nom < 99.9: # Success must be 100% since TVD (initial_val) == Target
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
        _on_cloud = os.environ.get('VERCEL') or os.environ.get('RAILWAY_ENVIRONMENT')
        default_log_path = os.path.join('/tmp' if _on_cloud else os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'simulation_audit.log')
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
