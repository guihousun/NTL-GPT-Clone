# # from tools import Engineer_tools, Code_tools, data_searcher_tools
    
# # from langchain_core.tools import StructuredTool
# # import types

# # import types
# # from langchain_core.tools import StructuredTool

# # # 假设 Engineer_tools 已经从 tools 模块导入
# # # from tools import Engineer_tools

# # # 提取名称并构建字典
# # TOOL_REGISTRY = {}

# # for tool in Engineer_tools:
# #     # 1. 获取工具的唯一名称
# #     if isinstance(tool, StructuredTool):
# #         name = tool.name
# #     elif isinstance(tool, types.FunctionType):
# #         name = tool.__name__
# #     else:
# #         # 兜底方案：尝试获取 name 属性或转为字符串
# #         name = getattr(tool, 'name', str(tool))
    
# #     # 2. 映射名称到工具对象本身
# #     TOOL_REGISTRY[name] = tool

# # # 打印生成的字典键值对以供确认
# # print("成功构建 TOOL_REGISTRY:")
# # for name in TOOL_REGISTRY.keys():
# #     print(f"  - {name}")

# # # 现在你可以这样使用：
# # # selected_tool = TOOL_REGISTRY["NTL_Knowledge_Base"]

# import rasterio
# import numpy as np
# import geopandas as gpd
# import matplotlib.pyplot as plt
# from rasterio.features import geometry_mask
# from storage_manager import storage_manager

# # Resolve paths
# ntl_path = storage_manager.resolve_input_path('ntl_shanghai_2020.tif')
# boundary_path = storage_manager.resolve_input_path('shanghai_boundary.shp')

# # Load data
# dataset = rasterio.open(ntl_path)
# raster = dataset.read(1)
# city_boundary = gpd.read_file(boundary_path)

# # Create mask for city boundary
# mask = geometry_mask([geom for geom in city_boundary.geometry],
#                      transform=dataset.transform,
#                      invert=True,
#                      out_shape=dataset.shape)

# # Mask pixels outside city
# raster_masked = np.where(mask, raster, np.nan)

# # Define threshold
# threshold = 0.1

# # Identify pixels above threshold
# bright_pixels = raster_masked > threshold

# # Calculate pixel area (m^2)
# pixel_area = abs(dataset.transform.a * dataset.transform.e) * (111319.49079327358 ** 2) # Convert degrees to meters at equator

# # Calculate total bright pixel area
# bright_area = np.nansum(bright_pixels) * pixel_area

# # Calculate total city area
# city_area = np.nansum(mask) * pixel_area

# # Calculate proportion
# proportion = bright_area / city_area if city_area > 0 else np.nan

# # Print results
# print(f'Total area of pixels with NTL > 0.1: {bright_area:.2f} square meters')
# print(f'Proportion of Shanghai\'s area with NTL > 0.1: {proportion:.4f}')

# # Visualization
# plt.figure(figsize=(10, 8))
# plt.imshow(raster_masked, cmap='hot', vmin=0, vmax=np.nanmax(raster_masked))
# plt.colorbar(label='NTL Radiance')
# plt.title('Shanghai NTL 2020 (Masked by City Boundary)')
# plt.xlabel('Pixel Column')
# plt.ylabel('Pixel Row')
# plt.savefig(storage_manager.resolve_output_path('shanghai_ntl_2020_masked.png'))
# plt.show()

# from storage_manager import storage_manager
# import pandas as pd
# import matplotlib.pyplot as plt
# import seaborn as sns
# import statsmodels.api as sm
# from sklearn.model_selection import train_test_split
# from sklearn.metrics import r2_score, mean_squared_error
# import numpy as np

# # STEP 1 — DATA LOADING AND PREPARATION
# # Load the ANTL and GDP data
# antl_path = storage_manager.resolve_output_path('Shanghai_ANTL_Statistics_2013_2022.csv')
# gdp_path = storage_manager.resolve_output_path('Shanghai_GDP_2013_2022.csv')

