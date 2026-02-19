#!/usr/bin/env python3
"""
NTL-GDP Regression Analysis for Shanghai (2013-2022)
Multiple regression models: OLS, Ridge, Lasso, Random Forest
Evaluates models using R² and RMSE, selects best-fitting model.
"""

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.linear_model import LinearRegression, Ridge, Lasso
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import r2_score, mean_squared_error
from sklearn.preprocessing import StandardScaler
from storage_manager import storage_manager

# ============================================================
# Step 1: Prepare ANTL and GDP data
# ============================================================

# ANTL values extracted from NTL raster statistics (2013-2022)
years = [2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022]
antl_values = [
    12.6935,  # 2013
    12.3080,  # 2014
    12.6828,  # 2015
    12.6039,  # 2016
    13.9421,  # 2017
    13.6770,  # 2018
    14.2958,  # 2019
    14.4234,  # 2020
    14.9202,  # 2021
    14.8432   # 2022
]

# GDP values (billion yuan) from Shanghai Municipal Statistics Bureau
gdp_values = [
    2160.21,  # 2013
    2356.77,  # 2014
    2512.34,  # 2015
    2746.61,  # 2016
    3063.30,  # 2017
    3267.99,  # 2018
    3815.53,  # 2019
    3870.06,  # 2020
    4321.45,  # 2021
    4465.28   # 2022
]

# Create DataFrame
df = pd.DataFrame({
    'Year': years,
    'ANTL': antl_values,
    'GDP_billion_yuan': gdp_values
})

# Prepare features (X) and target (y)
X = df[['ANTL']].values
y = df['GDP_billion_yuan'].values

# ============================================================
# Step 2: Fit multiple regression models
# ============================================================

# Initialize models
models = {
    'OLS': LinearRegression(),
    'Ridge': Ridge(alpha=1.0),
    'Lasso': Lasso(alpha=0.1),
    'Random Forest': RandomForestRegressor(n_estimators=100, random_state=42)
}

# Store results
results = []

for name, model in models.items():
    # Fit model
    model.fit(X, y)
    
    # Predict
    y_pred = model.predict(X)
    
    # Calculate metrics
    r2 = r2_score(y, y_pred)
    rmse = np.sqrt(mean_squared_error(y, y_pred))
    
    # Get coefficients
    if hasattr(model, 'coef_'):
        coef = model.coef_[0] if hasattr(model.coef_, '__len__') else model.coef_
        intercept = model.intercept_
    else:
        coef = np.nan
        intercept = np.nan
    
    results.append({
        'Model': name,
        'R2': r2,
        'RMSE': rmse,
        'Coefficient': coef,
        'Intercept': intercept
    })
    
    print(f"{name}: R² = {r2:.6f}, RMSE = {rmse:.4f}")

# Create results DataFrame
results_df = pd.DataFrame(results)

# ============================================================
# Step 3: Select best model
# ============================================================

# Best model by R² (highest)
best_model_r2 = results_df.loc[results_df['R2'].idxmax()]
print(f"\nBest model by R²: {best_model_r2['Model']} (R² = {best_model_r2['R2']:.6f})")

# Best model by RMSE (lowest)
best_model_rmse = results_df.loc[results_df['RMSE'].idxmin()]
print(f"Best model by RMSE: {best_model_rmse['Model']} (RMSE = {best_model_rmse['RMSE']:.4f})")

# Overall best (using R² as primary criterion)
best_model_name = best_model_r2['Model']
print(f"\nSelected best-fitting model: {best_model_name}")

# ============================================================
# Step 4: Save results to CSV
# ============================================================

output_csv_path = storage_manager.resolve_output_path('ntl_gdp_regression_results.csv')
results_df.to_csv(output_csv_path, index=False)
print(f"\nRegression results saved to: {output_csv_path}")

# Save detailed predictions
detailed_results = df.copy()
for name, model in models.items():
    detailed_results[f'{name}_Prediction'] = model.predict(X)
    detailed_results[f'{name}_Residual'] = y - model.predict(X)

detailed_csv_path = storage_manager.resolve_output_path('ntl_gdp_detailed_predictions.csv')
detailed_results.to_csv(detailed_csv_path, index=False)
print(f"Detailed predictions saved to: {detailed_csv_path}")

# ============================================================
# Step 5: Create visualization
# ============================================================

fig, axes = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle('NTL-GDP Regression Analysis for Shanghai (2013-2022)', fontsize=14, fontweight='bold')

