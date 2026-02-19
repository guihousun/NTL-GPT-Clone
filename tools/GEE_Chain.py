from langchain_core.tools import StructuredTool
# 更新函数，使用解包参数
from pydantic import BaseModel, Field

from GEE_tool import time_series_analysis, TimeSeriesAnalysisInput, detect_anomaly, AnomalyDetectionInput, \
    DailyNTL_preprocess
import geemap




# Define the StructuredTool
DailyNTL_preprocess_tool = StructuredTool.from_function(
    DailyNTL_preprocess,
    name="DailyNTL_retrieve_with_preprocess",
    description=(
        """
        This tool is designed for retrieving and preprocessing daily nighttime light data from Google Earth Engine within a specified administrative region and date range. 
        It produces corrected daily mean NTL values for the selected region and date range.
        The output file includes additional information for each date, such as holiday and weekday.

        Example Input:
        start_date = '2023-01-01'
        end_date = '2023-02-01'
        study_area = '黄浦区'
        scale_level = 'county'

        Example Output:
        Returns a string representing the path to the CSV file containing the preprocessed data, e.g., 'C:/NTL_Agent/report/csv/Daily_NTL_preprocess.csv'.
        """

    ),
    input_type=[str, str, str],
)
# 定义 StructuredTool
time_series_tool = StructuredTool.from_function(
    time_series_analysis,
    name="time_series_analysis_tool",
    description=(
        """
        This tool is used to make STL Time Series Analysis, perform seasonal adjustment on the preprocessed daily NTL mean data CSV file for a specific region. 
        The tool includes data preprocessing, logarithmic transformation, monthly seasonal adjustments, and detection of anomalous dates. 
        It ultimately generates a CSV file containing the analysis results.

        Example Input:
        TimeSeriesAnalysisInput(
            csv_path='nightlight_data.csv',
            use_normalized_data=False,
            interpolation_method='time',
            seasonal_params={
                'monthly': 15,
                'yearly': 23
            },
            outlier_handling_method='include'
        )

        Example Output:
        Returns the path to the resulting CSV file, e.g., 'C:/NTL_Agent/report/csv/Daily_NTL_seasonal_adjustment.csv'.
        """
    ),
    input_type=TimeSeriesAnalysisInput,
)

# 定义 StructuredTool
anomaly_detection_tool = StructuredTool.from_function(
    detect_anomaly,
    name="daily_anomaly_detection_tool",
    description=(
        "此工具接受新日期的日度夜间灯光均值，基于之前分析的时间序列数据，判断该值是否为异常。"
        "工具使用时间序列模型预测给定日期的预期夜光值，计算输入值与预测值之间的残差和 z-score，"
        "并根据偏差程度确定异常等级。\n\n"
        "**示例输入：**\n"
        "AnomalyDetectionInput(\n"
        "    new_ntl_value=20.5,\n"
        "    new_date_str='2023-03-01',\n"
        "    processed_csv_path='nightlight_time_series_analysis.csv',\n"
        ")\n\n"
        "**示例输出：**\n"
        "{\n"
        "    '日期': '2023-03-01',\n"
        "    '预测的夜光值': 18.7,\n"
        "    '输入的夜光值': 20.5,\n"
        "    '残差': 1.8,\n"
        "    'z-score': 1.2,\n"
        "    '异常等级': '轻度异常',\n"
        "    '是否节假日': '正常日期',\n"
        "    '星期几': '周三'\n"
        "}"
    ),
    input_type=AnomalyDetectionInput,
)

# result = nightlight_download_tool.func(study_area='南京市',scale_level='city',dataset_choice='monthly',
#                                        time_range_input='2020-01 to 2020-02',export_folder='C:/NTL_Agent/Night_data/Nanjing',
#                                        workplace = 'GEE',collection_name = 'NTL_VIIRS_Nanjing_202001_202002')
#
# print(result)
#
# result2 = GEE_process_tool.func(task_description=".",GEE_python_code=
# """
# print('Task Begin')
# import ee
# import pandas as pd
#
# # Authenticate and Initialize the Earth Engine module
# ee.Authenticate()
# project_id = 'empyrean-caster-430308-m2'
# ee.Initialize(project=project_id)
#
# # Define the time range and region
# start_date = '2014-01-01'
# end_date = '2014-03-31'
# region = ee.Geometry.Polygon([
#     [[73.5, 18], [135, 18], [135, 53.5], [73.5, 53.5], [73.5, 18]]
# ])
#
# # Load the VIIRS DNB Nighttime Day/Night Band Composites dataset
# dataset = NTL_VIIRS_Nanjing_202001_202002
#
# # Filter the dataset by date and region
# filtered_dataset = dataset.filterBounds(region)
#
# # Apply the mean calculation to each image in the collection
# def calculate_mean_inline(image):
#     mean = image.reduceRegion(
#         reducer=ee.Reducer.mean(),
#         geometry=region,
#         scale=500,
#         maxPixels=1e9
#     )
#     return image.set({'date': image.date().format('YYYY-MM'), 'mean_ntl': mean.get('avg_rad')})
#
# mean_features = filtered_dataset.map(calculate_mean_inline)
#
# # Convert the FeatureCollection to a list of dictionaries
# mean_dicts = mean_features.aggregate_array('properties').getInfo()
#
# # Convert to DataFrame
# mean_df = pd.DataFrame(mean_dicts)
#
# # Save to CSV
# csv_path = r'C:/NTL_Agent/report/csv/china_ntl_monthly_mean_2014_2024.csv'
# mean_df.to_csv(csv_path, index=False)
#
# print(f'Result: {csv_path}')
# print('Task Completed')
# """)
# print(result2)

# result = NTL_download_tool.func(study_area='南京市',
#             scale_level='city',
#             dataset_choice='annual',
#             time_range_input='2019 to 2020',
#             export_folder='C:/NTL_Agent/Night_data/Nanjing')

# DailyNTL_preprocess_tool.func(study_area='黄浦区',scale_level='county',start_date = '2022-01-01',end_date = '2024-01-01')
# input = TimeSeriesAnalysisInput(csv_path="C:/NTL_Agent/report/csv/nightlight_data.csv")
# result = time_series_tool.func(input)
# print(result)
