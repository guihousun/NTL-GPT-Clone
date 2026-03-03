from pathlib import Path
import re


SCRIPT_PATH = Path("base_data/Iran_War/analysis/scripts/rebuild_iran_event_report.py")


def _script_text() -> str:
    return SCRIPT_PATH.read_text(encoding="utf-8")


def test_ntl_class_bins_are_centralized_and_reused_for_variants() -> None:
    text = _script_text()
    assert "NTL_CLASS_BINS = 5" in text

    uses = re.findall(r"build_breaks\([^\n]*bins=NTL_CLASS_BINS\)", text)
    # Ensure global + city + county all route through one shared class-bin setting.
    assert len(uses) >= 3


def test_axis_title_labels_are_removed_for_global_and_local_maps() -> None:
    text = _script_text()

    x_empty = len(re.findall(r'ax\.set_xlabel\("", fontsize=\d+\)', text))
    y_empty = len(re.findall(r'ax\.set_ylabel\("", fontsize=\d+\)', text))
    assert x_empty >= 4
    assert y_empty >= 4

    assert 'ax.set_xlabel("经度"' not in text
    assert 'ax.set_ylabel("纬度"' not in text


def test_delta_overlay_is_opaque() -> None:
    text = _script_text()
    assert "DELTA_OVERLAY_ALPHA = 1.0" in text
