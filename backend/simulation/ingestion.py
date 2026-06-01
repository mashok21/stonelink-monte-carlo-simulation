import os
import pandas as pd
import numpy as np

EXCEL_FILENAME = 'portfolio_data.xlsx'

def get_excel_path():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, EXCEL_FILENAME)

def make_default_correlation_matrix(asset_names):
    n = len(asset_names)
    C = np.eye(n)
    for i in range(min(5, n)):
        for j in range(min(5, n)):
            if i != j: C[i, j] = 0.75
    for i in [5, 6, 8, 9]:
        if i >= n: continue
        for j in [5, 6, 8, 9]:
            if j >= n: continue
            if i != j: C[i, j] = 0.50
    for i in range(min(5, n)):
        for j in [5, 6, 8, 9]:
            if j >= n: continue
            C[i, j] = C[j, i] = 0.10
    
    eigvals, eigvecs = np.linalg.eigh(C)
    eigvals = np.maximum(eigvals, 1e-8)
    C_psd = eigvecs @ np.diag(eigvals) @ eigvecs.T
    d = np.sqrt(np.diag(C_psd))
    C_psd = C_psd / d[:, None] / d[None, :]
    return C_psd

def generate_default_excel(filepath):
    asset_data = {
        'Asset Class': [
            'US Large Cap', 'US Mid Cap', 'US Small Cap', 'Dev Markets Equities', 'Emerging Markets Equities',
            'US High Yield Bonds', 'US IG Corporate Bonds', 'US Treasuries Short', 'US Treasuries Long', 'EM Bonds',
            'REITs', 'Commodities', 'Gold', 'Cash Equivalents', 'Infrastructure', 'Private Equity',
            'Hedge Funds', 'Cryptocurrencies'
        ],
        'Expected Return (pa)': [
            8.5, 9.0, 9.5, 7.5, 9.5, 
            5.5, 4.0, 2.5, 3.5, 6.0, 
            7.0, 3.5, 4.5, 2.0, 6.0, 11.0, 
            6.5, 18.0
        ],
        'Volatility': [
            15.0, 17.0, 19.0, 16.0, 21.0, 
            8.0, 5.5, 1.0, 7.5, 9.5, 
            14.5, 14.0, 14.0, 0.5, 9.5, 22.0, 
            8.5, 55.0
        ]
    }
    df_params = pd.DataFrame(asset_data)
    assets = df_params['Asset Class'].tolist()
    C_psd = make_default_correlation_matrix(assets)
    df_corr = pd.DataFrame(C_psd, index=assets, columns=assets)
    
    weights_data = {
        'Asset Class': assets,
        'Min Risk': [10.0, 0.0, 0.0, 0.0, 0.0, 0.0, 20.0, 40.0, 0.0, 0.0, 0.0, 0.0, 0.0, 30.0, 0.0, 0.0, 0.0, 0.0],
        'Balanced': [30.0, 0.0, 0.0, 15.0, 5.0, 0.0, 20.0, 0.0, 10.0, 0.0, 5.0, 0.0, 5.0, 5.0, 0.0, 0.0, 0.0, 0.0],
        'Growth': [40.0, 10.0, 0.0, 15.0, 10.0, 5.0, 0.0, 0.0, 0.0, 0.0, 5.0, 5.0, 0.0, 0.0, 0.0, 5.0, 5.0, 0.0],
        'High Return': [30.0, 0.0, 15.0, 5.0, 15.0, 0.0, 0.0, 0.0, 0.0, 0.0, 10.0, 5.0, 0.0, 0.0, 0.0, 15.0, 5.0, 5.0]
    }
    df_weights = pd.DataFrame(weights_data)
    
    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
        df_params.to_excel(writer, sheet_name='Asset Parameters', index=False)
        df_corr.to_excel(writer, sheet_name='Correlation Matrix', index=True)
        df_weights.to_excel(writer, sheet_name='Portfolio Weights', index=False)

