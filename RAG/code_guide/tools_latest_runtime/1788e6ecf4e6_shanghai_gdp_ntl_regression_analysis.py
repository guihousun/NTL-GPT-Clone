"""
Shanghai GDP-ANTL Regression Analysis (2013-2022)
Multiple regression models with comprehensive model selection
"""
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.linear_model import LinearRegression, Ridge, Lasso
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import cross_val_score, KFold
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error
from scipy import stats
import json
from storage_manager import storage_manager

# ==================== Data Loading ====================
antl_path = storage_manager.resolve_output_path('shanghai_ANTL_statistics_2013_2022.csv')
gdp_path = storage_manager.resolve_input_path('shanghai_gdp_2013_2022.csv')

antl_df = pd.read_csv(antl_path)
gdp_df = pd.read_csv(gdp_path)

# Merge on year
merged = antl_df.merge(gdp_df, left_on='Year', right_on='year', how='inner')
print("Merged data shape:", merged.shape)
print(merged[['Year', 'ANTL', 'value_100m_cny']])

# Prepare X and y
X = merged['ANTL'].values.reshape(-1, 1)
y = merged['value_100m_cny'].values
years = merged['Year'].values

# Log-transformed data for log-log model
X_log = np.log(X).reshape(-1, 1)
y_log = np.log(y)

# ==================== Model Definitions ====================
models = {
    'OLS': LinearRegression(),
    'Ridge': Ridge(alpha=1.0),
    'Lasso': Lasso(alpha=0.1),
    'RandomForest': RandomForestRegressor(n_estimators=100, random_state=42),
    'LogLog': LinearRegression(),  # Will fit on log-transformed data
    'Exponential': LinearRegression()  # Will fit log(y) ~ X
}

# Models that don't have coef_ (tree-based)
non_linear_models = ['RandomForest']

# ==================== Model Fitting and Evaluation ====================
results = []
predictions = {}

for name, model in models.items():
    if name == 'LogLog':
        # Fit log(GDP) ~ log(ANTL)
        model.fit(X_log, y_log)
        y_pred_log = model.predict(X_log)
        y_pred = np.exp(y_pred_log)
    elif name == 'Exponential':
        # Fit log(GDP) ~ ANTL, then GDP ~ exp(ANTL)
        model.fit(X, y_log)
        y_pred_log = model.predict(X)
        y_pred = np.exp(y_pred_log)
    else:
        model.fit(X, y)
        y_pred = model.predict(X)
    
    predictions[name] = y_pred
    
    # Calculate metrics
    r2 = r2_score(y, y_pred)
    rmse = np.sqrt(mean_squared_error(y, y_pred))
    mae = mean_absolute_error(y, y_pred)
    
    # Adjusted R2 (for single predictor, same as R2 but keeping for consistency)
    n = len(y)
    p = 1  # number of predictors
    adj_r2 = 1 - (1 - r2) * (n - 1) / (n - p - 1)
    
    # AIC and BIC
    rss = np.sum((y - y_pred) ** 2)
    aic = n * np.log(rss / n) + 2 * p
    bic = n * np.log(rss / n) + p * np.log(n)
    
    # Cross-validation (5-fold)
    cv_scores = cross_val_score(model, X_log if name == 'LogLog' else X, 
                                 y_log if name in ['LogLog', 'Exponential'] else y, 
                                 cv=5, scoring='r2')
    cv_mean = cv_scores.mean()
    cv_std = cv_scores.std()
    
    # Get coefficients (handle tree-based models)
    if name in non_linear_models:
        coef = None
        intercept = None
    elif name in ['LogLog', 'Exponential']:
        coef = model.coef_[0]
        intercept = model.intercept_
    else:
        coef = model.coef_[0]
        intercept = model.intercept_
    
    results.append({
        'Model': name,
        'R2': r2,
        'Adjusted_R2': adj_r2,
        'AIC': aic,
        'BIC': bic,
        'RMSE': rmse,
        'MAE': mae,
        'CV_Mean_R2': cv_mean,
        'CV_Std_R2': cv_std,
        'Coefficient': coef,
        'Intercept': intercept
    })
    
    print(f"\n{name}:")
    print(f"  R² = {r2:.6f}, Adj R² = {adj_r2:.6f}")
    print(f"  AIC = {aic:.2f}, BIC = {bic:.2f}")
    print(f"  RMSE = {rmse:.2f}, MAE = {mae:.2f}")
    print(f"  CV R² = {cv_mean:.4f} (+/- {cv_std:.4f})")

# ==================== Model Selection ====================
results_df = pd.DataFrame(results)

# Composite score: higher R2 is better, lower AIC/BIC is better
# Normalize AIC and BIC for comparison
results_df['AIC_norm'] = (results_df['AIC'] - results_df['AIC'].min()) / (results_df['AIC'].max() - results_df['AIC'].min() + 1e-10)
results_df['BIC_norm'] = (results_df['BIC'] - results_df['BIC'].min()) / (results_df['BIC'].max() - results_df['BIC'].min() + 1e-10)
results_df['RMSE_norm'] = (results_df['RMSE'] - results_df['RMSE'].min()) / (results_df['RMSE'].max() - results_df['RMSE'].min() + 1e-10)

# Composite score: weighted combination (higher is better)
results_df['Composite_Score'] = (
    0.4 * results_df['R2'] + 
    0.2 * (1 - results_df['AIC_norm']) + 
    0.2 * (1 - results_df['BIC_norm']) + 
    0.2 * (1 - results_df['RMSE_norm'])
)

