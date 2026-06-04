from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import numpy as np
from .engine import run_portfolio_simulation
from .ingestion import parse_portfolio_excel

class SimulatePortfolioView(APIView):
    def post(self, request):
        try:
            data = request.data
            
            # Extract inputs with defaults
            initial_val = float(data.get('initial_portfolio_value', 100000))
            years = int(data.get('years', 30))
            # Extract contribution & distribution rates (Percentage of assets)
            contribution_rate = float(data.get('contribution_rate', data.get('annual_contribution', 3.0))) / 100.0
            distribution_rate = float(data.get('distribution_rate', data.get('annual_withdrawal', 4.0))) / 100.0
            withdr_start = int(data.get('withdrawal_start_year', 15))
            inflation = float(data.get('inflation_rate', 2.5)) / 100.0
            num_trials = int(data.get('num_trials', 1000))
            
            # Portfolio mix type selection
            portfolio_type = data.get('portfolio_type', 'Balanced')
            target_hurdle = data.get('target_hurdle')
            if target_hurdle is not None:
                target_hurdle = float(target_hurdle)
            else:
                target_hurdle = initial_val
                
            # Simulation environment mode (STANDARD_CRUISE or MARKET_STRESS)
            environment_mode = data.get('environment_mode', 'STANDARD_CRUISE')
            
            # Simulation seed control (standardized baseline or live variance)
            use_fixed_seed = data.get('use_fixed_seed', True)
            if isinstance(use_fixed_seed, str):
                use_fixed_seed = use_fixed_seed.lower() == 'true'
            
            # Validate core values
            if initial_val < 0 or years <= 0 or contribution_rate < 0 or distribution_rate < 0:
                return Response(
                    {"error": "Numeric values must be positive and years must be greater than zero."},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
            if num_trials < 10 or num_trials > 10000:
                num_trials = 1000
                
            # Load dynamic parameters from Excel ingestion pipeline
            excel_data = parse_portfolio_excel()
            
            asset_names = excel_data['asset_names']
            expected_returns = excel_data['expected_returns']
            volatilities = excel_data['volatilities']
            correlation_matrix = excel_data['correlation_matrix']
            portfolio_weights = excel_data['portfolio_weights']
            asset_classes = excel_data.get('asset_classes')
            unsmoothing_factor = excel_data.get('unsmoothing_factor', 1.4)
            
            # Extract allocation weights corresponding to the portfolio_type
            if portfolio_type in portfolio_weights:
                allocations = portfolio_weights[portfolio_type]
            else:
                # Fallback
                portfolio_type = 'Balanced'
                allocations = portfolio_weights.get('Balanced', np.ones(len(expected_returns)) / len(expected_returns))
                
            # Run simulation
            results = run_portfolio_simulation(
                initial_portfolio_value=initial_val,
                years=years,
                contribution_rate=contribution_rate,
                distribution_rate=distribution_rate,
                withdrawal_start_year=withdr_start,
                inflation_rate=inflation,
                allocations=allocations,
                num_trials=num_trials,
                expected_returns=expected_returns,
                volatilities=volatilities,
                correlation_matrix=correlation_matrix,
                target_hurdle=target_hurdle,
                environment_mode=environment_mode,
                asset_classes=asset_classes,
                unsmoothing_factor=unsmoothing_factor,
                use_fixed_seed=use_fixed_seed
            )
            
            # Append portfolio info to results for frontend metadata display
            results['portfolio_type'] = portfolio_type
            results['assets'] = [
                {
                    'name': name,
                    'weight': float(weight * 100.0), # Convert to percentage for UI display
                    'return': float(ret * 100.0),
                    'volatility': float(vol * 100.0)
                }
                for name, weight, ret, vol in zip(asset_names, allocations, expected_returns, volatilities)
                if weight > 0 # Only send non-zero allocations to keep payload neat
            ]
            
            # Full correlation matrix and asset list for covariance network visualizer
            results['correlation_matrix'] = correlation_matrix.tolist()
            results['all_assets'] = [
                {
                    'name': name,
                    'weight': float(weight * 100.0),
                    'return': float(ret * 100.0),
                    'volatility': float(vol * 100.0)
                }
                for name, weight, ret, vol in zip(asset_names, allocations, expected_returns, volatilities)
            ]
            
            return Response(results, status=status.HTTP_200_OK)
            
        except ValueError as ve:
            return Response(
                {"error": f"Invalid parameter type: {str(ve)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response(
                {"error": f"An error occurred: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
