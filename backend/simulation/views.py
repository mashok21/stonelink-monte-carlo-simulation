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
            annual_contrib = float(data.get('annual_contribution', 5000))
            contrib_growth = float(data.get('annual_contribution_growth', 3.0)) / 100.0
            annual_withdr = float(data.get('annual_withdrawal', 12000))
            withdr_start = int(data.get('withdrawal_start_year', 15))
            inflation = float(data.get('inflation_rate', 2.5)) / 100.0
            num_trials = int(data.get('num_trials', 1000))
            
            # Portfolio mix type selection
            portfolio_type = data.get('portfolio_type', 'Balanced')
            
            # Validate core values
            if initial_val < 0 or years <= 0 or annual_contrib < 0 or annual_withdr < 0:
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
                annual_contribution=annual_contrib,
                annual_contribution_growth=contrib_growth,
                annual_withdrawal=annual_withdr,
                withdrawal_start_year=withdr_start,
                inflation_rate=inflation,
                allocations=allocations,
                num_trials=num_trials,
                expected_returns=expected_returns,
                volatilities=volatilities,
                correlation_matrix=correlation_matrix
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