# Scatter plot with regression lines
ax = axes[0, 0]
ax.scatter(X, y, color='black', s=80, label='Actual Data', zorder=5)

colors = {'OLS': 'blue', 'Ridge': 'green', 'Lasso': 'orange', 'Random Forest': 'red'}
linestyles = {'OLS': '-', 'Ridge': '--', 'Lasso': '-.', 'Random Forest': ':'}

X_range = np.linspace(X.min() - 0.5, X.max() + 0.5, 100).reshape(-1, 1)
for name, model in models.items():
    y_range = model.predict(X_range)
    ax.plot(X_range, y_range, color=colors[name], linestyle=linestyles[name], 
            linewidth=2, label=f"{name} (R²={results_df[results_df['Model']==name]['R2'].values[0]:.4f})")

ax.set_xlabel('ANTL (Annual Nighttime Light)', fontsize=11)
ax.set_ylabel('GDP (billion yuan)', fontsize=11)
ax.set_title('Regression Models Comparison', fontsize=12)
ax.legend(loc='upper left', fontsize=9)
ax.grid(True, alpha=0.3)

# Residuals plot
ax = axes[0, 1]
for name, model in models.items():
    y_pred = model.predict(X)
    residuals = y - y_pred
    ax.scatter(y_pred, residuals, label=name, alpha=0.7, s=60)

ax.axhline(y=0, color='black', linestyle='--', linewidth=1)
ax.set_xlabel('Predicted GDP', fontsize=11)
ax.set_ylabel('Residuals', fontsize=11)
ax.set_title('Residual Analysis', fontsize=12)
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)

# Model performance comparison
ax = axes[1, 0]
model_names = results_df['Model'].tolist()
r2_values = results_df['R2'].tolist()
rmse_values = results_df['RMSE'].tolist()

x_pos = np.arange(len(model_names))
width = 0.35

bars1 = ax.bar(x_pos - width/2, r2_values, width, label='R²', color='steelblue')
ax2 = ax.twinx()
bars2 = ax2.bar(x_pos + width/2, rmse_values, width, label='RMSE', color='coral')

ax.set_xlabel('Model', fontsize=11)
ax.set_ylabel('R²', color='steelblue', fontsize=11)
ax2.set_ylabel('RMSE', color='coral', fontsize=11)
ax.set_title('Model Performance Comparison', fontsize=12)
ax.set_xticks(x_pos)
ax.set_xticklabels(model_names, rotation=15)
ax.legend(loc='upper left', fontsize=9)
ax2.legend(loc='upper right', fontsize=9)
ax.grid(True, alpha=0.3, axis='y')

# Highlight best model
best_idx = results_df['R2'].idxmax()
ax.bar(best_idx - width/2, r2_values[best_idx], width, color='darkgreen', alpha=0.7, label='Best R²')

# Time series comparison
ax = axes[1, 1]
ax.plot(years, y, 'ko-', linewidth=2, markersize=8, label='Actual GDP')

for name, model in models.items():
    y_pred = model.predict(X)
    ax.plot(years, y_pred, marker='o', linestyle=linestyles[name], linewidth=1.5, 
            markersize=6, label=f"{name}", color=colors[name], alpha=0.8)

ax.set_xlabel('Year', fontsize=11)
ax.set_ylabel('GDP (billion yuan)', fontsize=11)
ax.set_title('GDP Time Series: Actual vs Predicted', fontsize=12)
ax.legend(loc='upper left', fontsize=9)
ax.grid(True, alpha=0.3)
ax.set_xticks(years)

plt.tight_layout()

# Save figure
output_png_path = storage_manager.resolve_output_path('ntl_gdp_regression_analysis.png')
plt.savefig(output_png_path, dpi=150, bbox_inches='tight')
print(f"Visualization saved to: {output_png_path}")

# ============================================================
# Step 6: Print summary
# ============================================================

print("\n" + "="*60)
print("REGRESSION ANALYSIS SUMMARY")
print("="*60)
print(f"\nStudy Area: Shanghai, China")
print(f"Time Period: 2013-2022 (10 years)")
print(f"\nANTL Range: {min(antl_values):.4f} - {max(antl_values):.4f}")
print(f"GDP Range: {min(gdp_values):.2f} - {max(gdp_values):.2f} billion yuan")
print("\nModel Performance:")
print(results_df.to_string(index=False))
print(f"\n*** BEST-FITTING MODEL: {best_model_name} ***")
print(f"    R² = {best_model_r2['R2']:.6f}")
print(f"    RMSE = {best_model_r2['RMSE']:.4f} billion yuan")
print("="*60)
