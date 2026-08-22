from __future__ import annotations

import json
import math

import pytest

import tools.NTL_estimate_indicator as dei_module
from tools import _EXPORTS, _GROUPS
from tools.NTL_estimate_indicator import (
    DEI_Estimate_City_Input,
    DEI_estimate_city,
    DEI_estimate_city_tool,
)


PAPER_MODELS = {
    "2017": {"form": "a * ln(TNTL) + b", "coefficient": 13.387, "intercept": -91.838},
    "2018": {"form": "a * ln(TNTL) + b", "coefficient": 13.596, "intercept": -94.755},
    "2019": {"form": "a * ln(TNTL) + b", "coefficient": 13.0006, "intercept": -85.622},
    "2020": {"form": "a * ln(TNTL) + b", "coefficient": 12.619, "intercept": -81.687},
}


def _write_artifact(path, *, feature_name="TNTL", transform="natural_log"):
    artifact = {
        "schema_version": "ntl-gpt.dei.yearly-formula.v1",
        "artifact_type": "reconstructed-from-paper",
        "source": {"doi": "10.1016/j.compenvurbsys.2021.101749"},
        "feature": {"name": feature_name, "transform": transform},
        "models": PAPER_MODELS,
        "warnings": ["Published coefficients are rounded."],
    }
    path.write_text(json.dumps(artifact), encoding="utf-8")


def _v2_artifact(*, form="linear", parameters=None, training_range=None):
    if parameters is None:
        parameters = {"a": 2.0, "b": 3.0}
    if training_range is None:
        training_range = {"min": 1.0, "max": 100.0}
    equations = {
        "linear": "a * TNTL + b",
        "logarithmic": "a * ln(TNTL) + b",
        "quadratic": "a * TNTL^2 + b * TNTL + c",
        "exponential": "b * exp(a * TNTL)",
    }
    return {
        "schema_version": "ntl-gpt.dei.yearly-formula.v2",
        "artifact_id": "unit-test-v2",
        "artifact_type": "retrained",
        "status": "candidate-not-deployed",
        "inputs": {"training_csv": {"sha256": "unit-test"}},
        "feature": {
            "name": "TNTL",
            "transform": "model-specific",
            "antl_is_accepted": False,
        },
        "models": {
            "2020": {
                "form": form,
                "model_type": form,
                "equation": equations.get(form, "unsupported unit-test equation"),
                "parameters": parameters,
                "training_tntl_range": training_range,
                "training": {
                    "tntl_range": {
                        "min": training_range.get("min"),
                        "max": training_range.get("max"),
                        "unit": "summed radiance",
                    }
                },
            }
        },
        "warnings": ["Unit-test candidate only."],
    }


def _write_v2_artifact(path, **kwargs):
    artifact = _v2_artifact(**kwargs)
    path.write_text(json.dumps(artifact), encoding="utf-8")
    return artifact


def test_public_schema_requires_tntl_and_year_and_forbids_antl():
    assert _EXPORTS["DEI_estimate_city_tool"] == (".NTL_estimate_indicator", "DEI_estimate_city_tool")
    assert "DEI_estimate_city_tool" in _GROUPS["Engineer_tools"]
    assert "DEI_estimate_city_tool" in _GROUPS["specialized_tool_catalog"]
    schema = DEI_Estimate_City_Input.schema()
    assert set(schema["required"]) == {"tntl", "year"}
    assert set(schema["properties"]) == {"tntl", "year"}
    assert schema["additionalProperties"] is False
    assert "TNTL" in DEI_estimate_city_tool.description
    assert "ANTL" in DEI_estimate_city_tool.description

    with pytest.raises(Exception):
        DEI_estimate_city_tool.invoke({"antl": 100000.0, "year": 2020})
    with pytest.raises(Exception):
        DEI_estimate_city_tool.invoke({"tntl": 100000.0})


def test_missing_model_fails_explicitly(tmp_path, monkeypatch):
    missing = tmp_path / "missing.json"
    monkeypatch.setattr(dei_module, "_dei_model_candidates", lambda: [missing])

    result = DEI_estimate_city(tntl=100000.0, year=2020)

    assert result["error"] is True
    assert "missing" in result["message"].lower()
    assert str(missing) in result["message"]


