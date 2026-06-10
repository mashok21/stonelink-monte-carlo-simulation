from django.core.cache import cache
from django.test import TestCase, Client
from django.urls import reverse
import numpy as np
import os
from unittest.mock import patch

from . import ingestion
from .benchmarks import TWO_ASSET_GOLDEN_CASE
from .ingestion import parse_portfolio_excel, get_excel_path, clear_portfolio_excel_cache
from .engine import run_portfolio_simulation
from .model_metadata import MODEL_VERSION

class PortfolioSimulationTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.url = reverse('simulate')
        
    def test_excel_parser(self):
        """Test that the Excel parser reads asset parameters, weights, and correlation matrix correctly."""
        # Ensure the excel file exists (if missing it auto-generates the template)
        excel_path = get_excel_path()
        self.assertTrue(os.path.exists(excel_path), f"Excel file {excel_path} does not exist.")
        
        # Parse data
        data = parse_portfolio_excel()
        
        # Assert structure
        self.assertIn('asset_names', data)
        self.assertIn('expected_returns', data)
        self.assertIn('volatilities', data)
        self.assertIn('correlation_matrix', data)
        self.assertIn('portfolio_weights', data)
        
        # Verify sizes (18 assets model)
        num_assets = len(data['asset_names'])
        self.assertEqual(num_assets, 18)
        self.assertEqual(len(data['expected_returns']), 18)
        self.assertEqual(len(data['volatilities']), 18)
        self.assertEqual(data['correlation_matrix'].shape, (18, 18))
        
        # Verify key Indian assets are present in the list
        self.assertIn('India Equity ETF', data['asset_names'])
        self.assertIn('Active MF - Equity', data['asset_names'])
        
        # Verify portfolio weights keys
        weights = data['portfolio_weights']
        for key in ['Min Risk', 'Balanced', 'Growth', 'High Return']:
            self.assertIn(key, weights)
            self.assertEqual(len(weights[key]), 18)
            # Allocation weights must sum close to 1.0 (100%) or 0.0
            total_w = np.sum(weights[key])
            self.assertTrue(0.0 <= total_w <= 1.05)

    def test_simulation_engine_calculations(self):
        """Test that the Monte Carlo engine runs correctly and applies spectral repair to non-PSD correlation matrices."""
        # Load parameters
        data = parse_portfolio_excel()
        
        # 1. Run simulation with standard parameters
        results = run_portfolio_simulation(
            initial_portfolio_value=100000,
            years=15,
            contribution_rate=0.03,
            distribution_rate=0.04,
            withdrawal_start_year=5,
            inflation_rate=0.02,
            allocations=data['portfolio_weights']['Balanced'],
            num_trials=100,
            expected_returns=data['expected_returns'],
            volatilities=data['volatilities'],
            correlation_matrix=data['correlation_matrix']
        )
        
        # Check return keys
        self.assertIn('years_list', results)
        self.assertIn('success_rates_nominal', results)
        self.assertIn('success_rates_real', results)
        self.assertIn('nominal_paths', results)
        self.assertIn('real_paths', results)
        self.assertIn('summary', results)
        
        # Check years length (15 years + index 0 = 16 steps)
        self.assertEqual(len(results['years_list']), 16)
        self.assertEqual(len(results['success_rates_nominal']), 16)
        
        # Check summary metrics
        summary = results['summary']
        self.assertEqual(summary['initial_value'], 100000)
        self.assertEqual(summary['target_hurdle'], 100000)
        self.assertTrue(summary['median_terminal_nominal'] >= 0)
        
        # 2. Test Spectral Repair specifically by passing a heavily non-PSD correlation matrix
        non_psd_corr = np.array([
            [1.0, 0.9, -0.9],
            [0.9, 1.0, 0.9],
            [-0.9, 0.9, 1.0]
        ]) # This matrix is invalid (non-transitive high correlations) and has negative eigenvalues
        
        # Check eigenvalues
        eigvals = np.linalg.eigvalsh(non_psd_corr)
        self.assertTrue(np.any(eigvals < 0), "Test matrix must be non-PSD for this test case.")
        
        # Run simulation with the invalid correlation matrix
        # This will trigger spectral repair. If repair fails, Cholesky raises LinAlgError and test crashes.
        try:
            repair_results = run_portfolio_simulation(
                initial_portfolio_value=10000,
                years=5,
                contribution_rate=0.0,
                distribution_rate=0.0,
                allocations=np.array([0.33, 0.33, 0.34]),
                num_trials=50,
                expected_returns=np.array([0.10, 0.08, 0.05]),
                volatilities=np.array([0.15, 0.10, 0.02]),
                correlation_matrix=non_psd_corr
            )
            self.assertTrue(repair_results['summary']['median_terminal_nominal'] > 0)
        except np.linalg.LinAlgError as e:
            self.fail(f"Simulation crashed due to correlation matrix non-PSD error: {e}")

    def test_api_simulation_view(self):
        """Test POST requests to SimulatePortfolioView endpoint with different inputs."""
        payload = {
            "initial_portfolio_value": 150000,
            "years": 10,
            "num_trials": 200,
            "portfolio_type": "Balanced",
            "contribution_rate": 3.0,
            "distribution_rate": 4.0,
            "withdrawal_start_year": 5
        }
        
        response = self.client.post(self.url, data=payload, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        
        res_data = response.json()
        self.assertEqual(res_data['portfolio_type'], 'Balanced')
        self.assertIn('assets', res_data)
        self.assertEqual(res_data['audit_report']['status'], 'NOT_RUN')
        self.assertEqual(res_data['model_version'], MODEL_VERSION)
        self.assertEqual(res_data['metadata']['model_version'], MODEL_VERSION)
        self.assertIn('disclaimer', res_data['metadata'])
        self.assertIn('runtime_ms', res_data['metadata'])
        self.assertIn('simulation', res_data['metadata']['runtime_ms'])
        self.assertIn('X-Request-ID', response.headers)
        
        # Check that assets list is returned and has content
        self.assertTrue(len(res_data['assets']) > 0)
        # Ensure correct key types in returned assets metadata
        asset_sample = res_data['assets'][0]
        self.assertIn('name', asset_sample)
        self.assertIn('weight', asset_sample)
        self.assertIn('return', asset_sample)
        self.assertIn('volatility', asset_sample)
        
        # Verify validation error status 400 for negative value inputs
        invalid_payload = payload.copy()
        invalid_payload['initial_portfolio_value'] = -100
        bad_response = self.client.post(self.url, data=invalid_payload, content_type='application/json')
        self.assertEqual(bad_response.status_code, 400)
        self.assertIn('initial_portfolio_value', bad_response.json())

    def test_api_contract_root_and_versioned_endpoints_match(self):
        """Both supported API routes should expose the same response contract during migration."""
        payload = {
            "initial_portfolio_value": 150000,
            "years": 5,
            "num_trials": 50,
            "portfolio_type": "Balanced",
            "contribution_rate": 3.0,
            "distribution_rate": 4.0,
            "withdrawal_start_year": 2
        }
        root_response = self.client.post(reverse('simulation'), data=payload, content_type='application/json')
        api_response = self.client.post(self.url, data=payload, content_type='application/json')
        self.assertEqual(root_response.status_code, 200)
        self.assertEqual(api_response.status_code, 200)

        for key in [
            'years_list',
            'success_rates_nominal',
            'success_rates_real',
            'summary',
            'assets',
            'all_assets',
            'correlation_matrix',
            'audit_report',
            'portfolio_type',
            'model_version',
            'metadata',
        ]:
            self.assertIn(key, root_response.json())
            self.assertIn(key, api_response.json())

    def test_api_validation_rejects_unbounded_or_inconsistent_inputs(self):
        payload = {
            "initial_portfolio_value": 100000,
            "years": 101,
            "num_trials": 10001,
            "portfolio_type": "Balanced",
            "environment_mode": "BAD_MODE",
            "withdrawal_start_year": 102
        }
        response = self.client.post(self.url, data=payload, content_type='application/json')
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIn('years', body)
        self.assertIn('num_trials', body)
        self.assertIn('environment_mode', body)

        custom_target_missing = {
            "initial_portfolio_value": 100000,
            "years": 10,
            "num_trials": 50,
            "target_mode": "custom",
            "withdrawal_start_year": 5
        }
        response = self.client.post(self.url, data=custom_target_missing, content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('target_hurdle', response.json())

    def test_simulation_endpoint_is_rate_limited(self):
        cache.clear()
        payload = {
            "initial_portfolio_value": 150000,
            "years": 1,
            "num_trials": 10,
            "portfolio_type": "Balanced",
            "contribution_rate": 3.0,
            "distribution_rate": 4.0,
            "withdrawal_start_year": 1
        }
        statuses = [
            self.client.post(self.url, data=payload, content_type='application/json').status_code
            for _ in range(21)
        ]
        self.assertEqual(statuses[:20], [200] * 20)
        self.assertEqual(statuses[20], 429)

    def test_market_stress_mode(self):
        """Test POST request with environment_mode: MARKET_STRESS and verify that calculations branch into Multivariate Student-t distribution without crashing."""
        payload = {
            "initial_portfolio_value": 150000,
            "years": 10,
            "num_trials": 200,
            "portfolio_type": "Balanced",
            "environment_mode": "MARKET_STRESS",
            "contribution_rate": 3.0,
            "distribution_rate": 4.0,
            "withdrawal_start_year": 5
        }
        
        response = self.client.post(self.url, data=payload, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        
        res_data = response.json()
        self.assertEqual(res_data['portfolio_type'], 'Balanced')
        self.assertIn('summary', res_data)
        self.assertIn('success_rates_real', res_data)
        self.assertTrue(res_data['summary']['median_terminal_nominal'] >= 0)

    def test_simulation_seed_reproducibility(self):
        """Test that using a fixed seed yields perfectly reproducible outcomes, while disabling the fixed seed yields variance."""
        payload = {
            "initial_portfolio_value": 150000,
            "years": 10,
            "num_trials": 200,
            "portfolio_type": "Balanced",
            "contribution_rate": 3.0,
            "distribution_rate": 4.0,
            "withdrawal_start_year": 5,
            "use_fixed_seed": True
        }
        
        # Call 1 with fixed seed
        response1 = self.client.post(self.url, data=payload, content_type='application/json')
        self.assertEqual(response1.status_code, 200)
        res_data1 = response1.json()
        
        # Call 2 with fixed seed
        response2 = self.client.post(self.url, data=payload, content_type='application/json')
        self.assertEqual(response2.status_code, 200)
        res_data2 = response2.json()
        
        # Assert they are identical
        self.assertEqual(
            res_data1['summary']['median_terminal_nominal'],
            res_data2['summary']['median_terminal_nominal']
        )
        self.assertEqual(
            res_data1['success_rates_real'],
            res_data2['success_rates_real']
        )
        
        # Call with use_fixed_seed=False
        payload_no_seed = payload.copy()
        payload_no_seed['use_fixed_seed'] = False
        
        response3 = self.client.post(self.url, data=payload_no_seed, content_type='application/json')
        self.assertEqual(response3.status_code, 200)
        res_data3 = response3.json()
        
        # Free-variance is expected to produce a different result than fixed seed
        self.assertNotEqual(
            res_data1['summary']['median_terminal_nominal'],
            res_data3['summary']['median_terminal_nominal']
        )

    def test_numerical_regression_for_deterministic_two_asset_case(self):
        """Golden values protect the core Monte Carlo math from accidental drift."""
        results = run_portfolio_simulation(**TWO_ASSET_GOLDEN_CASE['params'])
        expected = TWO_ASSET_GOLDEN_CASE['expected']

        self.assertAlmostEqual(results['summary']['median_terminal_nominal'], expected['median_terminal_nominal'], places=6)
        self.assertAlmostEqual(results['summary']['median_tvd_nominal'], expected['median_tvd_nominal'], places=6)
        self.assertEqual(results['success_rate_terminal_nominal'], expected['success_rate_terminal_nominal'])
        self.assertEqual(results['summary']['prob_reserve_breach'], expected['prob_reserve_breach'])

    def test_average_failure_year_is_recorded(self):
        results = run_portfolio_simulation(
            initial_portfolio_value=100000,
            years=5,
            contribution_rate=0.0,
            distribution_rate=1.0,
            withdrawal_start_year=0,
            inflation_rate=0.0,
            allocations=np.array([1.0]),
            num_trials=20,
            expected_returns=np.array([0.0]),
            volatilities=np.array([0.0]),
            correlation_matrix=np.array([[1.0]]),
            use_fixed_seed=True,
            enable_hard_liquidation=True,
            min_reserve_threshold_ratio=0.2,
        )

        self.assertEqual(results['avg_failure_year'], 1.0)
        self.assertEqual(results['success_rate_terminal_nominal'], 0.0)

    def test_excel_ingestion_cache_reuses_parse_until_file_changes(self):
        clear_portfolio_excel_cache()
        with patch.object(ingestion, '_parse_portfolio_excel_uncached', wraps=ingestion._parse_portfolio_excel_uncached) as parse_mock:
            first = parse_portfolio_excel()
            second = parse_portfolio_excel()

        self.assertEqual(parse_mock.call_count, 1)
        self.assertEqual(first['asset_names'], second['asset_names'])
        self.assertIsNot(first['expected_returns'], second['expected_returns'])

    def test_health_check_endpoint(self):
        """Test that the health check endpoint returns git commit info, schema version, and workbook metadata."""
        url = reverse('health')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('backend_version', data)
        self.assertIn('build_date', data)
        self.assertIn('schema_version', data)
        self.assertEqual(data['schema_version'], '3')
        self.assertEqual(data['model_version'], MODEL_VERSION)
        self.assertTrue(data['observability']['request_ids'])
        self.assertTrue(data['observability']['structured_logging'])

        # Assert workbook metadata is present
        self.assertIn('portfolio_workbook', data)
        wb_data = data['portfolio_workbook']
        self.assertEqual(wb_data['filename'], 'portfolio_data.xlsx')
        self.assertEqual(wb_data['relative_path'], 'simulation/portfolio_data.xlsx')

        if wb_data['available']:
            self.assertIn('sha256', wb_data)
            self.assertEqual(len(wb_data['sha256']), 64)
            self.assertIn('size_bytes', wb_data)
            self.assertIn('last_modified_utc', wb_data)
            self.assertTrue(wb_data['last_modified_utc'].endswith('Z'))
        else:
            self.assertIn('error', wb_data)


