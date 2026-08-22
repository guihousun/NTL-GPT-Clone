from __future__ import annotations

import os
import ssl
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import gee_runtime
import storage_manager


class GEERuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._project_token = storage_manager.current_gee_project_id.set("")
        self._source_token = storage_manager.current_gee_profile_source.set("")

    def tearDown(self) -> None:
        storage_manager.current_gee_profile_source.reset(self._source_token)
        storage_manager.current_gee_project_id.reset(self._project_token)
        os.environ.pop(gee_runtime.GEE_PROJECT_ENV, None)
        os.environ.pop(gee_runtime.GEE_BOUNDARY_ASSET_PROJECT_ENV, None)
        os.environ.pop("EE_SERVICE_ACCOUNT", None)
        os.environ.pop("EE_PRIVATE_KEY_JSON", None)

    def _dotenv(self, value: str = ""):
        temp_dir = tempfile.TemporaryDirectory()
        env_file = Path(temp_dir.name) / ".env"
        env_file.write_text(
            f"{gee_runtime.GEE_PROJECT_ENV}={value}\n" if value else "# empty\n",
            encoding="utf-8",
        )
        return temp_dir, patch.object(gee_runtime, "REPO_DOTENV_PATH", env_file)

    def test_project_resolution_priority(self) -> None:
        temp_dir, dotenv_patch = self._dotenv("dotenv-project")
        with temp_dir, dotenv_patch, patch.dict(
            os.environ,
            {gee_runtime.GEE_PROJECT_ENV: "environment-project"},
            clear=False,
        ):
            context_token = storage_manager.current_gee_project_id.set("context-project")
            try:
                self.assertEqual(gee_runtime.resolve_gee_project_id("explicit-project"), "explicit-project")
                self.assertEqual(gee_runtime.resolve_gee_project_id(), "context-project")
            finally:
                storage_manager.current_gee_project_id.reset(context_token)

            self.assertEqual(gee_runtime.resolve_gee_project_id(), "environment-project")

    def test_repository_dotenv_is_final_configured_source(self) -> None:
        os.environ.pop(gee_runtime.GEE_PROJECT_ENV, None)
        temp_dir, dotenv_patch = self._dotenv("dotenv-project")
        with temp_dir, dotenv_patch:
            self.assertEqual(gee_runtime.resolve_gee_project_id(), "dotenv-project")

    def test_missing_project_fails_closed(self) -> None:
        os.environ.pop(gee_runtime.GEE_PROJECT_ENV, None)
        temp_dir, dotenv_patch = self._dotenv()
        with temp_dir, dotenv_patch:
            with self.assertRaises(gee_runtime.GEEProjectConfigurationError):
                gee_runtime.resolve_gee_project_id()

    def test_initialize_always_passes_explicit_project_and_never_authenticates(self) -> None:
        fake_ee = Mock()
        credentials = object()

        with patch.dict(
            os.environ,
            {"EE_SERVICE_ACCOUNT": "", "EE_PRIVATE_KEY_JSON": ""},
            clear=False,
        ):
            resolved = gee_runtime.initialize_ee(
                "explicit-project",
                credentials=credentials,
                ee_module=fake_ee,
            )

        self.assertEqual(resolved, "explicit-project")
        fake_ee.Initialize.assert_called_once_with(
            project="explicit-project",
            credentials=credentials,
        )
        fake_ee.Authenticate.assert_not_called()

    def test_initialize_classifies_tls_failure_without_authenticate_fallback(self) -> None:
        fake_ee = Mock()
        fake_ee.Initialize.side_effect = ssl.SSLError("UNEXPECTED_EOF_WHILE_READING")

        with patch.dict(
            os.environ,
            {"EE_SERVICE_ACCOUNT": "", "EE_PRIVATE_KEY_JSON": ""},
            clear=False,
        ):
            with self.assertRaises(gee_runtime.GEEInitializationError) as raised:
                gee_runtime.initialize_ee("explicit-project", ee_module=fake_ee)

        self.assertEqual(raised.exception.category, "transport_tls")
        self.assertEqual(raised.exception.project_id, "explicit-project")
        self.assertIn("category=transport_tls", str(raised.exception))
        fake_ee.Authenticate.assert_not_called()

    def test_initialize_classifies_missing_persistent_credential_without_authenticate_fallback(self) -> None:
        fake_ee = Mock()
        fake_ee.Initialize.side_effect = RuntimeError(
            "Please authorize access to your Earth Engine account by running earthengine authenticate"
        )

        with patch.dict(
            os.environ,
            {"EE_SERVICE_ACCOUNT": "", "EE_PRIVATE_KEY_JSON": ""},
            clear=False,
        ):
            with self.assertRaises(gee_runtime.GEEInitializationError) as raised:
                gee_runtime.initialize_ee("explicit-project", ee_module=fake_ee)

        self.assertEqual(raised.exception.category, "credentials")
        fake_ee.Authenticate.assert_not_called()

    def test_bind_runtime_sets_and_resets_project_and_source_context(self) -> None:
        before_project = storage_manager.current_gee_project_id.get()
        before_source = storage_manager.current_gee_profile_source.get()

        with gee_runtime.bind_gee_runtime("bound-project", "user_profile") as project_id:
            self.assertEqual(project_id, "bound-project")
            self.assertEqual(storage_manager.current_gee_project_id.get(), "bound-project")
            self.assertEqual(storage_manager.current_gee_profile_source.get(), "user_profile")

        self.assertEqual(storage_manager.current_gee_project_id.get(), before_project)
        self.assertEqual(storage_manager.current_gee_profile_source.get(), before_source)

    def test_context_resets_when_bound_run_raises(self) -> None:
        before_project = storage_manager.current_gee_project_id.get()
        before_source = storage_manager.current_gee_profile_source.get()

        with self.assertRaisesRegex(RuntimeError, "boom"):
            with gee_runtime.bind_gee_runtime("bound-project", "deployment_default"):
                raise RuntimeError("boom")

        self.assertEqual(storage_manager.current_gee_project_id.get(), before_project)
        self.assertEqual(storage_manager.current_gee_profile_source.get(), before_source)

    def test_app_does_not_switch_to_per_user_project_in_shared_process(self) -> None:
        import app_logic

        class GuardedProfile(dict):
            def get(self, key, default=None):
                if key in {"encrypted_refresh_token", "token_scopes"}:
                    raise AssertionError("runtime selection must not read OAuth material")
                return super().get(key, default)

        profile = GuardedProfile(mode="user", gee_project_id="user-project")
        with patch.object(app_logic.history_store, "get_user_gee_profile", return_value=profile) as getter, patch.object(
            app_logic,
            "resolve_gee_project_id",
            return_value="deployment-project",
        ) as resolver:
            selected = app_logic._resolve_run_gee_profile("alice")

        self.assertEqual(selected, ("deployment-project", "default", "deployment_default"))
        resolver.assert_called_once_with()
        getter.assert_not_called()

    def test_app_falls_back_to_deployment_project_for_incomplete_user_profile(self) -> None:
        import app_logic

        profile = {"mode": "user", "gee_project_id": ""}
        with patch.object(app_logic.history_store, "get_user_gee_profile", return_value=profile) as getter, patch.object(
            app_logic,
            "resolve_gee_project_id",
            return_value="deployment-project",
        ) as resolver:
            selected = app_logic._resolve_run_gee_profile("alice")

        self.assertEqual(selected, ("deployment-project", "default", "deployment_default"))
        resolver.assert_called_once_with()
        getter.assert_not_called()

    def test_boundary_asset_project_is_separate_and_falls_back_to_runtime_project(self) -> None:
        with patch.dict(
            os.environ,
            {
                gee_runtime.GEE_PROJECT_ENV: "runtime-project",
                gee_runtime.GEE_BOUNDARY_ASSET_PROJECT_ENV: "boundary-owner-project",
            },
            clear=False,
        ):
            self.assertEqual(
                gee_runtime.resolve_gee_boundary_asset_project_id(),
                "boundary-owner-project",
            )

        os.environ.pop(gee_runtime.GEE_BOUNDARY_ASSET_PROJECT_ENV, None)
        temp_dir, dotenv_patch = self._dotenv()
        with temp_dir, dotenv_patch, patch.dict(
            os.environ,
            {gee_runtime.GEE_PROJECT_ENV: "runtime-project"},
            clear=False,
        ):
            self.assertEqual(
                gee_runtime.resolve_gee_boundary_asset_project_id(),
                "runtime-project",
            )

    def test_deployment_service_account_is_centralized_for_all_callers(self) -> None:
        fake_ee = Mock()
        fake_credentials = object()
        fake_ee.ServiceAccountCredentials.return_value = fake_credentials
        with patch.dict(
            os.environ,
            {
                "EE_SERVICE_ACCOUNT": "service@example.invalid",
                "EE_PRIVATE_KEY_JSON": "{\"private_key\":\"redacted\"}",
            },
            clear=False,
        ):
            gee_runtime.initialize_ee("runtime-project", ee_module=fake_ee)

        fake_ee.ServiceAccountCredentials.assert_called_once_with(
            "service@example.invalid",
            key_data="{\"private_key\":\"redacted\"}",
        )
        fake_ee.Initialize.assert_called_once_with(
            project="runtime-project",
            credentials=fake_credentials,
        )

    def test_incomplete_deployment_service_account_fails_closed(self) -> None:
        fake_ee = Mock()
        with patch.dict(
            os.environ,
            {"EE_SERVICE_ACCOUNT": "service@example.invalid", "EE_PRIVATE_KEY_JSON": ""},
            clear=False,
        ):
            with self.assertRaisesRegex(gee_runtime.GEERuntimeError, "configuration is incomplete"):
                gee_runtime.initialize_ee("runtime-project", ee_module=fake_ee)
        fake_ee.Initialize.assert_not_called()

    def test_unconfigured_runtime_binding_allows_local_work_but_gee_resolution_fails(self) -> None:
        os.environ.pop(gee_runtime.GEE_PROJECT_ENV, None)
        with patch.object(gee_runtime, "REPO_DOTENV_PATH", Path("missing-test-dotenv")):
            with gee_runtime.bind_gee_runtime("", "unconfigured") as project_id:
                self.assertEqual(project_id, "")
                with self.assertRaises(gee_runtime.GEEProjectConfigurationError):
                    gee_runtime.resolve_gee_project_id()


if __name__ == "__main__":
    unittest.main()
