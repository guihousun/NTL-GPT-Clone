import app_ui


def test_to_ui_relative_path_redacts_absolute_drive_path():
    out = app_ui._to_ui_relative_path(
        r"E:\NTL-GPT-Clone\user_data\debug\outputs\myanmar_earthquake_2025_impact_report.json",
        thread_id="e1060731",
    )
    assert "E:\\" not in out
    assert out.startswith("user_data/e1060731/outputs/")


def test_sanitize_paths_in_text_removes_absolute_prefix():
    text = (
        "Current thread outputs: "
        r"E:\NTL-GPT-Clone\user_data\debug\outputs\myanmar_earthquake_2025_antl_analysis.csv"
    )
    sanitized = app_ui._sanitize_paths_in_text(text, thread_id="e1060731")
    assert "E:\\" not in sanitized
    assert "user_data/e1060731/outputs/" in sanitized
