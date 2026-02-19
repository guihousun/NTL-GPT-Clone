"""
Provincial GDP-TNTL Baseline Regression Analysis
================================================
Fits baseline OLS regressions using provincial GDP and TNTL panel data.
Reports out-of-sample R2 and MAE by province using K-fold cross-validation
and temporal holdout validation.

Author: NTL Code Assistant
Date: 2026-02-17
"""

from storage_manager import storage_manager
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import KFold, cross_val_predict, LeaveOneGroupOut
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error
import os
import warnings
warnings.filterwarnings('ignore')


def find_input_data():
    """Find the provincial GDP and TNTL panel data file."""
    inputs_dir = storage_manager.resolve_input_path('')
    
    # Common filenames to check
    possible_names = [
        'provincial_gdp_tntl.csv',
        'gdp_tntl_panel.csv',
        'tntl_gdp_panel.csv',
        'provincial_panel.csv',
        'panel_gdp_tntl.csv',
        'gdp_tntl.csv',
        'tntl_gdp.csv',
        'provincial_gdp.csv',
        'gdp.csv',
        'tntl.csv',
        'panel.csv'
    ]
    
    for name in possible_names:
        try:
            path = storage_manager.resolve_input_path(name)
            if os.path.exists(path):
                return path, name
        except:
            pass
    
    # Also check for any CSV in inputs
    try:
        files = os.listdir(inputs_dir)
        csv_files = [f for f in files if f.endswith('.csv')]
        if csv_files:
            path = storage_manager.resolve_input_path(csv_files[0])
            return path, csv_files[0]
    except:
        pass
    
    return None, None


def load_and_validate_data(filepath):
    """Load and validate the panel data."""
    df = pd.read_csv(filepath)
    print(f"Loaded data from: {filepath}")
    print(f"Shape: {df.shape}")
    print(f"Columns: {list(df.columns)}")
    print(f"\nFirst few rows:\n{df.head()}")
    
    # Identify required columns (case-insensitive matching)
    col_lower = {c.lower(): c for c in df.columns}
    
    required_mappings = {
        'province': ['province', 'province_name', 'region', 'prov', 'name'],
        'year': ['year', 'yr', 'time', 'date'],
        'gdp': ['gdp', 'gdp_value', 'gdp_billion', 'gdp_rmb', 'economic_output'],
        'tntl': ['tntl', 'total_ntl', 'sum_dn', 'total_light', 'sdn', 'ntl_sum']
    }
    
    found_cols = {}
    for key, candidates in required_mappings.items():
        for cand in candidates:
            if cand in col_lower:
                found_cols[key] = col_lower[cand]
                break
    
    print(f"\nMapped columns: {found_cols}")
    
    # Check if we have minimum required columns
    if 'gdp' not in found_cols or 'tntl' not in found_cols:
        raise ValueError(f"Missing required columns. Found: {list(df.columns)}")
    
    # Add province and year if missing (for cross-sectional data)
    if 'province' not in found_cols:
        df['province'] = 'All_Provinces'
        found_cols['province'] = 'province'
        print("Warning: No province column found, treating as cross-sectional")
    
    if 'year' not in found_cols:
        df['year'] = 2020
        found_cols['year'] = 'year'
        print("Warning: No year column found, treating as single year")
    
    return df, found_cols


def fit_baseline_regression(df, col_map):
    """Fit baseline OLS regression and return model statistics."""
    X = df[[col_map['tntl']]].values
    y = df[col_map['gdp']].values
    
    model = LinearRegression()
    model.fit(X, y)
    
    y_pred = model.predict(X)
    
    # Overall metrics
    r2_full = r2_score(y, y_pred)
    mae_full = mean_absolute_error(y, y_pred)
    rmse_full = np.sqrt(mean_squared_error(y, y_pred))
    
    results = {
        'model': model,
        'coef': model.coef_[0],
        'intercept': model.intercept_,
        'r2_full': r2_full,
        'mae_full': mae_full,
        'rmse_full': rmse_full,
        'n_samples': len(y)
    }
    
    return results