# df_antl = pd.read_csv(antl_path)
# df_gdp = pd.read_csv(gdp_path)

# # Merge the datasets on Year (since both have 'Year' column)
# df_merged = pd.merge(df_antl, df_gdp, on=['Year', 'Region'])

# print("Merged Data:")
# print(df_merged.head())
# print(f"\nData shape: {df_merged.shape}")

# # STEP 2 — EXPLORATORY DATA ANALYSIS
# # Create a scatter plot to visualize the relationship between ANTL and GDP
# plt.figure(figsize=(10, 6))
# sns.scatterplot(data=df_merged, x='ANTL', y='GDP', hue='Year', size='Year', sizes=(50, 200))
# plt.title('Relationship between Annual Average Nighttime Light (ANTL) and GDP in Shanghai (2013-2022)')
# plt.xlabel('Annual Average Nighttime Light (ANTL)')
# plt.ylabel('GDP (billion RMB)')
# plt.grid(True, alpha=0.3)

# # Save the plot
# plot_path = storage_manager.resolve_output_path('Shanghai_ANTL_vs_GDP_Scatter.png')
# plt.savefig(plot_path, dpi=300, bbox_inches='tight')
# plt.show()

# # STEP 3 — MULTIPLE REGRESSION ANALYSIS
# # Since we only have one predictor (ANTL), we'll create additional features for multiple regression
# # Create polynomial features and log transformations to test different models

# # Add log-transformed variables
# df_merged['log_ANTL'] = np.log(df_merged['ANTL'])
# df_merged['log_GDP'] = np.log(df_merged['GDP'])

# # Add polynomial features
# df_merged['ANTL_squared'] = df_merged['ANTL'] ** 2
# df_merged['ANTL_cubed'] = df_merged['ANTL'] ** 3

# print("\nData with additional features:")
# print(df_merged.head())

# # Model 1: Simple linear regression (GDP ~ ANTL)
# X1 = sm.add_constant(df_merged['ANTL'])
# y1 = df_merged['GDP']
# model1 = sm.OLS(y1, X1).fit()

# # Model 2: Log-linear regression (log(GDP) ~ log(ANTL))
# X2 = sm.add_constant(df_merged['log_ANTL'])
# y2 = df_merged['log_GDP']
# model2 = sm.OLS(y2, X2).fit()

# # Model 3: Polynomial regression (GDP ~ ANTL + ANTL²)
# X3 = sm.add_constant(df_merged[['ANTL', 'ANTL_squared']])
# y3 = df_merged['GDP']
# model3 = sm.OLS(y3, X3).fit()

# # Model 4: Full polynomial regression (GDP ~ ANTL + ANTL² + ANTL³)
# X4 = sm.add_constant(df_merged[['ANTL', 'ANTL_squared', 'ANTL_cubed']])
# y4 = df_merged['GDP']
# model4 = sm.OLS(y4, X4).fit()

# # STEP 4 — MODEL COMPARISON AND SELECTION
# print("\n" + "="*60)
# print("MODEL COMPARISON")
# print("="*60)

# models = [
#     ("Simple Linear Regression (GDP ~ ANTL)", model1),
#     ("Log-Linear Regression (log(GDP) ~ log(ANTL))", model2),
#     ("Polynomial Regression (GDP ~ ANTL + ANTL²)", model3),
#     ("Full Polynomial Regression (GDP ~ ANTL + ANTL² + ANTL³)", model4)
# ]

