from experiments.official_daily_ntl_fastpath.gridded_pipeline import select_variable_path


def test_select_variable_path_prefers_exact_candidate():
    datasets = [
        "HDFEOS/GRIDS/VNP_Grid_DNB/Data Fields/DNB_At_Sensor_Radiance_500m",
        "HDFEOS/GRIDS/VNP_Grid_DNB/Data Fields/Gap_Filled_DNB_BRDF-Corrected_NTL",
    ]
    candidates = (
        "HDFEOS/GRIDS/VNP_Grid_DNB/Data Fields/Gap_Filled_DNB_BRDF-Corrected_NTL",
        "Gap_Filled_DNB_BRDF-Corrected_NTL",
    )
    picked = select_variable_path(datasets, candidates)
    assert picked == "HDFEOS/GRIDS/VNP_Grid_DNB/Data Fields/Gap_Filled_DNB_BRDF-Corrected_NTL"


def test_select_variable_path_handles_non_target_variation():
    datasets = [
        "HDFEOS/GRIDS/VNP_Grid_DNB/Data Fields/DNB_At_Sensor_Radiance_500m",
        "HDFEOS/GRIDS/VNP_Grid_DNB/Data Fields/QF_Cloud_Mask",
    ]
    candidates = (
        "Gap_Filled_DNB_BRDF-Corrected_NTL",
        "DNB_At_Sensor_Radiance_500m",
    )
    picked = select_variable_path(datasets, candidates)
    assert picked == "HDFEOS/GRIDS/VNP_Grid_DNB/Data Fields/DNB_At_Sensor_Radiance_500m"