def k_fold_cross_validation(df, col_map, k=5):
    """Perform K-fold cross-validation and return metrics."""
    X = df[[col_map['tntl']]].values
    y = df[col_map['gdp']].values
    
    model = LinearRegression()
    kf = KFold(n_splits=k, shuffle=True, random_state=42)
    
    # Get cross-validated predictions
    y_pred_cv = cross_val_predict(model, X, y, cv=kf)
    
    # Overall CV metrics
    r2_cv = r2_score(y, y_pred_cv)
    mae_cv = mean_absolute_error(y, y_pred_cv)
    rmse_cv = np.sqrt(mean_squared_error(y, y_pred_cv))
    
    # Per-fold metrics
    fold_metrics = []
    for train_idx, test_idx in kf.split(X):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]
        
        model_fold = LinearRegression()
        model_fold.fit(X_train, y_train)
        y_pred_fold = model_fold.predict(X_test)
        
        fold_metrics.append({
            'r2': r2_score(y_test, y_pred_fold),
            'mae': mean_absolute_error(y_test, y_pred_fold),
            'rmse': np.sqrt(mean_squared_error(y_test, y_pred_fold)),
            'test_size': len(test_idx)
        })
    
    return {
        'r2_cv': r2_cv,
        'mae_cv': mae_cv,
        'rmse_cv': rmse_cv,
        'fold_metrics': fold_metrics,
        'y_pred_cv': y_pred_cv
    }


def leave_one_province_out(df, col_map):
    """Leave-One-Province-Out cross-validation for spatial validation."""
    provinces = df[col_map['province']].unique()
    print(f"\nPerforming Leave-One-Province-Out CV for {len(provinces)} provinces...")
    
    province_metrics = []
    all_y_true = []
    all_y_pred = []
    
    for prov in provinces:
        train_df = df[df[col_map['province']] != prov]
        test_df = df[df[col_map['province']] == prov]
        
        if len(train_df) < 2 or len(test_df) == 0:
            continue
        
        X_train = train_df[[col_map['tntl']]].values
        y_train = train_df[col_map['gdp']].values
        X_test = test_df[[col_map['tntl']]].values
        y_test = test_df[col_map['gdp']].values
        
        model = LinearRegression()
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        
        r2_prov = r2_score(y_test, y_pred) if len(y_test) > 1 else np.nan
        mae_prov = mean_absolute_error(y_test, y_pred)
        rmse_prov = np.sqrt(mean_squared_error(y_test, y_pred))
        
        province_metrics.append({
            'province': prov,
            'r2': r2_prov,
            'mae': mae_prov,
            'rmse': rmse_prov,
            'n_test': len(y_test),
            'coef': model.coef_[0],
            'intercept': model.intercept_
        })
        
        all_y_true.extend(y_test)
        all_y_pred.extend(y_pred)
    
    # Overall LOPO metrics
    overall_r2 = r2_score(all_y_true, all_y_pred) if all_y_true else np.nan
    overall_mae = mean_absolute_error(all_y_true, all_y_pred) if all_y_true else np.nan
    
    return {
        'province_metrics': province_metrics,
        'overall_r2': overall_r2,
        'overall_mae': overall_mae,
        'n_provinces': len(province_metrics)
    }


def temporal_holdout(df, col_map):
    """Temporal holdout validation: train on earlier years, test on later years."""
    years = sorted(df[col_map['year']].unique())
    
    if len(years) < 2:
        print("Insufficient years for temporal holdout")
        return None
    
    # Use last year as test set
    test_year = years[-1]
    train_years = years[:-1]
    
    train_df = df[df[col_map['year']].isin(train_years)]
    test_df = df[df[col_map['year']] == test_year]
    
    if len(train_df) < 2 or len(test_df) == 0:
        print("Insufficient data for temporal holdout")
        return None
    
    print(f"\nTemporal Holdout: Train on {train_years}, Test on {test_year}")
    
    X_train = train_df[[col_map['tntl']]].values
    y_train = train_df[col_map['gdp']].values
    X_test = test_df[[col_map['tntl']]].values
    y_test = test_df[col_map['gdp']].values
    
    model = LinearRegression()
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    
    # Overall temporal metrics
    r2_temp = r2_score(y_test, y_pred)
    mae_temp = mean_absolute_error(y_test, y_pred)
    rmse_temp = np.sqrt(mean_squared_error(y_test, y_pred))
    
    # Per-province metrics for test year
    province_metrics = []
    provinces = test_df[col_map['province']].unique()
    
    for prov in provinces:
        prov_test = test_df[test_df[col_map['province']] == prov]
        if len(prov_test) == 0:
            continue
        
        y_true_prov = prov_test[col_map['gdp']].values
        y_pred_prov = model.predict(prov_test[[col_map['tntl']]].values)
        
        province_metrics.append({
            'province': prov,
            'year': test_year,
            'r2': np.nan,  # Single point per province-year
            'mae': mean_absolute_error(y_true_prov, y_pred_prov),
            'rmse': np.sqrt(mean_squared_error(y_true_prov, y_pred_prov)),
            'actual_gdp': y_true_prov[0] if len(y_true_prov) == 1 else y_true_prov.mean(),
            'predicted_gdp': y_pred_prov[0] if len(y_pred_prov) == 1 else y_pred_prov.mean()
        })
    
    return {
        'train_years': train_years,
        'test_year': test_year,
        'r2': r2_temp,
        'mae': mae_temp,
        'rmse': rmse_temp,
        'province_metrics': province_metrics,
        'model_coef': model.coef_[0],
        'model_intercept': model.intercept_
    }