# results = []
# for name, model in models:
#     if "Log-Linear" in name:
#         # For log-linear model, calculate R² on original scale
#         y_pred_log = model.predict()
#         y_pred_original = np.exp(y_pred_log)
#         r2_original = r2_score(df_merged['GDP'], y_pred_original)
#         results.append({
#             'Model': name,
#             'R²': r2_original,
#             'Adj_R²': model.rsquared_adj,
#             'AIC': model.aic,
#             'BIC': model.bic
#         })
#         print(f"\n{name}:")
#         print(f"  R² (original scale): {r2_original:.4f}")
#         print(f"  Adjusted R²: {model.rsquared_adj:.4f}")
#         print(f"  AIC: {model.aic:.4f}")
#         print(f"  BIC: {model.bic:.4f}")
#     else:
#         results.append({
#             'Model': name,
#             'R²': model.rsquared,
#             'Adj_R²': model.rsquared_adj,
#             'AIC': model.aic,
#             'BIC': model.bic
#         })
#         print(f"\n{name}:")
#         print(f"  R²: {model.rsquared:.4f}")
#         print(f"  Adjusted R²: {model.rsquared_adj:.4f}")
#         print(f"  AIC: {model.aic:.4f}")
#         print(f"  BIC: {model.bic:.4f}")

# # Create a DataFrame for model comparison
# df_results = pd.DataFrame(results)
# df_results.to_csv(storage_manager.resolve_output_path('Model_Comparison_Results.csv'), index=False)

# print("\n" + "="*60)
# print("BEST MODEL SELECTION")
# print("="*60)

# # Select best model based on Adjusted R² (higher is better) and AIC/BIC (lower is better)
# best_model_idx = df_results['Adj_R²'].idxmax()
# best_model_name = df_results.loc[best_model_idx, 'Model']

# print(f"Best model based on Adjusted R²: {best_model_name}")
# print(f"Adjusted R²: {df_results.loc[best_model_idx, 'Adj_R²']:.4f}")
# print(f"AIC: {df_results.loc[best_model_idx, 'AIC']:.4f}")
# print(f"BIC: {df_results.loc[best_model_idx, 'BIC']:.4f}")

# # STEP 5 — VISUALIZE MODEL FITS
# fig, axes = plt.subplots(2, 2, figsize=(15, 12))
# fig.suptitle('Model Fits for ANTL vs GDP Relationship in Shanghai', fontsize=16)

# # Plot 1: Simple Linear Regression
# axes[0, 0].scatter(df_merged['ANTL'], df_merged['GDP'], color='blue', label='Actual')
# axes[0, 0].plot(df_merged['ANTL'], model1.predict(), color='red', label='Predicted')
# axes[0, 0].set_title(f'Simple Linear: R² = {model1.rsquared:.4f}')
# axes[0, 0].set_xlabel('ANTL')
# axes[0, 0].set_ylabel('GDP')
# axes[0, 0].legend()
# axes[0, 0].grid(True, alpha=0.3)

# # Plot 2: Log-Linear Regression
# axes[0, 1].scatter(df_merged['ANTL'], df_merged['GDP'], color='blue', label='Actual')
# # Transform predictions back to original scale
# y_pred_log = model2.predict(sm.add_constant(df_merged['log_ANTL']))
# y_pred_original = np.exp(y_pred_log)
# axes[0, 1].plot(df_merged['ANTL'], y_pred_original, color='red', label='Predicted')
# axes[0, 1].set_title(f'Log-Linear: R² = {r2_score(df_merged["GDP"], y_pred_original):.4f}')
# axes[0, 1].set_xlabel('ANTL')
# axes[0, 1].set_ylabel('GDP')
# axes[0, 1].legend()
# axes[0, 1].grid(True, alpha=0.3)

# # Plot 3: Polynomial Regression (quadratic)
# axes[1, 0].scatter(df_merged['ANTL'], df_merged['GDP'], color='blue', label='Actual')
# axes[1, 0].plot(df_merged['ANTL'], model3.predict(), color='red', label='Predicted')
# axes[1, 0].set_title(f'Polynomial (Degree 2): R² = {model3.rsquared:.4f}')
# axes[1, 0].set_xlabel('ANTL')
# axes[1, 0].set_ylabel('GDP')
# axes[1, 0].legend()
# axes[1, 0].grid(True, alpha=0.3)