@pytest.mark.parametrize(
    "payload, expected_message",
    [
        ("{not-json", "invalid or unreadable"),
        (
            json.dumps(
                {
                    "schema_version": "ntl-gpt.dei.yearly-formula.v1",
                    "artifact_type": "reconstructed-from-paper",
                    "source": {"doi": "10.1016/j.compenvurbsys.2021.101749"},
                    "feature": {"name": "ANTL", "transform": "natural_log"},
                    "models": PAPER_MODELS,
                }
            ),
            "ANTL artifacts are incompatible",
        ),
    ],
)
def test_corrupt_or_wrong_feature_artifact_fails(tmp_path, monkeypatch, payload, expected_message):
    model_path = tmp_path / "yearly_dei_models.json"
    model_path.write_text(payload, encoding="utf-8")
    monkeypatch.setattr(dei_module, "_dei_model_candidates", lambda: [model_path])

    result = DEI_estimate_city(tntl=100000.0, year=2020)

    assert result["error"] is True
    assert expected_message in result["message"]


@pytest.mark.parametrize("tntl", [0.0, -1.0, math.nan, math.inf, -math.inf, True, "not-a-number"])
def test_invalid_tntl_fails_before_model_loading(tntl, tmp_path, monkeypatch):
    monkeypatch.setattr(dei_module, "_dei_model_candidates", lambda: [tmp_path / "missing.json"])

    result = DEI_estimate_city(tntl=tntl, year=2020)

    assert result["error"] is True
    assert "Invalid TNTL feature" in result["message"]


def test_unavailable_year_fails_with_exact_available_years(tmp_path, monkeypatch):
    model_path = tmp_path / "yearly_dei_models.json"
    _write_artifact(model_path)
    monkeypatch.setattr(dei_module, "_dei_model_candidates", lambda: [model_path])

    result = DEI_estimate_city(tntl=100000.0, year=2021)

    assert result["error"] is True
    assert "2021" in result["message"]
    assert "[2017, 2018, 2019, 2020]" in result["message"]


@pytest.mark.parametrize("year", [2020.5, "2020", True, None])
def test_non_integer_year_fails_explicitly(year, tmp_path, monkeypatch):
    model_path = tmp_path / "yearly_dei_models.json"
    _write_artifact(model_path)
    monkeypatch.setattr(dei_module, "_dei_model_candidates", lambda: [model_path])

    result = DEI_estimate_city(tntl=100000.0, year=year)

    assert result["error"] is True
    assert "must be an integer" in result["message"]


@pytest.mark.parametrize("year", [2017, 2018, 2019, 2020])
def test_each_paper_formula_is_evaluated_exactly(year, tmp_path, monkeypatch):
    model_path = tmp_path / "yearly_dei_models.json"
    _write_artifact(model_path)
    monkeypatch.setattr(dei_module, "_dei_model_candidates", lambda: [model_path])
    tntl = 100000.0
    entry = PAPER_MODELS[str(year)]

    result = DEI_estimate_city(tntl=tntl, year=year)

    expected = entry["coefficient"] * math.log(tntl) + entry["intercept"]
    assert result["error"] is False
    assert result["year"] == year
    assert result["tntl"] == tntl
    assert result["predicted_dei"] == pytest.approx(expected, abs=1e-12)
    assert result["model_provenance"] == "reconstructed-from-paper"
    assert "TNTL" in result["input_semantics"]
    assert "ANTL" in result["input_semantics"]
    assert any("not a retrained model" in warning for warning in result["warnings"])


def test_structured_tool_end_to_end_uses_tntl_and_explicit_year(tmp_path, monkeypatch):
    model_path = tmp_path / "yearly_dei_models.json"
    _write_artifact(model_path)
    monkeypatch.setattr(dei_module, "_dei_model_candidates", lambda: [model_path])

    result = DEI_estimate_city_tool.invoke({"tntl": 100000.0, "year": 2020})

    expected = 12.619 * math.log(100000.0) - 81.687
    assert result["error"] is False
    assert result["predicted_dei"] == pytest.approx(expected, abs=1e-12)
    assert result["year"] == 2020