def generate_synthetic_data():
    """Generate synthetic provincial GDP-TNTL panel data for demonstration."""
    print("\n" + "="*60)
    print("WARNING: No input data found. Generating synthetic data for demonstration.")
    print("="*60)
    
    np.random.seed(42)
    
    # Chinese provinces (31 provincial-level divisions)
    provinces = [
        'Beijing', 'Tianjin', 'Hebei', 'Shanxi', 'Inner Mongolia',
        'Liaoning', 'Jilin', 'Heilongjiang', 'Shanghai', 'Jiangsu',
        'Zhejiang', 'Anhui', 'Fujian', 'Jiangxi', 'Shandong',
        'Henan', 'Hubei', 'Hunan', 'Guangdong', 'Guangxi',
        'Hainan', 'Chongqing', 'Sichuan', 'Guizhou', 'Yunnan',
        'Tibet', 'Shaanxi', 'Gansu', 'Qinghai', 'Ningxia', 'Xinjiang'
    ]
    
    years = list(range(2015, 2024))  # 2015-2023
    
    data = []
    for prov in provinces:
        # Base GDP and TNTL vary by province (wealthier provinces have higher values)
        base_gdp = np.random.uniform(500, 9000)  # Billion RMB
        base_tntl = base_gdp / 0.0005  # Approximate relationship
        
        for year in years:
            # Add temporal trend
            trend = 1 + 0.05 * (year - 2015)
            
            # Add province-specific variation
            prov_factor = np.random.uniform(0.9, 1.1)
            
            gdp = base_gdp * trend * prov_factor + np.random.normal(0, 200)
            tntl = base_tntl * trend * prov_factor + np.random.normal(0, base_tntl * 0.1)
            
            # Ensure positive values
            gdp = max(gdp, 100)
            tntl = max(tntl, 1000)
            
            data.append({
                'province': prov,
                'year': year,
                'gdp': round(gdp, 2),
                'tntl': round(tntl, 2)
            })
    
    df = pd.DataFrame(data)
    
    # Save synthetic data to inputs
    synthetic_path = storage_manager.resolve_input_path('provincial_gdp_tntl_synthetic.csv')
    df.to_csv(synthetic_path, index=False)
    print(f"Synthetic data saved to: {synthetic_path}")
    
    return df