def parse_portfolio_excel():
    filepath = get_excel_path()
    
    if not os.path.exists(filepath):
        generate_default_excel(filepath)
        
    try:
        # Load sheets with context manager to prevent file locks
        with pd.ExcelFile(filepath) as xls:
            sheet_names = xls.sheet_names
            
            # Verify required sheets exist (case-insensitive check)
            required_sheets = ['Asset Parameters', 'Correlation Matrix', 'Portfolio Weights']
            matched_sheets = {}
            for req in required_sheets:
                match = [s for s in sheet_names if s.strip().lower() == req.lower()]
                if not match:
                    raise ValueError(f"Required sheet '{req}' not found. Available sheets: {sheet_names}")
                matched_sheets[req] = match[0]
            
            # 1. Load Asset Parameters and detect header row
            df_raw_params = pd.read_excel(xls, sheet_name=matched_sheets['Asset Parameters'], header=None)
            header_idx_params = 0
            for idx, row in df_raw_params.iterrows():
                row_str = [str(x).strip().lower() for x in row.values]
                if 'asset' in row_str:
                    header_idx_params = idx
                    break
            df_params = pd.read_excel(xls, sheet_name=matched_sheets['Asset Parameters'], header=header_idx_params)
            
            # 2. Load Correlation Matrix and detect header row
            df_raw_corr = pd.read_excel(xls, sheet_name=matched_sheets['Correlation Matrix'], header=None)
            header_idx_corr = 0
            # Look for row containing any non-null strings that correspond to asset names
            for idx, row in df_raw_corr.iterrows():
                row_str = [str(x).strip().lower() for x in row.values]
                # If row contains common asset indicators
                if any(x in row_str for x in ['asset', 'india equity etf', 'us large cap']):
                    header_idx_corr = idx
                    break
            # Fallback check: find first row where element 1 is a valid string
            if header_idx_corr == 0:
                for idx, row in df_raw_corr.iterrows():
                    val = str(row.iloc[1]).strip() if len(row) > 1 else ''
                    if val and val != 'nan' and not val.replace('.', '', 1).isdigit():
                        header_idx_corr = idx
                        break
            df_corr = pd.read_excel(xls, sheet_name=matched_sheets['Correlation Matrix'], header=header_idx_corr)

            # 3. Load Portfolio Weights and detect header row
            df_raw_weights = pd.read_excel(xls, sheet_name=matched_sheets['Portfolio Weights'], header=None)
            header_idx_weights = 0
            for idx, row in df_raw_weights.iterrows():
                row_str = [str(x).strip().lower() for x in row.values]
                if 'asset' in row_str:
                    header_idx_weights = idx
                    break
            df_weights = pd.read_excel(xls, sheet_name=matched_sheets['Portfolio Weights'], header=header_idx_weights)
        
        # --- PROCESS ASSET PARAMETERS ---
        param_cols = df_params.columns.tolist()
        asset_col_match = [c for c in param_cols if 'asset' in str(c).lower()]
        if not asset_col_match:
            raise ValueError(f"Could not find an 'Asset Class' column in 'Asset Parameters' sheet. Available columns: {param_cols}")
        asset_col = asset_col_match[0]
        
        ret_col_match = [c for c in param_cols if 'return' in str(c).lower() or 'ret' in str(c).lower()]
        vol_col_match = [c for c in param_cols if 'volatility' in str(c).lower() or 'vol' in str(c).lower()]
        
        if not ret_col_match or not vol_col_match:
            raise ValueError(f"Could not find return/volatility columns in 'Asset Parameters'. Columns: {param_cols}")
        ret_col = ret_col_match[0]
        vol_col = vol_col_match[0]
        
        # Remove any rows where asset name is empty or nan
        df_params = df_params.dropna(subset=[asset_col])
        asset_names = df_params[asset_col].astype(str).str.strip().tolist()
        
        # --- PROCESS CORRELATION MATRIX ---
        corr_cols = df_corr.columns.tolist()
        df_corr = df_corr.set_index(corr_cols[0])
        df_corr.index = df_corr.index.astype(str).str.strip()
        df_corr.columns = df_corr.columns.astype(str).str.strip()
        
        # Align correlations to match the exact order of asset names
        df_corr = df_corr.reindex(index=asset_names, columns=asset_names)
        
        corr_matrix = df_corr.to_numpy(dtype=float)
        corr_matrix = np.nan_to_num(corr_matrix, nan=0.0)
        np.fill_diagonal(corr_matrix, 1.0)
        
        # --- PROCESS PORTFOLIO WEIGHTS ---
        weights_cols = df_weights.columns.tolist()
        w_asset_col_match = [c for c in weights_cols if 'asset' in str(c).lower()]
        if not w_asset_col_match:
            raise ValueError(f"Could not find an 'Asset Class' column in 'Portfolio Weights' sheet. Columns: {weights_cols}")
        w_asset_col = w_asset_col_match[0]
        
        df_weights = df_weights.set_index(w_asset_col)
        df_weights.index = df_weights.index.astype(str).str.strip()
        df_weights = df_weights.reindex(asset_names)
        
        # Parse return and volatility numeric values
        returns_val = df_params[ret_col].to_numpy(dtype=float)
        vols_val = df_params[vol_col].to_numpy(dtype=float)
        
        # Detect percentage formatting vs float decimals
        # If returns average > 0.5 (e.g. 8.5% is written as 8.5 rather than 0.085), divide by 100
        if np.any(returns_val > 1.0) or np.any(vols_val > 1.0):
            if np.mean(returns_val) > 0.5:
                returns_val = returns_val / 100.0
            if np.mean(vols_val) > 0.5:
                vols_val = vols_val / 100.0
                
        # Parse weights
        weights_dict = {}
        mapping = {
            'Min Risk': 'Portfolio 1\n(Min Risk)',
            'Balanced': 'Portfolio 2\n(Balanced)',
            'Growth': 'Portfolio 3\n(Growth)',
            'High Return': 'Portfolio 4\n(High Return)'
        }
        
        for short_name, exact_col in mapping.items():
            found_col = None
            for col in df_weights.columns:
                c_clean = str(col).replace('\r', '').replace('\n', ' ').strip().lower()
                exact_clean = exact_col.replace('\r', '').replace('\n', ' ').strip().lower()
                short_clean = short_name.replace('\r', '').replace('\n', ' ').strip().lower()
                
                # Check exact match or substring match
                if c_clean == exact_clean or short_clean in c_clean:
                    found_col = col
                    break
            
            if found_col is not None:
                w_vec = df_weights[found_col].to_numpy(dtype=float)
                w_vec = np.nan_to_num(w_vec, nan=0.0)
                # If weights sum to > 2.0, convert from percentages to decimal fractions
                if np.sum(w_vec) > 2.0:
                    w_vec = w_vec / 100.0
                weights_dict[short_name] = w_vec
            else:
                # Fallback if missing
                weights_dict[short_name] = np.zeros(len(asset_names))
                weights_dict[short_name][0] = 1.0
                
        return {
            'asset_names': asset_names,
            'expected_returns': returns_val,
            'volatilities': vols_val,
            'correlation_matrix': corr_matrix,
            'portfolio_weights': weights_dict
        }
        
    except Exception as e:
        print(f"Error parsing Excel file: {e}")
        raise e