@pytest.mark.parametrize(
    "form, parameters, expected",
    [
        ("linear", {"a": 2.0, "b": 3.0}, 23.0),
        ("logarithmic", {"a": 2.0, "b": 3.0}, 2.0 * math.log(10.0) + 3.0),
        ("quadratic", {"a": 0.5, "b": 2.0, "c": 3.0}, 73.0),
        ("exponential", {"a": 0.01, "b": 2.0}, 2.0 * math.exp(0.1)),
    ],
)
def test_v2_mixed_formula_families_are_evaluated_transparently(
    form, parameters, expected, tmp_path, monkeypatch
):
    model_path = tmp_path / "yearly_dei_models_candidate.json"
    _write_v2_artifact(model_path, form=form, parameters=parameters)
    monkeypatch.setattr(dei_module, "_dei_model_candidates", lambda: [model_path])

    result = DEI_estimate_city(tntl=10.0, year=2020)

    assert result["error"] is False
    assert result["predicted_dei"] == pytest.approx(expected, abs=1e-12)
    assert result["formula_form"] == form
    assert result["model_schema_version"] == "ntl-gpt.dei.yearly-formula.v2"
    assert result["model_provenance"] == "retrained"
    assert result["training_tntl_range"] == {"min": 1.0, "max": 100.0}
    assert "TNTL" in result["formula"]


def test_v2_accepts_source_provenance_variant_without_artifact_id(tmp_path, monkeypatch):
    model_path = tmp_path / "yearly_dei_models_candidate.json"
    artifact = _v2_artifact()
    artifact.pop("artifact_id")
    artifact.pop("inputs")
    artifact["source"] = {"experiment": "transparent-v2-unit-test"}
    model_path.write_text(json.dumps(artifact), encoding="utf-8")
    monkeypatch.setattr(dei_module, "_dei_model_candidates", lambda: [model_path])

    result = DEI_estimate_city(tntl=10.0, year=2020)

    assert result["error"] is False
    assert result["model_schema_version"] == "ntl-gpt.dei.yearly-formula.v2"


@pytest.mark.parametrize("tntl", [0.5, 100.0001])
def test_retrained_v2_refuses_out_of_domain_tntl(tntl, tmp_path, monkeypatch):
    model_path = tmp_path / "yearly_dei_models_candidate.json"
    _write_v2_artifact(model_path)
    monkeypatch.setattr(dei_module, "_dei_model_candidates", lambda: [model_path])

    result = DEI_estimate_city(tntl=tntl, year=2020)

    assert result["error"] is True
    assert "outside the inclusive training TNTL range" in result["message"]
    assert "prediction refused" in result["message"]
    assert result["training_tntl_range"] == {"min": 1.0, "max": 100.0}


@pytest.mark.parametrize("tntl", [1.0, 100.0])
def test_retrained_v2_range_boundaries_are_inclusive(tntl, tmp_path, monkeypatch):
    model_path = tmp_path / "yearly_dei_models_candidate.json"
    _write_v2_artifact(model_path)
    monkeypatch.setattr(dei_module, "_dei_model_candidates", lambda: [model_path])

    result = DEI_estimate_city(tntl=tntl, year=2020)

    assert result["error"] is False


@pytest.mark.parametrize(
    "training_range, expected_message",
    [
        (None, "training_tntl_range is missing"),
        ({"min": 1.0}, "exactly 'min' and 'max'"),
        ({"min": 0.0, "max": 100.0}, "greater than zero"),
        ({"min": 101.0, "max": 100.0}, "must not exceed max"),
        ({"min": "1", "max": 100.0}, "must be a JSON number"),
    ],
)
def test_retrained_v2_requires_valid_training_domain(
    training_range, expected_message, tmp_path, monkeypatch
):
    model_path = tmp_path / "yearly_dei_models_candidate.json"
    artifact = _v2_artifact()
    if training_range is None:
        artifact["models"]["2020"].pop("training_tntl_range")
    else:
        artifact["models"]["2020"]["training_tntl_range"] = training_range
    model_path.write_text(json.dumps(artifact), encoding="utf-8")
    monkeypatch.setattr(dei_module, "_dei_model_candidates", lambda: [model_path])

    result = DEI_estimate_city(tntl=10.0, year=2020)

    assert result["error"] is True
    assert expected_message in result["message"]