# # Plot 4: Polynomial Regression (cubic)
# axes[1, 1].scatter(df_merged['ANTL'], df_merged['GDP'], color='blue', label='Actual')
# axes[1, 1].plot(df_merged['ANTL'], model4.predict(), color='red', label='Predicted')
# axes[1, 1].set_title(f'Polynomial (Degree 3): R² = {model4.rsquared:.4f}')
# axes[1, 1].set_xlabel('ANTL')
# axes[1, 1].set_ylabel('GDP')
# axes[1, 1].legend()
# axes[1, 1].grid(True, alpha=0.3)

# plt.tight_layout()
# model_comparison_plot_path = storage_manager.resolve_output_path('Model_Comparison_Plots.png')
# plt.savefig(model_comparison_plot_path, dpi=300, bbox_inches='tight')
# plt.show()

# # STEP 6 — SAVE DETAILED RESULTS
# # Save the best model's summary
# best_model_summary = f"""
# BEST MODEL SUMMARY
# ==================
# Model: {best_model_name}
# Adjusted R²: {df_results.loc[best_model_idx, 'Adj_R²']:.4f}
# AIC: {df_results.loc[best_model_idx, 'AIC']:.4f}
# BIC: {df_results.loc[best_model_idx, 'BIC']:.4f}

# Detailed Model Statistics:
# """

# if best_model_idx == 0:
#     best_model_summary += str(model1.summary())
# elif best_model_idx == 1:
#     best_model_summary += str(model2.summary())
# elif best_model_idx == 2:
#     best_model_summary += str(model3.summary())
# else:
#     best_model_summary += str(model4.summary())

# # Save to text file
# with open(storage_manager.resolve_output_path('Best_Model_Summary.txt'), 'w', encoding='utf-8') as f:
#     f.write(best_model_summary)

# print("\nAnalysis complete!")
# print(f"Scatter plot saved to: {plot_path}")
# print(f"Model comparison results saved to: {storage_manager.resolve_output_path('Model_Comparison_Results.csv')}")
# print(f"Model comparison plots saved to: {model_comparison_plot_path}")
# print(f"Best model summary saved to: {storage_manager.resolve_output_path('Best_Model_Summary.txt')}")

from dotenv import load_dotenv
load_dotenv()

from langchain.agents import create_agent


def get_weather(city: str) -> str:
    """Get weather for a given city."""
    return f"It's always sunny in {city}!"


agent = create_agent(
    model="openai:gpt-5-mini",
    tools=[get_weather],
    system_prompt="You are a helpful assistant",
)

# Run the agent
agent.invoke(
    {"messages": [{"role": "user", "content": "What is the weather in San Francisco?"}]}
)

