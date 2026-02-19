1.Input NTL_Shanghai_NPP-VIIRS-Like_2018.tif.
2.NTL-GPT will apply a SVM classification method to the NTL image to extract built-up areas.
3.Compare the resulting binary map with real_sh.tif using metrics such as overall accuracy, F1-score, or spatial overlap.

The real_sh.tif layer is sampled from the MGUP (2018), which is part of the dataset described in:
Liu, X., Yu, L., Li, X., & Gong, P. (2021). An updated MODIS global urban extent product (MGUP) from 2001 to 2018 based on an automated mapping approach. International Journal of Applied Earth Observation and Geoinformation, 94, 102255. https://doi.org/10.1016/j.jag.2020.102255