from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_active_analyst_contract_preserves_declared_rmse_selection_rule():
    prompt = (REPO_ROOT / "agents" / "NTL_Analyst.py").read_text(encoding="utf-8")
    skill = (
        REPO_ROOT
        / ".ntl-gpt"
        / "skills"
        / "analyst"
        / "thematic-modeling"
        / "SKILL.md"
    ).read_text(encoding="utf-8")

    for text in (prompt, skill):
        normalized = re.sub(r"\s+", " ", text.replace("-", " "))
        assert "minimum RMSE" in normalized
        assert "RMSE tie" in text
        assert "declared model order" in text
        assert "original response scale" in normalized
        assert "nonlinear least squares" in text
        assert "log-linear" in text
        assert "nonzero metric difference" in normalized or "nonzero metric difference" in text


def test_engineer_cannot_replace_a_contract_metric_winner_for_parsimony():
    graph = (REPO_ROOT / "graph_factory.py").read_text(encoding="utf-8")
    synthesis = (
        REPO_ROOT
        / ".ntl-gpt"
        / "skills"
        / "engineer"
        / "evidence-synthesis"
        / "SKILL.md"
    ).read_text(encoding="utf-8")

    assert graph.count("any lower finite RMSE wins") == 2
    assert "metric tie is exact unless the task declares a tolerance" in graph
    assert "Do not replace it with a simpler model" in synthesis