@pytest.mark.parametrize(
    "form, parameters, expected_message",
    [
        ("cubic", {"a": 1.0, "b": 2.0}, ".form must be one of"),
        ("linear", {"a": 1.0}, "must contain exactly"),
        ("linear", {"a": 1.0, "b": 2.0, "c": 3.0}, "must contain exactly"),
        ("linear", {"a": True, "b": 2.0}, "must be a JSON number"),
        ("linear", {"a": math.inf, "b": 2.0}, "must be finite"),
    ],
)
def test_v2_formula_schema_and_parameters_fail_closed(
    form, parameters, expected_message, tmp_path, monkeypatch
):
    model_path = tmp_path / "yearly_dei_models_candidate.json"
    _write_v2_artifact(model_path, form=form, parameters=parameters)
    monkeypatch.setattr(dei_module, "_dei_model_candidates", lambda: [model_path])

    result = DEI_estimate_city(tntl=10.0, year=2020)

    assert result["error"] is True
    assert expected_message in result["message"]


def test_v2_exponential_overflow_is_an_explicit_formula_failure(tmp_path, monkeypatch):
    model_path = tmp_path / "yearly_dei_models_candidate.json"
    _write_v2_artifact(
        model_path,
        form="exponential",
        parameters={"a": 1000.0, "b": 1.0},
        training_range={"min": 1.0, "max": 2.0},
    )
    monkeypatch.setattr(dei_module, "_dei_model_candidates", lambda: [model_path])

    result = DEI_estimate_city(tntl=1.0, year=2020)

    assert result["error"] is True
    assert "formula evaluation failed" in result["message"]
    assert "exponential" in result["message"]


def test_v2_does_not_select_latest_year_implicitly(tmp_path, monkeypatch):
    model_path = tmp_path / "yearly_dei_models_candidate.json"
    _write_v2_artifact(model_path)
    monkeypatch.setattr(dei_module, "_dei_model_candidates", lambda: [model_path])

    with pytest.raises(Exception):
        DEI_estimate_city_tool.invoke({"tntl": 10.0})

    unavailable = DEI_estimate_city(tntl=10.0, year=2024)
    assert unavailable["error"] is True
    assert "unavailable" in unavailable["message"]
    assert "[2020]" in unavailable["message"]


def test_v2_surfaces_candidate_status_and_limitations(tmp_path, monkeypatch):
    model_path = tmp_path / "yearly_dei_models_candidate.json"
    artifact = _v2_artifact()
    artifact["limitations"] = ["Boundary provenance is unresolved."]
    model_path.write_text(json.dumps(artifact), encoding="utf-8")
    monkeypatch.setattr(dei_module, "_dei_model_candidates", lambda: [model_path])

    result = DEI_estimate_city(tntl=10.0, year=2020)

    assert result["error"] is False
    assert result["artifact_status"] == "candidate-not-deployed"
    assert "Boundary provenance is unresolved." in result["warnings"]
    assert "status: candidate-not-deployed" in result["message"]


def test_duplicate_json_keys_are_rejected_instead_of_silently_overwritten(
    tmp_path, monkeypatch
):
    model_path = tmp_path / "yearly_dei_models_candidate.json"
    model_path.write_text(
        """
        {
          "schema_version": "ntl-gpt.dei.yearly-formula.v2",
          "artifact_id": "duplicate-key-test",
          "artifact_type": "retrained",
          "inputs": {"training_csv": {"sha256": "unit-test"}},
          "feature": {"name": "TNTL"},
          "models": {
            "2020": {
              "form": "linear",
              "parameters": {"a": 1.0, "a": 999.0, "b": 0.0},
              "training_tntl_range": {"min": 1.0, "max": 100.0}
            }
          }
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(dei_module, "_dei_model_candidates", lambda: [model_path])

    result = DEI_estimate_city(tntl=10.0, year=2020)

    assert result["error"] is True
    assert "duplicate JSON object key 'a'" in result["message"]
