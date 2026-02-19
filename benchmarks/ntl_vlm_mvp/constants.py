"""Shared constants for the NTL-VLM benchmark MVP."""

from __future__ import annotations

from typing import Dict, List

DEFAULT_SPLIT_COUNTS = {
    "train": 2400,
    "val": 400,
    "public_test": 400,
    "private_test": 400,
}

DEFAULT_OBJECTIVE_WEIGHT = 0.7
DEFAULT_TEXT_WEIGHT = 0.3

ALLOWED_LICENSE_TAGS = {
    "cc-by-4.0",
    "cc-by-sa-4.0",
    "cc-by-nc-4.0",
    "cc-by-nc-sa-4.0",
    "odc-by-1.0",
    "public-domain",
    "open-government-license",
    "gee-public-catalog",
}

TASK_SPECS: Dict[str, Dict] = {
    "T1": {
        "name": "Impact Presence",
        "task_type": "objective",
        "primary_metric": "f1",
        "options": [
            "A. Yes, significant impact is visible.",
            "B. No, no significant impact is visible.",
        ],
    },
    "T2": {
        "name": "Hazard Type",
        "task_type": "objective",
        "primary_metric": "accuracy",
        "options": [
            "A. Earthquake",
            "B. Flood",
            "C. Wildfire",
            "D. Hurricane/Typhoon",
            "E. Conflict",
            "F. Other",
        ],
    },
    "T3": {
        "name": "Outage Severity",
        "task_type": "objective",
        "primary_metric": "macro_f1",
        "options": [
            "A. No or minimal outage",
            "B. Moderate outage",
            "C. Major outage",
            "D. Extreme outage",
        ],
    },
    "T4": {
        "name": "Affected Area Localization",
        "task_type": "objective",
        "primary_metric": "accuracy",
        "options": [
            "A. North sector",
            "B. East sector",
            "C. South sector",
            "D. West sector",
        ],
    },
    "T5": {
        "name": "Blackout Cluster Counting",
        "task_type": "objective",
        "primary_metric": "pm1_accuracy",
        "options": [
            "A. 0-2 clusters",
            "B. 3-5 clusters",
            "C. 6-10 clusters",
            "D. >10 clusters",
        ],
    },
    "T6": {
        "name": "Temporal Recovery State",
        "task_type": "objective",
        "primary_metric": "macro_f1",
        "options": [
            "A. No recovery",
            "B. Early recovery",
            "C. Stable recovery",
            "D. Near full recovery",
        ],
    },
    "T7": {
        "name": "Situation Caption",
        "task_type": "text",
        "primary_metric": "text_score",
        "options": [],
    },
    "T8": {
        "name": "Recovery Recommendation",
        "task_type": "text",
        "primary_metric": "text_score",
        "options": [],
    },
}

OBJECTIVE_TASK_IDS = tuple(k for k, v in TASK_SPECS.items() if v["task_type"] == "objective")
TEXT_TASK_IDS = tuple(k for k, v in TASK_SPECS.items() if v["task_type"] == "text")

TRACKS: List[str] = ["zero_shot", "fine_tune"]

DEFAULT_PRE_WINDOW_DAYS = (30, 7)
DEFAULT_POST_WINDOW_DAYS = (0, 21)

