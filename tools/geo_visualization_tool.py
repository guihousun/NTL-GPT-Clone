from langchain_experimental.utilities import PythonREPL
from langchain_core.tools import StructuredTool
# 更新函数，使用解包参数
from pydantic import BaseModel, Field
from IPython import InteractiveShell
import io
from contextlib import redirect_stdout
import json

from Langchain_tool import repl_tool

# # Set up the IPython shell instance
# shell = InteractiveShell().instance()

# Initialize Python REPL to execute code
python_repl = PythonREPL()

import os
import matplotlib.pyplot as plt
import matplotlib
from matplotlib import cm
from typing import Optional


# Define the input schema


# import os
# import rasterio
# import matplotlib.pyplot as plt
# import numpy as np
# from matplotlib.colors import Normalize
#
# # File path
# masked_image_path = os.path.join(r'C:/NTL_Agent/report/image', 'Masked_NTL_Image_of_Nanjing_June_2020.tif')
#
# # Open the masked nighttime light data
# data = rasterio.open(masked_image_path)
#
# # Read data
# band1 = data.read(1)
#
# # Visualization
# plt.figure(figsize=(10, 10))
# plt.imshow(band1, cmap='cividis', norm=Normalize(vmin=np.percentile(band1, 1), vmax=np.percentile(band1, 99)))
# plt.colorbar(label='Radiance')
# plt.title('Masked NTL Image of Nanjing - June 2020', fontsize=16, fontweight='bold')
# plt.xlabel('X', fontsize=15)
# plt.ylabel('Y', fontsize=15)
#
# # Save the figure
# save_path = os.path.join(r'C:/NTL_Agent/report/image', 'Masked_NTL_Image_of_Nanjing_June_2020.png')
# plt.savefig(save_path, dpi=300)
# plt.show()
# plt.close()
#
# print(f'Full storage address: {save_path}')
# print('Task Completed')

# import os
# import matplotlib.pyplot as plt
# import rasterio
#
# # File path
# masked_ntl_path = os.path.join(r'C:/NTL_Agent/Night_data/Shanghai', '上海市_Masked_NTL_2020-06.tif')
# output_image_path = os.path.join(r'C:/NTL_Agent/report/image', 'NTL_Image_of_Shanghai_June_2020.png')
#
# # Open the raster file
# with rasterio.open(masked_ntl_path) as src:
#   ntl_data = src.read(1)
#   nodata_value = src.nodata  # Get the NoData value
#   # # Mask the NoData values (If NoData value is defined)
#   # if nodata_value is not None:
#   ntl_data = np.ma.masked_equal(ntl_data, nodata_value)  # Mask NoData values
#   vmin, vmax = np.percentile(ntl_data, (1, 99))  # Calculate 1% and 99% percentiles
#   # Plot
#   fig, ax = plt.subplots(figsize=(10, 10))
#   cax = ax.imshow(ntl_data, cmap='cividis', vmin=vmin, vmax=vmax)
#   fig.colorbar(cax, ax=ax, label='Radiance')
#   ax.set_title('NTL Image of Shanghai - June 2020', fontsize=16, fontweight='bold')
#   ax.set_xlabel('Longitude', fontsize=15)
#   ax.set_ylabel('Latitude', fontsize=15)
#   plt.axis('off')
#   plt.show()
#   plt.savefig(output_image_path, dpi=300, bbox_inches='tight')
#
# print(f'Full storage address: {output_image_path}')
# print('Task Completed')