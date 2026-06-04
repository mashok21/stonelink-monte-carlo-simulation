from django.test import TestCase, Client
from django.urls import reverse
import numpy as np
import os

from .ingestion import parse_portfolio_excel, get_excel_path
from .engine import run_portfolio_simulation

class PortfolioSimulationTestCase(TestCase):
    def setUp(self):
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


