"""
Shanghai GDP-ANTL Regression Analysis (2013-2022)
Analyzes the relationship between Annual Nighttime Light (ANTL) and GDP
using multiple regression models: OLS, Ridge, Lasso, and Random Forest.
Selects the best-fitting model based on R² and RMSE.
"""

from storage_manager import storage_manager
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.linear_model import LinearRegression, Ridge, Lasso
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import r2_score, mean_squared_error

# =============================================================================
# 1. Data Loading
# =============================================================================
gdp_path = storage_manager.resolve_input_path('shanghai_gdp_2013_2022.csv')
ntl_stats_path = storage_manager.resolve_output_path('shanghai_ntl_stats_2013_2022.csv')
output_csv = storage_manager.resolve_output_path('shanghai_gdp_antl_regression_results.csv')
output_png = storage_manager.resolve_output_path('shanghai_gdp_antl_regression_plot.png')

# Load data
gdp_df = pd.read_csv(gdp_path)
ntl_df = pd.read_csv(ntl_stats_path)

# Merge on year
merged_df = pd.merge(gdp_df, ntl_df, left_on='year', right_on='Year')

# Prepare features and target
X = merged_df[['ANTL']].values  # Feature: ANTL
y = merged_df['value_100m_cny'].values  # Target: GDP (100 million CNY)
years = merged_df['year'].values

print("=" * 60)
print("Shanghai GDP-ANTL Regression Analysis (2013-2022)")
print("=" * 60)
print(f"\nData loaded: {len(merged_df)} years")
print(f"ANTL range: {X.min():.4f} - {X.max():.4f}")
print(f"GDP range: {y.min():.2f} - {y.max():.2f} (100 million CNY)")

# =============================================================================
# 2. Model Fitting and Evaluation
# =============================================================================
models = {
    'OLS': LinearRegression(),
    'Ridge': Ridge(alpha=1.0),
    'Lasso': Lasso(alpha=0.1),
    'RandomForest': RandomForestRegressor(n_estimators=100, random_state=42)
}

results = []
predictions = {}

print("\n" + "-" * 60)
print("Model Performance Comparison")
print("-" * 60)

for name, model in models.items():
    model.fit(X, y)
    y_pred = model.predict(X)
    r2 = r2_score(y, y_pred)
    rmse = np.sqrt(mean_squared_error(y, y_pred))
    mae = np.mean(np.abs(y - y_pred))
    
    results.append({
        'Model': name,
        'R2': r2,
        'RMSE': rmse,
        'MAE': mae
    })
    predictions[name] = y_pred
    
    print(f"{name:15s}: R²={r2:.6f}, RMSE={rmse:.2f}, MAE={mae:.2f}")

results_df = pd.DataFrame(results)

# =============================================================================
# 3. Best Model Selection
# =============================================================================
# Select best model based on highest R² (and lowest RMSE as tiebreaker)
best_idx = results_df['R2'].idxmax()
best_model_name = results_df.loc[best_idx, 'Model']
best_r2 = results_df.loc[best_idx, 'R2']
best_rmse = results_df.loc[best_idx, 'RMSE']

print("\n" + "=" * 60)
print(f"BEST MODEL: {best_model_name}")
print(f"  R² = {best_r2:.6f}")
print(f"  RMSE = {best_rmse:.2f} (100 million CNY)")
print("=" * 60)

# Get best model coefficients
best_model = models[best_model_name]
if hasattr(best_model, 'coef_'):
    coef = best_model.coef_[0]
    intercept = best_model.intercept_
    print(f"\nModel equation: GDP = {coef:.4f} × ANTL + {intercept:.4f}")

# =============================================================================
# 4. Save Results to CSV
# =============================================================================
# Save model comparison results
results_df.to_csv(output_csv, index=False)
print(f"\nModel comparison saved to: {output_csv}")

# Save detailed predictions
predictions_df = pd.DataFrame({
    'Year': years,
    'ANTL': X.flatten(),
    'Actual_GDP': y,
    'OLS_Pred': predictions['OLS'],
    'Ridge_Pred': predictions['Ridge'],
    'Lasso_Pred': predictions['Lasso'],
    'RF_Pred': predictions['RandomForest']
})
predictions_csv = storage_manager.resolve_output_path('shanghai_gdp_antl_predictions.csv')
predictions_df.to_csv(predictions_csv, index=False)
print(f"Predictions saved to: {predictions_csv}")

# =============================================================================
# 5. Visualization
# =============================================================================
fig, axes = plt.subplots(2, 2, figsize=(14, 10))

