from pathlib import Path

import app_ui


def test_app_ui_runtime_paths_are_absolute_and_exist():
    assert app_ui._NTL_SCAN_SCRIPT_PATH.is_absolute()
    assert app_ui._NTL_SCAN_SCRIPT_PATH.exists()
    assert app_ui._project_path("assets", "nasa_black_marble.jpg").exists()
    assert app_ui._TEST_CASE_FILES
    assert app_ui._TEST_CASE_FILES[0].is_absolute()
    assert app_ui._TEST_CASE_FILES[0].exists()


def test_app_ui_paths_work_when_cwd_is_not_repo_root(tmp_path, monkeypatch):
    external_cwd = tmp_path / "external_run_dir"
    external_cwd.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(external_cwd)

    assert app_ui._NTL_SCAN_SCRIPT_PATH.exists()
    assert app_ui._project_path("assets", "nasa_black_marble.jpg").exists()
    assert app_ui._TEST_CASE_FILES[0].exists()


def test_app_ui_paths_work_when_cwd_is_repo_root(monkeypatch):
    monkeypatch.chdir(app_ui.APP_ROOT)

    assert app_ui._NTL_SCAN_SCRIPT_PATH.exists()
    assert app_ui._project_path("assets", "nasa_black_marble.jpg").exists()
    assert app_ui._TEST_CASE_FILES[0].exists()