# Rank models
results_df = results_df.sort_values('Composite_Score', ascending=False)
results_df['Rank'] = range(1, len(results_df) + 1)

best_model_name = results_df.iloc[0]['Model']
print(f"\n{'='*50}")
print(f"BEST MODEL: {best_model_name}")
print(f"{'='*50}")
print(results_df[['Model', 'Rank', 'R2', 'AIC', 'BIC', 'RMSE', 'Composite_Score']].to_string(index=False))

# ==================== Diagnostic Plots ====================
fig, axes = plt.subplots(2, 2, figsize=(14, 10))

# Plot 1: Actual vs Predicted for all models
ax1 = axes[0, 0]
for name in models.keys():
    ax1.scatter(y, predictions[name], label=name, alpha=0.7, s=60)
ax1.plot([y.min(), y.max()], [y.min(), y.max()], 'k--', linewidth=2, label='Perfect fit')
ax1.set_xlabel('Actual GDP (100 million CNY)')
ax1.set_ylabel('Predicted GDP (100 million CNY)')
ax1.set_title('Actual vs Predicted GDP by Model')
ax1.legend(loc='upper left')
ax1.grid(True, alpha=0.3)

# Plot 2: Residuals for best model
ax2 = axes[0, 1]
best_pred = predictions[best_model_name]
residuals = y - best_pred
ax2.scatter(best_pred, residuals, alpha=0.7, s=60, color='darkblue')
ax2.axhline(y=0, color='red', linestyle='--', linewidth=2)
ax2.set_xlabel('Predicted GDP (100 million CNY)')
ax2.set_ylabel('Residuals')
ax2.set_title(f'Residuals Plot ({best_model_name})')
ax2.grid(True, alpha=0.3)

# Plot 3: Q-Q Plot for best model
ax3 = axes[1, 0]
stats.probplot(residuals, dist="norm", plot=ax3)
ax3.set_title(f'Q-Q Plot of Residuals ({best_model_name})')
ax3.grid(True, alpha=0.3)

# Plot 4: Model comparison (R² and RMSE)
ax4 = axes[1, 1]
x_pos = np.arange(len(results_df))
width = 0.35
ax4.bar(x_pos - width/2, results_df['R2'], width, label='R²', color='steelblue')
ax4_twin = ax4.twinx()
ax4_twin.bar(x_pos + width/2, results_df['RMSE'], width, label='RMSE', color='coral')
ax4.set_xticks(x_pos)
ax4.set_xticklabels(results_df['Model'], rotation=45, ha='right')
ax4.set_ylabel('R²')
ax4_twin.set_ylabel('RMSE')
ax4.set_title('Model Comparison: R² and RMSE')
ax4.legend(loc='upper left')
ax4_twin.legend(loc='upper right')
ax4.grid(True, alpha=0.3, axis='y')

plt.tight_layout()
plot_path = storage_manager.resolve_output_path('shanghai_gdp_ntl_regression_diagnostic.png')
plt.savefig(plot_path, dpi=150, bbox_inches='tight')
plt.close()
print(f"\nDiagnostic plot saved to: {plot_path}")

# ==================== Time Series Visualization ====================
fig, ax = plt.subplots(figsize=(12, 6))
ax.plot(years, y, 'ko-', label='Actual GDP', linewidth=2, markersize=8)
for name in models.keys():
    ax.plot(years, predictions[name], '--', label=f'{name} Prediction', alpha=0.7)
ax.set_xlabel('Year')
ax.set_ylabel('GDP (100 million CNY)')
ax.set_title('Shanghai GDP: Actual vs Model Predictions (2013-2022)')
ax.legend(loc='upper left')
ax.grid(True, alpha=0.3)
ts_plot_path = storage_manager.resolve_output_path('shanghai_gdp_timeseries_comparison.png')
plt.savefig(ts_plot_path, dpi=150, bbox_inches='tight')
plt.close()
print(f"Time series plot saved to: {ts_plot_path}")

# ==================== Save Results ====================
# Save detailed results
results_output_path = storage_manager.resolve_output_path('shanghai_GDP_Regression_Analysis_Report.csv')
results_df.to_csv(results_output_path, index=False)
print(f"\nRegression analysis report saved to: {results_output_path}")

# Save model comparison summary as JSON
summary = {
    'best_model': best_model_name,
    'best_model_metrics': results_df.iloc[0][['R2', 'Adjusted_R2', 'AIC', 'BIC', 'RMSE', 'MAE', 'CV_Mean_R2']].to_dict(),
    'all_models_ranking': results_df[['Model', 'Rank', 'R2', 'AIC', 'BIC', 'RMSE', 'Composite_Score']].to_dict('records'),
    'data_info': {
        'years': years.tolist(),
        'ANTL_range': [float(X.min()), float(X.max())],
        'GDP_range': [float(y.min()), float(y.max())],
        'n_observations': len(y)
    }
}
summary_path = storage_manager.resolve_output_path('shanghai_model_comparison_summary.json')
with open(summary_path, 'w') as f:
    json.dump(summary, f, indent=2)
print(f"Model comparison summary saved to: {summary_path}")

print("\n" + "="*50)
print("ANALYSIS COMPLETE")
print("="*50)
print(f"Best Model: {best_model_name}")
print(f"Best R²: {results_df.iloc[0]['R2']:.6f}")
print(f"Best RMSE: {results_df.iloc[0]['RMSE']:.2f} (100 million CNY)")
print(f"Output files:")
print(f"  - {results_output_path}")
print(f"  - {summary_path}")
print(f"  - {plot_path}")
print(f"  - {ts_plot_path}")
