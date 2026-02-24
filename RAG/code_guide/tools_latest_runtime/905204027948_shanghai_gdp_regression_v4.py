#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Shanghai ANTL-GDP Regression Analysis (2013-2022)
Analyzes relationship between Annual Nighttime Light (ANTL) and GDP using multiple regression models.
Selects best-fitting model based on R², AIC, BIC, RMSE, and cross-validation scores.

Author: NTL-GPT System
Date: 2026-02-23
"""

from storage_manager import storage_manager
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression, Ridge, Lasso, ElasticNet
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.model_selection import cross_val_score, KFold
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error
import statsmodels.api as sm
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# STEP 1: Load Data
# ============================================================
print("=" * 60)
print("Shanghai ANTL-GDP Regression Analysis (2013-2022)")
print("=" * 60)

# Load ANTL statistics
antl_csv_path = storage_manager.resolve_output_path('shanghai_ANTL_statistics.csv')
antl_df = pd.read_csv(antl_csv_path)
print(f"\n[1] Loaded ANTL statistics: {len(antl_df)} records")
print(antl_df.head())

# Load official GDP data
gdp_csv_path = storage_manager.resolve_input_path('shanghai_gdp_2013_2022.csv')
gdp_df = pd.read_csv(gdp_csv_path)
print(f"\n[2] Loaded GDP data: {len(gdp_df)} records")
print(gdp_df.head())

# Merge datasets
# Standardize column names to lowercase
antl_df.columns = antl_df.columns.str.lower().str.strip()
gdp_df.columns = gdp_df.columns.str.lower().str.strip()

# Merge on 'year' column
data = pd.merge(antl_df, gdp_df, on='year')
print(f"\n[3] Merged dataset: {len(data)} records")
print(data[['year', 'antl', 'value_100m_cny']].head(10))

# ============================================================
# STEP 2: Data Preparation
# ============================================================
# Column names from merged data
antl_col = 'antl'
gdp_col = 'value_100m_cny'

# Prepare X and y
X = data[antl_col].values.reshape(-1, 1)
y = data[gdp_col].values
predictor_name = 'ANTL'

print(f"\n[4] Using {predictor_name} as predictor variable")
print(f"     X shape: {X.shape}, y shape: {y.shape}")
print(f"     X range: [{X.min():.2f}, {X.max():.2f}]")
print(f"     y range: [{y.min():.2f}, {y.max():.2f}]")

# ============================================================
# STEP 3: Define Regression Models
# ============================================================
models = {
    'OLS': LinearRegression(),
    'Ridge (α=1.0)': Ridge(alpha=1.0),
    'Ridge (α=0.1)': Ridge(alpha=0.1),
    'Lasso (α=0.1)': Lasso(alpha=0.1),
    'Lasso (α=0.01)': Lasso(alpha=0.01),
    'ElasticNet': ElasticNet(alpha=0.1, l1_ratio=0.5),
    'RandomForest (n=100)': RandomForestRegressor(n_estimators=100, random_state=42),
    'RandomForest (n=200)': RandomForestRegressor(n_estimators=200, random_state=42),
    'GradientBoosting': GradientBoostingRegressor(n_estimators=100, random_state=42)
}

# ============================================================
# STEP 4: Fit Models and Calculate Metrics
# ============================================================
print("\n" + "=" * 60)
print("Model Fitting and Evaluation")
print("=" * 60)

results = []
n_samples = len(y)
n_features = X.shape[1]

for name, model in models.items():
    print(f"\nFitting {name}...")
    
    # Fit model
    model.fit(X, y)
    y_pred = model.predict(X)
    
    # Calculate metrics
    r2 = r2_score(y, y_pred)
    rmse = np.sqrt(mean_squared_error(y, y_pred))
    mae = mean_absolute_error(y, y_pred)
    rss = np.sum((y - y_pred) ** 2)
    
    # AIC and BIC
    k = n_features + 1
    aic = n_samples * np.log(rss / n_samples) + 2 * k
    bic = n_samples * np.log(rss / n_samples) + k * np.log(n_samples)
    
    # Cross-validation (5-fold)
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    cv_scores = cross_val_score(model, X, y, cv=kf, scoring='r2')
    cv_r2_mean = cv_scores.mean()
    cv_r2_std = cv_scores.std()
    
    # Store results
    results.append({
        'model': name,
        'R2': r2,
        'AIC': aic,
        'BIC': bic,
        'RMSE': rmse,
        'MAE': mae,
        'CV_R2_mean': cv_r2_mean,
        'CV_R2_std': cv_r2_std
    })
    
    print(f"  R² = {r2:.4f}, AIC = {aic:.2f}, BIC = {bic:.2f}, RMSE = {rmse:.2f}")
    print(f"  CV R² = {cv_r2_mean:.4f} (±{cv_r2_std:.4f})")

# Convert to DataFrame
results_df = pd.DataFrame(results)

# ============================================================
# STEP 5: Statistical Significance Testing (OLS only)
# ============================================================
print("\n" + "=" * 60)
print("OLS Statistical Significance Test")
print("=" * 60)

X_ols = sm.add_constant(X)
ols_model = sm.OLS(y, X_ols).fit()
print(ols_model.summary())

ols_result_pvalue = ols_model.pvalues[1]
print(f"\nOLS p-value for {predictor_name}: {ols_result_pvalue:.6f}")

# ============================================================
# STEP 6: Select Best Model
# ============================================================
print("\n" + "=" * 60)
print("Model Selection")
print("=" * 60)

# Best by R²
best_r2_idx = int(results_df['R2'].idxmax())
best_r2_model = results_df.loc[best_r2_idx]
print(f"\nBest model by R²: {best_r2_model['model']}")
print(f"  R² = {best_r2_model['R2']:.4f}")

# Best by AIC
best_aic_idx = int(results_df['AIC'].idxmin())
best_aic_model = results_df.loc[best_aic_idx]
print(f"\nBest model by AIC: {best_aic_model['model']}")
print(f"  AIC = {best_aic_model['AIC']:.2f}")

# Best by BIC
best_bic_idx = int(results_df['BIC'].idxmin())
best_bic_model = results_df.loc[best_bic_idx]
print(f"\nBest model by BIC: {best_bic_model['model']}")
print(f"  BIC = {best_bic_model['BIC']:.2f}")

# Best by Cross-Validation
best_cv_idx = int(results_df['CV_R2_mean'].idxmax())
best_cv_model = results_df.loc[best_cv_idx]
print(f"\nBest model by CV R²: {best_cv_model['model']}")
print(f"  CV R² = {best_cv_model['CV_R2_mean']:.4f}")

# Overall best model selection
# If R² difference < 0.01, prefer simpler model (OLS/Ridge over RF)
r2_threshold = 0.01
top_models = results_df[results_df['R2'] >= results_df['R2'].max() - r2_threshold]

if len(top_models) > 1:
    linear_models = top_models[top_models['model'].str.contains('OLS|Ridge|Lasso', regex=True)]
    if len(linear_models) > 0:
        overall_best_idx = int(linear_models['R2'].idxmax())
    else:
        overall_best_idx = int(top_models['R2'].idxmax())
else:
    overall_best_idx = int(top_models.index[0])

overall_best = results_df.loc[overall_best_idx]

print("\n" + "=" * 60)
print("OVERALL BEST MODEL SELECTION")
print("=" * 60)
print(f"\n*** RECOMMENDED MODEL: {overall_best['model']} ***")
print(f"  R² = {overall_best['R2']:.4f}")
print(f"  AIC = {overall_best['AIC']:.2f}")
print(f"  BIC = {overall_best['BIC']:.2f}")
print(f"  RMSE = {overall_best['RMSE']:.2f}")
print(f"  MAE = {overall_best['MAE']:.2f}")
print(f"  CV R² = {overall_best['CV_R2_mean']:.4f} (±{overall_best['CV_R2_std']:.4f})")

# ============================================================
# STEP 7: Save Results
# ============================================================
report_csv_path = storage_manager.resolve_output_path('shanghai_GDP_Regression_Report.csv')
results_df.to_csv(report_csv_path, index=False)
print(f"\n[5] Comprehensive report saved to: outputs/shanghai_GDP_Regression_Report.csv")

# Save summary
summary = {
    'study_area': 'Shanghai',
    'period': '2013-2022',
    'n_samples': n_samples,
    'predictor_variable': predictor_name,
    'target_variable': 'GDP (100 million CNY)',
    'best_model_by_r2': best_r2_model['model'],
    'best_r2_value': best_r2_model['R2'],
    'best_model_by_aic': best_aic_model['model'],
    'best_aic_value': best_aic_model['AIC'],
    'best_model_by_bic': best_bic_model['model'],
    'best_bic_value': best_bic_model['BIC'],
    'best_model_by_cv': best_cv_model['model'],
    'best_cv_r2_value': best_cv_model['CV_R2_mean'],
    'recommended_model': overall_best['model'],
    'recommended_r2': overall_best['R2'],
    'recommended_aic': overall_best['AIC'],
    'recommended_bic': overall_best['BIC'],
    'recommended_rmse': overall_best['RMSE'],
    'recommended_mae': overall_best['MAE'],
    'recommended_cv_r2': overall_best['CV_R2_mean'],
    'ols_pvalue': ols_result_pvalue
}

summary_df = pd.DataFrame([summary])
summary_csv_path = storage_manager.resolve_output_path('shanghai_GDP_Model_Summary.csv')
summary_df.to_csv(summary_csv_path, index=False)
print(f"[6] Model summary saved to: outputs/shanghai_GDP_Model_Summary.csv")

# ============================================================
# STEP 8: Interpretation
# ============================================================
print("\n" + "=" * 60)
print("INTERPRETATION AND RECOMMENDATIONS")
print("=" * 60)

r2_value = overall_best['R2']
if r2_value >= 0.90:
    interpretation = "EXCELLENT: Very strong correlation between ANTL and GDP."
elif r2_value >= 0.80:
    interpretation = "STRONG: Strong correlation. Model is suitable for GDP estimation."
elif r2_value >= 0.60:
    interpretation = "MODERATE: Moderate correlation. Use with caution."
else:
    interpretation = "WEAK: Weak correlation. Consider alternative approaches."

print(f"\nR² Interpretation: {interpretation}")
print(f"\nLiterature Comparison:")
print(f"  - Chen et al. (2022): Expected R² = 0.78-0.85")
print(f"  - Wu et al. (2023): VNCI-corrected R² = 0.90-0.92")
print(f"  - Shi et al. (2014): Corrected NPP-VIIRS R² = 0.87")
print(f"\nOur Result: R² = {r2_value:.4f} ({overall_best['model']})")

if r2_value >= 0.78:
    print("\n✓ Result is CONSISTENT with published literature.")
else:
    print("\n⚠ Result is BELOW typical literature values.")

print("\n" + "=" * 60)
print("Analysis Complete!")
print("=" * 60)