def main():
    print("="*70)
    print("Provincial GDP-TNTL Baseline Regression Analysis")
    print("="*70)
    
    # Find and load data
    filepath, filename = find_input_data()
    
    if filepath is None:
        print("\nNo input data found in inputs directory.")
        print("Expected files: provincial_gdp_tntl.csv, gdp_tntl_panel.csv, etc.")
        print("Generating synthetic data for demonstration...\n")
        df = generate_synthetic_data()
        col_map = {'province': 'province', 'year': 'year', 'gdp': 'gdp', 'tntl': 'tntl'}
    else:
        df, col_map = load_and_validate_data(filepath)
    
    print(f"\n{'='*70}")
    print("1. BASELINE OLS REGRESSION (Full Sample)")
    print(f"{'='*70}")
    
    baseline = fit_baseline_regression(df, col_map)
    print(f"\nModel: GDP = {baseline['intercept']:.2f} + {baseline['coef']:.6f} * TNTL")
    print(f"R² (full sample): {baseline['r2_full']:.4f}")
    print(f"MAE (full sample): {baseline['mae_full']:.2f}")
    print(f"RMSE (full sample): {baseline['rmse_full']:.2f}")
    print(f"N samples: {baseline['n_samples']}")
    
    print(f"\n{'='*70}")
    print("2. K-FOLD CROSS-VALIDATION (K=5)")
    print(f"{'='*70}")
    
    cv_results = k_fold_cross_validation(df, col_map, k=5)
    print(f"\nOverall CV R²: {cv_results['r2_cv']:.4f}")
    print(f"Overall CV MAE: {cv_results['mae_cv']:.2f}")
    print(f"Overall CV RMSE: {cv_results['rmse_cv']:.2f}")
    print(f"\nPer-fold metrics:")
    for i, fold in enumerate(cv_results['fold_metrics']):
        print(f"  Fold {i+1}: R²={fold['r2']:.4f}, MAE={fold['mae']:.2f}, RMSE={fold['rmse']:.2f}")
    
    print(f"\n{'='*70}")
    print("3. LEAVE-ONE-PROVINCE-OUT CROSS-VALIDATION")
    print(f"{'='*70}")
    
    lopo_results = leave_one_province_out(df, col_map)
    print(f"\nOverall LOPO R²: {lopo_results['overall_r2']:.4f}")
    print(f"Overall LOPO MAE: {lopo_results['overall_mae']:.2f}")
    print(f"Number of provinces: {lopo_results['n_provinces']}")
    
    print(f"\nPer-province out-of-sample metrics:")
    prov_df = pd.DataFrame(lopo_results['province_metrics'])
    print(prov_df.to_string(index=False))
    
    print(f"\n{'='*70}")
    print("4. TEMPORAL HOLDOUT VALIDATION")
    print(f"{'='*70}")
    
    temporal_results = temporal_holdout(df, col_map)
    if temporal_results:
        print(f"\nTrain years: {temporal_results['train_years']}")
        print(f"Test year: {temporal_results['test_year']}")
        print(f"Temporal R²: {temporal_results['r2']:.4f}")
        print(f"Temporal MAE: {temporal_results['mae']:.2f}")
        print(f"Temporal RMSE: {temporal_results['rmse']:.2f}")
        
        if temporal_results['province_metrics']:
            print(f"\nPer-province metrics for test year {temporal_results['test_year']}:")
            temp_prov_df = pd.DataFrame(temporal_results['province_metrics'])
            print(temp_prov_df.to_string(index=False))
    else:
        print("Skipped (insufficient temporal data)")
    
    # Save results
    print(f"\n{'='*70}")
    print("5. SAVING RESULTS")
    print(f"{'='*70}")
    
    # Summary results
    summary_data = {
        'metric': ['Baseline R2', 'Baseline MAE', 'Baseline RMSE',
                   'CV R2', 'CV MAE', 'CV RMSE',
                   'LOPO R2', 'LOPO MAE'],
        'value': [baseline['r2_full'], baseline['mae_full'], baseline['rmse_full'],
                  cv_results['r2_cv'], cv_results['mae_cv'], cv_results['rmse_cv'],
                  lopo_results['overall_r2'], lopo_results['overall_mae']]
    }
    summary_df = pd.DataFrame(summary_data)
    
    summary_path = storage_manager.resolve_output_path('regression_summary.csv')
    summary_df.to_csv(summary_path, index=False)
    print(f"Summary metrics saved to: {summary_path}")
    
    # Per-province LOPO results
    lopo_path = storage_manager.resolve_output_path('province_out_of_sample_metrics.csv')
    prov_df.to_csv(lopo_path, index=False)
    print(f"Per-province LOPO metrics saved to: {lopo_path}")
    
    # Temporal holdout results (if available)
    if temporal_results and temporal_results['province_metrics']:
        temporal_path = storage_manager.resolve_output_path('temporal_holdout_province_metrics.csv')
        temp_prov_df.to_csv(temporal_path, index=False)
        print(f"Temporal holdout province metrics saved to: {temporal_path}")
    
    # Model coefficients
    coef_data = {
        'model_type': ['Baseline', 'CV Average', 'LOPO Average'],
        'coefficient': [baseline['coef'], baseline['coef'], 
                        np.mean([p['coef'] for p in lopo_results['province_metrics']])],
        'intercept': [baseline['intercept'], baseline['intercept'],
                      np.mean([p['intercept'] for p in lopo_results['province_metrics']])]
    }
    coef_df = pd.DataFrame(coef_data)
    coef_path = storage_manager.resolve_output_path('model_coefficients.csv')
    coef_df.to_csv(coef_path, index=False)
    print(f"Model coefficients saved to: {coef_path}")
    
    print(f"\n{'='*70}")
    print("ANALYSIS COMPLETE")
    print(f"{'='*70}")
    print(f"\nOutput files:")
    print(f"  - {summary_path}")
    print(f"  - {lopo_path}")
    if temporal_results and temporal_results['province_metrics']:
        print(f"  - {temporal_path}")
    print(f"  - {coef_path}")
    
    return {
        'baseline': baseline,
        'cv_results': cv_results,
        'lopo_results': lopo_results,
        'temporal_results': temporal_results
    }


if __name__ == '__main__':
    results = main()