# Plot 1: Actual vs Predicted GDP for all models
ax1 = axes[0, 0]
ax1.plot(years, y, 'ko-', linewidth=2, markersize=8, label='Actual GDP')
ax1.plot(years, predictions['OLS'], 'b--', linewidth=1.5, label=f'OLS (R²={results_df.loc[0, "R2"]:.4f})')
ax1.plot(years, predictions['Ridge'], 'g--', linewidth=1.5, label=f'Ridge (R²={results_df.loc[1, "R2"]:.4f})')
ax1.plot(years, predictions['Lasso'], 'r--', linewidth=1.5, label=f'Lasso (R²={results_df.loc[2, "R2"]:.4f})')
ax1.plot(years, predictions['RandomForest'], 'm--', linewidth=1.5, label=f'RF (R²={results_df.loc[3, "R2"]:.4f})')
ax1.set_xlabel('Year', fontsize=12)
ax1.set_ylabel('GDP (100 million CNY)', fontsize=12)
ax1.set_title('Actual vs Predicted GDP by Model', fontsize=14, fontweight='bold')
ax1.legend(loc='upper left', fontsize=9)
ax1.grid(True, alpha=0.3)

# Plot 2: Scatter plot with best model fit
ax2 = axes[0, 1]
ax2.scatter(X, y, s=100, c='blue', alpha=0.7, edgecolors='black', linewidth=1.5, label='Observations')

# Plot best model regression line
X_sorted = np.linspace(X.min(), X.max(), 100).reshape(-1, 1)
if best_model_name == 'RandomForest':
    y_sorted = best_model.predict(X_sorted)
    ax2.plot(X_sorted, y_sorted, 'r-', linewidth=2.5, label=f'{best_model_name} Fit (R²={best_r2:.4f})')
else:
    y_sorted = best_model.coef_[0] * X_sorted + best_model.intercept_
    ax2.plot(X_sorted, y_sorted, 'r-', linewidth=2.5, label=f'{best_model_name} Fit (R²={best_r2:.4f})')

ax2.set_xlabel('ANTL (Annual Nighttime Light)', fontsize=12)
ax2.set_ylabel('GDP (100 million CNY)', fontsize=12)
ax2.set_title(f'GDP vs ANTL - Best Model: {best_model_name}', fontsize=14, fontweight='bold')
ax2.legend(fontsize=11)
ax2.grid(True, alpha=0.3)

# Plot 3: Model comparison bar chart (R²)
ax3 = axes[1, 0]
model_names = results_df['Model'].tolist()
r2_values = results_df['R2'].tolist()
colors = ['steelblue', 'forestgreen', 'crimson', 'purple']
bars = ax3.bar(model_names, r2_values, color=colors, edgecolor='black', linewidth=1.2)
ax3.set_ylabel('R² Score', fontsize=12)
ax3.set_title('Model Comparison - R² Scores', fontsize=14, fontweight='bold')
ax3.set_ylim(0, 1.0)
ax3.axhline(y=best_r2, color='red', linestyle='--', linewidth=2, alpha=0.7, label=f'Best: {best_r2:.4f}')
ax3.legend(fontsize=10)
for bar, val in zip(bars, r2_values):
    ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01, 
             f'{val:.4f}', ha='center', va='bottom', fontsize=10, fontweight='bold')
ax3.grid(True, alpha=0.3, axis='y')

# Plot 4: RMSE comparison
ax4 = axes[1, 1]
rmse_values = results_df['RMSE'].tolist()
bars = ax4.bar(model_names, rmse_values, color=colors, edgecolor='black', linewidth=1.2)
ax4.set_ylabel('RMSE (100 million CNY)', fontsize=12)
ax4.set_title('Model Comparison - RMSE', fontsize=14, fontweight='bold')
ax4.axhline(y=best_rmse, color='red', linestyle='--', linewidth=2, alpha=0.7, label=f'Best: {best_rmse:.2f}')
ax4.legend(fontsize=10)
for bar, val in zip(bars, rmse_values):
    ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 50, 
             f'{val:.1f}', ha='center', va='bottom', fontsize=10, fontweight='bold')
ax4.grid(True, alpha=0.3, axis='y')

plt.tight_layout()
plt.savefig(output_png, dpi=150, bbox_inches='tight')
plt.close()
print(f"Visualization saved to: {output_png}")

# =============================================================================
# 6. Summary Report
# =============================================================================
print("\n" + "=" * 60)
print("ANALYSIS SUMMARY")
print("=" * 60)
print(f"Study Area: Shanghai, China")
print(f"Time Period: 2013-2022 (10 years)")
print(f"Data Source: NPP-VIIRS-Like NTL + NBS Official GDP")
print(f"\nBest Model: {best_model_name}")
print(f"  - R²: {best_r2:.6f} ({best_r2*100:.2f}% variance explained)")
print(f"  - RMSE: {best_rmse:.2f} (100 million CNY)")
print(f"\nInterpretation:")
print(f"  The {best_model_name} model demonstrates the strongest relationship")
print(f"  between ANTL and GDP for Shanghai during 2013-2022.")
if best_model_name == 'RandomForest':
    print(f"  This suggests nonlinear relationships exist between nighttime light")
    print(f"  intensity and economic output.")
else:
    print(f"  This indicates a predominantly linear relationship between ANTL and GDP.")
print("=" * 60)