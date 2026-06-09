from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
import numpy as np
import subprocess
import os
import logging
import time
from .engine import run_portfolio_simulation
from .ingestion import parse_portfolio_excel
from .audit import run_simulation_audit
from .serializers import SimulationRequestSerializer
from .model_metadata import MODEL_DISCLAIMER, MODEL_LIMITATIONS, MODEL_NAME, MODEL_VERSION, SCHEMA_VERSION

logger = logging.getLogger(__name__)

# Cache git commit info at server startup for high performance
_BACKEND_VERSION = "unknown"
_BUILD_DATE = "unknown"
_SCHEMA_VERSION = SCHEMA_VERSION

try:
    _repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _BACKEND_VERSION = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], 
        cwd=_repo_dir, 
        stderr=subprocess.DEVNULL
    ).decode("utf-8").strip()
    
    _BUILD_DATE = subprocess.check_output(
        ["git", "log", "-1", "--format=%cI"], 
        cwd=_repo_dir, 
        stderr=subprocess.DEVNULL
    ).decode("utf-8").strip()
except Exception:
    _BACKEND_VERSION = "unknown"
    _BUILD_DATE = "unknown"

class SimulatePortfolioView(APIView):
    throttle_scope = "simulation"

    def post(self, request):
        request_id = getattr(request, "request_id", "unknown")
        request_started = time.perf_counter()
        serializer = SimulationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            initial_val = data['initial_portfolio_value']
            years = data['years']
            contribution_rate = data['contribution_rate'] / 100.0
            distribution_rate = data['distribution_rate'] / 100.0
            withdr_start = data['withdrawal_start_year']
            inflation = data['inflation_rate'] / 100.0
            num_trials = data['num_trials']
            min_reserve_ratio = data['min_reserve_threshold_ratio'] / 100.0
            success_framework = data['success_framework']
            enable_hard_liquidation = data['enable_hard_liquidation']
            portfolio_type = data['portfolio_type']
            target_hurdle = data['target_hurdle']
            environment_mode = data['environment_mode']
            use_fixed_seed = data['use_fixed_seed']
            success_mode = data.get('success_mode')
            target_mode = data['target_mode']
                
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
            simulation_started = time.perf_counter()
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
                use_fixed_seed=use_fixed_seed,
                success_mode=success_mode,
                target_mode=target_mode,
                min_reserve_threshold_ratio=min_reserve_ratio,
                success_framework=success_framework,
                enable_hard_liquidation=enable_hard_liquidation
            )
            simulation_runtime_ms = round((time.perf_counter() - simulation_started) * 1000, 2)
            
            # Perform mathematical self-audit of simulation results
            params = {
                'initial_portfolio_value': initial_val,
                'years': years,
                'contribution_rate': contribution_rate,
                'distribution_rate': distribution_rate,
                'withdrawal_start_year': withdr_start,
                'inflation_rate': inflation,
                'allocations': allocations,
                'expected_returns': expected_returns,
                'volatilities': volatilities,
                'correlation_matrix': correlation_matrix,
                'target_hurdle': target_hurdle,
                'environment_mode': environment_mode,
                'asset_classes': asset_classes,
                'unsmoothing_factor': unsmoothing_factor,
                'success_mode': success_mode,
                'target_mode': target_mode,
                'use_fixed_seed': use_fixed_seed,
                'min_reserve_threshold_ratio': min_reserve_ratio,
                'success_framework': success_framework,
                'enable_hard_liquidation': enable_hard_liquidation
            }
            if data['include_audit'] or settings.SIMULATION_RUN_AUDIT_INLINE:
                audit_report = run_simulation_audit(params, results)
            else:
                audit_report = {
                    'status': 'NOT_RUN',
                    'warnings': [],
                    'test_results': {},
                    'message': 'Inline audit is disabled for normal API requests.'
                }
            results['audit_report'] = audit_report
            
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
            total_runtime_ms = round((time.perf_counter() - request_started) * 1000, 2)
            results['model_version'] = MODEL_VERSION
            results['metadata'] = {
                'request_id': request_id,
                'model_name': MODEL_NAME,
                'model_version': MODEL_VERSION,
                'schema_version': _SCHEMA_VERSION,
                'disclaimer': MODEL_DISCLAIMER,
                'limitations': MODEL_LIMITATIONS,
                'runtime_ms': {
                    'simulation': simulation_runtime_ms,
                    'total_request': total_runtime_ms,
                },
                'reproducible': bool(use_fixed_seed),
                'seed_policy': 'fixed_seed_42' if use_fixed_seed else 'random_generator_default_rng',
            }
            logger.info(
                "simulation_completed",
                extra={
                    "request_id": request_id,
                    "event": "simulation_completed",
                    "model_version": MODEL_VERSION,
                    "duration_ms": total_runtime_ms,
                    "path": request.path,
                },
            )
            
            return Response(results, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.exception(
                "Simulation request failed",
                extra={
                    "request_id": request_id,
                    "event": "simulation_failed",
                    "model_version": MODEL_VERSION,
                    "path": request.path,
                },
            )
            return Response(
                {
                    "error": "Simulation request failed.",
                    "request_id": request_id,
                    "model_version": MODEL_VERSION,
                    "disclaimer": MODEL_DISCLAIMER,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class HealthCheckView(APIView):
    def get(self, request):
        return Response({
            "backend_version": _BACKEND_VERSION,
            "build_date": _BUILD_DATE,
            "schema_version": _SCHEMA_VERSION,
            "model_name": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "observability": {
                "request_ids": True,
                "structured_logging": True,
                "error_tracking_configured": bool(settings.ERROR_TRACKING_DSN),
            },
            "disclaimer": MODEL_DISCLAIMER
        }, status=status.HTTP_200_OK)
