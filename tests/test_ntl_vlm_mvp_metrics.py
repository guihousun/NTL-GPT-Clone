from __future__ import annotations

from benchmarks.ntl_vlm_mvp.evaluate_benchmark import evaluate_objective_task
from benchmarks.ntl_vlm_mvp.text_metrics import aggregate_text_metrics


def test_objective_metrics_golden_case():
    refs = [
        {"sample_id": "s1", "answer": "A"},
        {"sample_id": "s2", "answer": "B"},
        {"sample_id": "s3", "answer": "A"},
        {"sample_id": "s4", "answer": "B"},
    ]
    perfect_pred = {"s1": "A", "s2": "B", "s3": "A", "s4": "B"}
    wrong_pred = {"s1": "B", "s2": "A", "s3": "B", "s4": "A"}

    perfect = evaluate_objective_task(task_id="T1", ref_rows=refs, pred_map=perfect_pred)
    wrong = evaluate_objective_task(task_id="T1", ref_rows=refs, pred_map=wrong_pred)

    assert perfect["accuracy"] == 1.0
    assert perfect["f1"] == 1.0
    assert wrong["accuracy"] == 0.0
    assert perfect["f1"] > wrong["f1"]


def test_random_baseline_is_worse_than_weak_baseline():
    refs = [{"sample_id": f"s{i}", "answer": "C"} for i in range(10)]
    weak_pred = {f"s{i}": ("C" if i < 8 else "B") for i in range(10)}
    random_pred = {f"s{i}": ("A" if i % 2 == 0 else "D") for i in range(10)}

    weak = evaluate_objective_task(task_id="T3", ref_rows=refs, pred_map=weak_pred)
    random = evaluate_objective_task(task_id="T3", ref_rows=refs, pred_map=random_pred)
    assert weak["macro_f1"] > random["macro_f1"]


def test_text_metrics_reward_better_predictions():
    references = [
        "The city shows major nighttime power loss after flooding.",
        "Recovery is partial with gradual brightness restoration.",
    ]
    strong_preds = [
        "Major nighttime power loss is visible after flooding in the city.",
        "Brightness is gradually recovering, indicating partial recovery.",
    ]
    weak_preds = [
        "Some change.",
        "Unknown.",
    ]

    strong = aggregate_text_metrics(references, strong_preds)
    weak = aggregate_text_metrics(references, weak_preds)
    assert strong["bleu4"] > weak["bleu4"]
    assert strong["rouge_l"] > weak["rouge_l"]
    assert strong["cider_lite"] > weak["cider_lite"]

