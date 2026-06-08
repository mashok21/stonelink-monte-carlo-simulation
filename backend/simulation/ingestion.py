import os
import threading
import pandas as pd
import numpy as np
from django.conf import settings

EXCEL_PATH = os.path.join(settings.BASE_DIR, 'simulation', 'portfolio_data.xlsx')
_CACHE_LOCK = threading.Lock()
_CACHE = {"path": None, "mtime": None, "data": None}

def get_excel_path():
    return EXCEL_PATH

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
        'Category': [
            'Public Equity', 'Public Equity', 'Public Equity', 'Public Equity', 'Public Equity',
            'Fixed Income', 'Fixed Income', 'Fixed Income', 'Fixed Income', 'Fixed Income',
            'Hard Assets', 'Commodities', 'Commodities', 'Fixed Income', 'Hard Assets', 'Private Equity',
            'Credit', 'Public Equity'
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
    
    # Simple simulation settings defaults
    settings_data = {
        'Setting': ['Starting Portfolio Value', 'Unsmoothing Factor', 'NAV Smoothing Correction'],
        'Value': [100000, 1.4, 'Yes'],
        'Description': ['Default AUM', 'Unsmoothing multiplier', 'Apply multiplier']
    }
    df_settings = pd.DataFrame(settings_data)

    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
        df_params.to_excel(writer, sheet_name='Asset Parameters', index=False)
        df_corr.to_excel(writer, sheet_name='Correlation Matrix', index=True)
        df_weights.to_excel(writer, sheet_name='Portfolio Weights', index=False)
        df_settings.to_excel(writer, sheet_name='Simulation Settings', index=False)

def _clone_excel_data(data):
    return {
        'asset_names': list(data['asset_names']),
        'expected_returns': data['expected_returns'].copy(),
        'volatilities': data['volatilities'].copy(),
        'correlation_matrix': data['correlation_matrix'].copy(),
        'portfolio_weights': {k: v.copy() for k, v in data['portfolio_weights'].items()},
        'asset_classes': list(data['asset_classes']),
        'unsmoothing_factor': data['unsmoothing_factor']
    }


def parse_portfolio_excel():
    filepath = get_excel_path()

    if not os.path.exists(filepath):
        generate_default_excel(filepath)

    mtime = os.path.getmtime(filepath)
    with _CACHE_LOCK:
        if _CACHE["path"] == filepath and _CACHE["mtime"] == mtime and _CACHE["data"] is not None:
            return _clone_excel_data(_CACHE["data"])

    data = _parse_portfolio_excel_uncached(filepath)
    with _CACHE_LOCK:
        _CACHE.update({"path": filepath, "mtime": mtime, "data": _clone_excel_data(data)})
    return data


def clear_portfolio_excel_cache():
    with _CACHE_LOCK:
        _CACHE.update({"path": None, "mtime": None, "data": None})


def _parse_portfolio_excel_uncached(filepath):
    try:
        # Load sheets with context manager to prevent file locks
        with pd.ExcelFile(filepath) as xls:
            sheet_names = xls.sheet_names
            
            # Verify required sheets exist (case-insensitive check)
            required_sheets = ['Asset Parameters', 'Correlation Matrix', 'Portfolio Weights', 'Simulation Settings']
            matched_sheets = {}
            for req in required_sheets:
                match = [s for s in sheet_names if s.strip().lower() == req.lower()]
                if not match:
                    # Simulation Settings is optional for backward compatibility
                    if req == 'Simulation Settings':
                        matched_sheets[req] = None
                        continue
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
            for idx, row in df_raw_corr.iterrows():
                row_str = [str(x).strip().lower() for x in row.values]
                if any(x in row_str for x in ['asset', 'india equity etf', 'us large cap']):
                    header_idx_corr = idx
                    break
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
            
            # 4. Load Simulation Settings and check for Unsmoothing Factor
            unsmoothing_factor = 1.4
            if matched_sheets['Simulation Settings'] is not None:
                df_settings = pd.read_excel(xls, sheet_name=matched_sheets['Simulation Settings'], header=None)
                for idx, row in df_settings.iterrows():
                    first_cell = str(row.iloc[0]).strip().lower()
                    if 'unsmoothing factor' in first_cell:
                        try:
                            unsmoothing_factor = float(row.iloc[1])
                        except Exception:
                            pass
                        break
        
        # --- PROCESS ASSET PARAMETERS ---
        param_cols = df_params.columns.tolist()
        asset_col_match = [c for c in param_cols if 'asset' in str(c).lower()]
        if not asset_col_match:
            raise ValueError(f"Could not find an 'Asset Class' column in 'Asset Parameters' sheet. Available columns: {param_cols}")
        asset_col = asset_col_match[0]
        
        # Category Column
        cat_col_match = [c for c in param_cols if 'category' in str(c).lower() or 'cat' in str(c).lower()]
        cat_col = cat_col_match[0] if cat_col_match else None
        
        ret_col_match = [c for c in param_cols if 'return' in str(c).lower() or 'ret' in str(c).lower()]
        vol_col_match = [c for c in param_cols if 'volatility' in str(c).lower() or 'vol' in str(c).lower()]
        
        if not ret_col_match or not vol_col_match:
            raise ValueError(f"Could not find return/volatility columns in 'Asset Parameters'. Columns: {param_cols}")
        ret_col = ret_col_match[0]
        vol_col = vol_col_match[0]
        
        # Remove any rows where asset name is empty or nan
        df_params = df_params.dropna(subset=[asset_col])
        asset_names = df_params[asset_col].astype(str).str.strip().tolist()
        
        # Determine asset categories
        categories = []
        if cat_col:
            categories = df_params[cat_col].astype(str).str.strip().tolist()
        else:
            categories = ['Public Equity'] * len(asset_names)
            
        # Classify asset classes into: equity, fixed_income, private
        asset_classes = []
        for cat in categories:
            cat_lower = cat.lower()
            if cat_lower in ['public equity', 'dynamic', 'commodities', 'hard assets']:
                asset_classes.append('equity')
            elif cat_lower in ['fixed income', 'fixed_income']:
                asset_classes.append('fixed_income')
            elif cat_lower in ['private equity', 'credit', 'private_equity']:
                asset_classes.append('private')
            else:
                # Fallback based on text match
                if 'equity' in cat_lower or 'etf' in cat_lower or 'mf' in cat_lower or 'metals' in cat_lower or 'invit' in cat_lower:
                    asset_classes.append('equity')
                elif 'bond' in cat_lower or 'treasur' in cat_lower or 'cash' in cat_lower:
                    asset_classes.append('fixed_income')
                else:
                    asset_classes.append('private')
        
        # --- PROCESS CORRELATION MATRIX ---
        corr_cols = df_corr.columns.tolist()
        df_corr = df_corr.set_index(corr_cols[0])
        df_corr.index = df_corr.index.astype(str).str.strip()
        df_corr.columns = df_corr.columns.astype(str).str.strip()
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
        
        returns_val = df_params[ret_col].to_numpy(dtype=float)
        vols_val = df_params[vol_col].to_numpy(dtype=float)
        
        if np.any(returns_val > 1.0) or np.any(vols_val > 1.0):
            if np.mean(returns_val) > 0.5:
                returns_val = returns_val / 100.0
            if np.mean(vols_val) > 0.5:
                vols_val = vols_val / 100.0
                
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
                
                if c_clean == exact_clean or short_clean in c_clean:
                    found_col = col
                    break
            
            if found_col is not None:
                w_vec = df_weights[found_col].to_numpy(dtype=float)
                w_vec = np.nan_to_num(w_vec, nan=0.0)
                if np.sum(w_vec) > 2.0:
                    w_vec = w_vec / 100.0
                weights_dict[short_name] = w_vec
            else:
                weights_dict[short_name] = np.zeros(len(asset_names))
                weights_dict[short_name][0] = 1.0
                
        return {
            'asset_names': asset_names,
            'expected_returns': returns_val,
            'volatilities': vols_val,
            'correlation_matrix': corr_matrix,
            'portfolio_weights': weights_dict,
            'asset_classes': asset_classes,
            'unsmoothing_factor': unsmoothing_factor
        }
        
    except Exception as e:
        print(f"Error parsing Excel file: {e}")
        raise e