{
  "status": "fail",
  "stdout": "---------------------------------------------------------------------------\nHttpError                                 Traceback (most recent call last)\nFile ~\\miniconda3\\envs\\ntlgpt\\Lib\\site-packages\\ee\\data.py:409, in _execute_cloud_call(call, num_retries)\n    408 try:\n--> 409   return call.execute(num_retries=num_retries)\n    410 except googleapiclient.errors.HttpError as e:\n\nFile ~\\miniconda3\\envs\\ntlgpt\\Lib\\site-packages\\googleapiclient\\_helpers.py:130, in positional.<locals>.positional_decorator.<locals>.positional_wrapper(*args, **kwargs)\n    129         logger.warning(message)\n--> 130 return wrapped(*args, **kwargs)\n\nFile ~\\miniconda3\\envs\\ntlgpt\\Lib\\site-packages\\googleapiclient\\http.py:938, in HttpRequest.execute(self, http, num_retries)\n    937 if resp.status >= 300:\n--> 938     raise HttpError(resp, content, uri=self.uri)\n    939 return self.postproc(resp, content)\n\nHttpError: <HttpError 400 when requesting https://earthengine.googleapis.com/v1/projects/empyrean-caster-430308-m2/value:compute?prettyPrint=false&alt=json returned \"Date: Bad date/time '2019-02-29'.\". Details: \"Date: Bad date/time '2019-02-29'.\">\n\nDuring handling of the above exception, another exception occurred:\n\nEEException                               Traceback (most recent call last)\nCell In[1], line 66\n     64 # Calculate means\n     65 mean_2020 = calculate_zonal_mean(img_2020)\n---> 66 mean_2019 = calculate_zonal_mean(img_2019)\n     68 # Only proceed if both values are valid\n     69 if mean_2020 is not None and mean_2019 is not None:\n\nCell In[1], line 37, in calculate_zonal_mean(image)\n     36 def calculate_zonal_mean(image):\n---> 37     if image.bandNames().size().getInfo() == 0:\n     38         return None\n     39     stats = image.reduceRegion(\n     40         reducer=ee.Reducer.mean(),\n     41         geometry=region_fc.geometry(),\n     42         scale=500,\n     43         maxPixels=1e9\n     44     )\n\nFile ~\\miniconda3\\envs\\ntlgpt\\Lib\\site-packages\\ee\\computedobject.py:107, in ComputedObject.getInfo(self)\n    101 def getInfo(self) -> Any | None:\n    102   \"\"\"Fetch and return information about this object.\n    103 \n    104   Returns:\n    105     The object can evaluate to anything.\n    106   \"\"\"\n--> 107   return data.computeValue(self)\n\nFile ~\\miniconda3\\envs\\ntlgpt\\Lib\\site-packages\\ee\\data.py:1128, in computeValue(obj)\n   1125 body = {'expression': serializer.encode(obj, for_cloud_api=True)}\n   1126 _maybe_populate_workload_tag(body)\n-> 1128 return _execute_cloud_call(\n   1129     _get_cloud_projects()\n   1130     .value()\n   1131     .compute(body=body, project=_get_projects_path(), prettyPrint=False)\n   1132 )['result']\n\nFile ~\\miniconda3\\envs\\ntlgpt\\Lib\\site-packages\\ee\\data.py:411, in _execute_cloud_call(call, num_retries)\n    409   return call.execute(num_retries=num_retries)\n    410 except googleapiclient.errors.HttpError as e:\n--> 411   raise _translate_cloud_exception(e)\n\nEEException: Date: Bad date/time '2019-02-29'.\n",
  "error_type": "EEException",
  "error_message": "Date: Bad date/time '2019-02-29'.",
  "traceback": "Traceback (most recent call last):\n  File \"C:\\Users\\27334\\miniconda3\\envs\\ntlgpt\\Lib\\site-packages\\ee\\data.py\", line 409, in _execute_cloud_call\n    return call.execute(num_retries=num_retries)\n           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n  File \"C:\\Users\\27334\\miniconda3\\envs\\ntlgpt\\Lib\\site-packages\\googleapiclient\\_helpers.py\", line 130, in positional_wrapper\n    return wrapped(*args, **kwargs)\n           ^^^^^^^^^^^^^^^^^^^^^^^^\n  File \"C:\\Users\\27334\\miniconda3\\envs\\ntlgpt\\Lib\\site-packages\\googleapiclient\\http.py\", line 938, in execute\n    raise HttpError(resp, content, uri=self.uri)\ngoogleapiclient.errors.HttpError: <HttpError 400 when requesting https://earthengine.googleapis.com/v1/projects/empyrean-caster-430308-m2/value:compute?prettyPrint=false&alt=json returned \"Date: Bad date/time '2019-02-29'.\". Details: \"Date: Bad date/time '2019-02-29'.\">\n\nDuring handling of the above exception, another exception occurred:\n\nTraceback (most recent call last):\n  File \"C:\\NTL-CHAT\\NTL-GPT-Clone\\tools\\NTL_Code_generation.py\", line 204, in _gee_run_cell\n    raise res.error_in_exec\n  File \"C:\\Users\\27334\\AppData\\Roaming\\Python\\Python312\\site-packages\\IPython\\core\\interactiveshell.py\", line 3701, in run_code\n    exec(code_obj, self.user_global_ns, self.user_ns)\n  File \"<ipython-input-1-843deb94eafa>\", line 66, in <module>\n    mean_2019 = calculate_zonal_mean(img_2019)\n                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n  File \"<ipython-input-1-843deb94eafa>\", line 37, in calculate_zonal_mean\n    if image.bandNames().size().getInfo() == 0:\n       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n  File \"C:\\Users\\27334\\miniconda3\\envs\\ntlgpt\\Lib\\site-packages\\ee\\computedobject.py\", line 107, in getInfo\n    return data.computeValue(self)\n           ^^^^^^^^^^^^^^^^^^^^^^^\n  File \"C:\\Users\\27334\\miniconda3\\envs\\ntlgpt\\Lib\\site-packages\\ee\\data.py\", line 1128, in computeValue\n    return _execute_cloud_call(\n           ^^^^^^^^^^^^^^^^^^^^\n  File \"C:\\Users\\27334\\miniconda3\\envs\\ntlgpt\\Lib\\site-packages\\ee\\data.py\", line 411, in _execute_cloud_call\n    raise _translate_cloud_exception(e)  # pylint: disable=raise-missing-from\n    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\nee.ee_exception.EEException: Date: Bad date/time '2019-02-29'.\n",
  "code": "project_id = 'empyrean-caster-430308-m2'\nee.Initialize(project=project_id)\nimport pandas as pd\nimport matplotlib.pyplot as plt\nfrom storage_manager import storage_manager\n\n# --- STEP 1: Define parameters and load data ---\n# Load the VNP46A2 daily NTL collection\nband_name = 'Gap_Filled_DNB_BRDF_Corrected_NTL'\ncollection = ee.ImageCollection('NASA/VIIRS/002/VNP46A2')\n\n# Define date ranges for 2019 and 2020 lockdown period\nstart_date_2019 = '2019-01-23'\nend_date_2019 = '2019-04-08'\nstart_date_2020 = '2020-01-23'\nend_date_2020 = '2020-04-08'\n\n# Fetch Wuhan city boundary from GEE\ncity_asset = \"projects/empyrean-caster-430308-m2/assets/city\"\nadmin_fc = ee.FeatureCollection(city_asset)\nname_prop = 'name'\nregion_fc = admin_fc.filter(ee.Filter.eq(name_prop, '\u6b66\u6c49\u5e02'))\n\n# Filter collections for Wuhan\ncol_2019 = collection.filterDate(start_date_2019, end_date_2019).filterBounds(region_fc)\ncol_2020 = collection.filterDate(start_date_2020, end_date_2020).filterBounds(region_fc)\n\n# --- STEP 2: Define helper functions ---\n# Function to get image for a specific date (YYYY-MM-DD)\ndef get_image_for_date(collection, target_date_str):\n    target_date = ee.Date(target_date_str)\n    filtered = collection.filterDate(target_date, target_date.advance(1, 'day'))\n    return ee.Image(filtered.first())\n\n# Function to calculate zonal mean for an image over Wuhan\ndef calculate_zonal_mean(image):\n    if image.bandNames().size().getInfo() == 0:\n        return None\n    stats = image.reduceRegion(\n        reducer=ee.Reducer.mean(),\n        geometry=region_fc.geometry(),\n        scale=500,\n        maxPixels=1e9\n    )\n    return stats.get(band_name).getInfo()\n\n# --- STEP 3: Calculate daily differences ---\n# Get list of dates from 2020 collection (76 days)\ndate_list_2020 = col_2020.aggregate_array('system:time_start').map(lambda ts: ee.Date(ts).format('YYYY-MM-dd')).getInfo()\n\n# Lists to store results\ndates = []\nantl_2019_list = []\nantl_2020_list = []\ndifferences = []\n\n# Iterate over each date in 2020 and calculate corresponding 2019 value\nfor date_2020 in date_list_2020:\n    # Get images\n    img_2020 = get_image_for_date(col_2020, date_2020)\n    date_2019 = date_2020.replace('2020', '2019')\n    img_2019 = get_image_for_date(col_2019, date_2019)\n    \n    # Calculate means\n    mean_2020 = calculate_zonal_mean(img_2020)\n    mean_2019 = calculate_zonal_mean(img_2019)\n    \n    # Only proceed if both values are valid\n    if mean_2020 is not None and mean_2019 is not None:\n        diff = mean_2020 - mean_2019\n        dates.append(date_2020)\n        antl_2019_list.append(mean_2019)\n        antl_2020_list.append(mean_2020)\n        differences.append(diff)\n    else:\n        print(f\"Skipping {date_2020}: Missing data for one or both years.\")\n\n# --- STEP 4: Create DataFrame and save to CSV ---\nresults_df = pd.DataFrame({\n    'Date': dates,\n    'ANTL_2019': antl_2019_list,\n    'ANTL_2020': antl_2020_list,\n    'Difference_2020_minus_2019': differences\n})\n\noutput_csv_path = storage_manager.resolve_output_path('wuhan_daily_antl_comparison_2019_vs_2020.csv')\nresults_df.to_csv(output_csv_path, index=False)\nprint(f\"Daily comparison results saved to: {output_csv_path}\")\n\n# --- STEP 5: Generate Visualization ---\nplt.figure(figsize=(14, 7))\n\n# Plot ANTL values for both years\nplt.plot(results_df['Date'], results_df['ANTL_2019'], label='2019', marker='o', linestyle='-', color='blue')\nplt.plot(results_df['Date'], results_df['ANTL_2020'], label='2020', marker='s', linestyle='-', color='red')\n\n# Customize plot\nplt.title('Daily Average Nighttime Light (ANTL) in Wuhan\\nDuring Lockdown Period (Jan 23 - Apr 8): 2019 vs 2020')\nplt.xlabel('Date')\nplt.ylabel('Average Radiance (nW/cm\u00b2/sr)')\nplt.legend()\nplt.grid(True, linestyle='--', alpha=0.7)\nplt.xticks(rotation=45)\nplt.tight_layout()\n\n# Save plot\nplot_path_line = storage_manager.resolve_output_path('wuhan_daily_antl_comparison_line_plot.png')\nplt.savefig(plot_path_line, dpi=300, bbox_inches='tight')\n\n# Create a bar plot for differences\nplt.figure(figsize=(14, 7))\nplt.bar(results_df['Date'], results_df['Difference_2020_minus_2019'], color=['green' if x > 0 else 'red' for x in differences])\nplt.title('Daily Difference in ANTL (2020 - 2019) in Wuhan\\nDuring Lockdown Period (Jan 23 - Apr 8)')\nplt.xlabel('Date')\nplt.ylabel('Difference in Radiance (nW/cm\u00b2/sr)')\nplt.axhline(0, color='black', linewidth=0.8)\nplt.grid(axis='y', linestyle='--', alpha=0.7)\nplt.xticks(rotation=45)\nplt.tight_layout()\n\n# Save difference plot\nplot_path_bar = storage_manager.resolve_output_path('wuhan_daily_antl_difference_bar_plot.png')\nplt.savefig(plot_path_bar, dpi=300, bbox_inches='tight')\n\nprint(f\"Line plot saved to: {plot_path_line}\")\nprint(f\"Bar plot (differences) saved to: {plot_path_bar}\")\n\n# Display summary statistics\nprint(\"\\n--- Summary Statistics ---\")\nprint(f\"Total Days Analyzed: {len(results_df)}\")\nprint(f\"Average ANTL 2019: {results_df['ANTL_2019'].mean():.4f}\")\nprint(f\"Average ANTL 2020: {results_df['ANTL_2020'].mean():.4f}\")\nprint(f\"Average Daily Difference: {results_df['Difference_2020_minus_2019'].mean():.4f}\")\nprint(f\"Days with Increase (2020 > 2019): {sum(d > 0 for d in differences)}\")\nprint(f\"Days with Decrease (2020 < 2019): {sum(d < 0 for d in differences)}\")"
}