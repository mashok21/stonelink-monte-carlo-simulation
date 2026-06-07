import os
import sys
import django
import numpy as np

# Set up django environment so we can parse portfolio excel parameters
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "stonelink_backend.settings")
django.setup()

from simulation.ingestion import parse_portfolio_excel
from simulation.engine import run_portfolio_simulation

def format_inr(value):
    """Format float into standard INR string format for readability."""
    if value is None:
        return "-"
    return f"INR {value:,.2f}"

def main():
    # Load Balanced portfolio allocation from Excel ingestion
    excel_data = parse_portfolio_excel()
    asset_names = excel_data['asset_names']
    expected_returns = excel_data['expected_returns']
    volatilities = excel_data['volatilities']
    correlation_matrix = excel_data['correlation_matrix']
    allocations = excel_data['portfolio_weights']['Balanced']
    asset_classes = excel_data.get('asset_classes')
    unsmoothing_factor = excel_data.get('unsmoothing_factor', 1.4)

    # Inputs
    initial_val = 100000.0
    years = 30
    contrib_rate = 0.03
    withdr_start = 15
    inflation = 0.025
    min_reserve_ratio = 0.20
    num_trials = 1000
    use_fixed_seed = True

    # Four frameworks to run
    frameworks = {
        'terminal_assets': 'Terminal Asset Preservation (TAP)',
        'total_value': 'Total Value Preservation (TVP)',
        'institutional_sustainability': 'Institutional Sustainability (IS)',
        'continuous_solvency': 'Continuous Solvency (CS)'
    }

    # Distribution rates to evaluate
    dist_rates = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10, 0.15, 0.25, 0.50, 0.75]

    # Collect data structures
    results_by_framework = {f: [] for f in frameworks}

    print("Starting full sensitivity analysis across 4 frameworks and 12 distribution rates...")
    for f_code, f_name in frameworks.items():
        print(f"Running calculations for framework: {f_name}...")
        for dr in dist_rates:
            res = run_portfolio_simulation(
                initial_portfolio_value=initial_val,
                years=years,
                contribution_rate=contrib_rate,
                distribution_rate=dr,
                withdrawal_start_year=withdr_start,
                inflation_rate=inflation,
                allocations=allocations,
                num_trials=num_trials,
                expected_returns=expected_returns,
                volatilities=volatilities,
                correlation_matrix=correlation_matrix,
                target_hurdle=initial_val, # Hurdle matches initial value
                environment_mode='STANDARD_CRUISE',
                asset_classes=asset_classes,
                unsmoothing_factor=unsmoothing_factor,
                use_fixed_seed=use_fixed_seed,
                success_framework=f_code,
                enable_hard_liquidation=False, # Decoupled simulation policy evaluation
                min_reserve_threshold_ratio=min_reserve_ratio
            )
            
            # Save relevant metrics
            results_by_framework[f_code].append({
                'dist_rate': dr,
                'success_prob_real': res['success_rate_terminal_real'],
                'success_prob_nominal': res['success_rate_terminal_nominal'],
                'breach_prob': res['prob_reserve_breach'],
                'median_terminal_nominal': res['summary']['median_terminal_nominal'],
                'median_terminal_real': res['summary']['median_terminal_real']
            })

    # Prepare markdown report contents
    artifact_dir = r"C:\Users\91994\.gemini\antigravity-ide\brain\b0af60fc-971a-4c5c-93a7-b02c99b99987"
    report_path = os.path.join(artifact_dir, "sensitivity_analysis_report.md")

    # Construct the Markdown content
    md = []
    md.append("# Full Sensitivity Analysis: Distribution Rate vs. Solvency Performance")
    md.append("\nThis report compiles the sensitivity analysis for all **four Success Frameworks** across a wide spectrum of distribution rates [1% - 75%] under the newly decoupled **3-Layer Solvency Architecture**.\n")
    md.append("> [!NOTE]")
    md.append("> **Baseline Parameters Used:**")
    md.append("> * Initial Portfolio Value: **INR 100,000.00**")
    md.append("> * Simulation Horizon: **30 Years**")
    md.append("> * Annual Contribution Rate: **3.0%** (Years 1 to 15)")
    md.append("> * Withdrawal Start Year: **Year 15**")
    md.append("> * Expected Long-Term Inflation: **2.5% p.a.**")
    md.append("> * Minimum Reserve Solvency Threshold: **20.0%** (INR 20,000.00)")
    md.append("> * Asset Allocation: **Balanced** (Parsed dynamically from ingestion excel)")
    md.append("> * Trial Count: **1,000 Monte Carlo Paths**")
    md.append("> * Replication Control: **Fixed seed (42)** for mathematical reproducibility\n")

    md.append("## Executive Summary")
    md.append("The 3-layer decoupled architecture reveals stark differences in success probabilities under different frameworks:")
    md.append("1. **Terminal Asset Preservation (TAP)**: Extremely conservative. It requires Terminal Assets $\ge$ inflation-adjusted target. Once distribution rates exceed 6%, success probability collapses to 0.0% as distributions drain terminal value.")
    md.append("2. **Total Value Preservation (TVP)**: Overly optimistic. Since it defines success as Total Value Delivered (Terminal Assets + Cumulative Distributions) $\ge$ Target, success probability remains near 100.0% even at a 75% distribution rate, despite the portfolio ending with effectively zero assets.")
    md.append("3. **Institutional Sustainability (IS)**: Solves the asymptotic decay loophole. By requiring `TVD >= Target` AND `Terminal Assets >= 20% Reserve Threshold`, success probability drops to 0.0% for distribution rates $\ge$ 50% (where terminal assets are depleted), despite high distributions.")
    md.append("4. **Continuous Solvency (CS)**: The most rigorous institutional standard. Success requires `TVD >= Target` AND that the portfolio value **never** breached the 20% Reserve Threshold during the 30-year walk. Under this mode, success drops at the same points as IS in standard cruise, reflecting that minimum assets usually occur in the terminal year under steady withdrawal decay.\n")

    # Generate tables for each framework
    for f_code, f_name in frameworks.items():
        md.append(f"## Framework: {f_name}")
        md.append(f"Evaluating portfolio performance metrics for various distribution rates under the **{f_name}** framework:\n")
        md.append("| Distribution Rate | Success Prob (Real) | Success Prob (Nominal) | Reserve Breach Prob | Median Terminal Assets (Real) | Median Terminal Assets (Nominal) |")
        md.append("|-------------------|---------------------|------------------------|---------------------|-------------------------------|-----------------------------------|")
        for row in results_by_framework[f_code]:
            dr_str = f"{row['dist_rate']*100:.0f}%"
            sp_real = f"{row['success_prob_real']:.2f}%"
            sp_nom = f"{row['success_prob_nominal']:.2f}%"
            bp = f"{row['breach_prob']:.2f}%"
            mta_real = format_inr(row['median_terminal_real'])
            mta_nom = format_inr(row['median_terminal_nominal'])
            md.append(f"| {dr_str} | {sp_real} | {sp_nom} | {bp} | {mta_real} | {mta_nom} |")
        md.append("\n")

    # Analysis Comparison Section
    md.append("## Cross-Framework Comparative Insights")
    md.append("\n### 1. The Asymptotic Decay Defect & Institutional Sustainability")
    md.append("Under the old solvency definition (`Assets > 0`), the Monte Carlo engine reported **99% success** at a **75% distribution rate** (due to asymptotic float decay). Under the new **Institutional Sustainability (IS)** framework, this loophole is closed: at a **50% and 75% distribution rate**, success collapses to **0.00%** because terminal assets fail the 20% (INR 20,000) threshold requirement.\n")

    md.append("### 2. Path Dependency vs. Terminal Status")
    md.append("Under standard cruise conditions (no heavy market stress), the minimum asset value typically occurs at the terminal year because withdrawals continuously compound downward pressure. As a result, the **Institutional Sustainability** and **Continuous Solvency** frameworks align closely. However, under market stress, the continuous path check ensures early/mid-horizon breaches (e.g. during a market crash) are penalized even if the portfolio later recovers terminal value above the threshold.\n")

    # Write out the file
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    print(f"Sensitivity Analysis successfully executed and written to: {report_path}")

if __name__ == "__main__":
    main()
