import app_ui


def test_sanitize_paths_in_obj_redacts_tool_json_path_fields():
    payload = {
        "script_path": r"E:\NTL-GPT-Clone\user_data\debug\outputs\my_script.py",
        "artifact_audit": {
            "workspace_outputs_dir": r"E:\NTL-GPT-Clone\user_data\debug\outputs",
            "out_of_workspace_paths": [
                r"E:\NTL-GPT-Clone\user_data\debug\outputs\my_result.csv",
            ],
        },
        "note": "Saved to E:\\NTL-GPT-Clone\\user_data\\debug\\outputs\\my_result.csv",
    }

    sanitized = app_ui._sanitize_paths_in_obj(payload, thread_id="abcd1234")
    assert "E:\\" not in str(sanitized)
    assert sanitized["script_path"].startswith("user_data/abcd1234/outputs/")
    assert sanitized["artifact_audit"]["workspace_outputs_dir"].startswith("user_data/abcd1234/outputs")
