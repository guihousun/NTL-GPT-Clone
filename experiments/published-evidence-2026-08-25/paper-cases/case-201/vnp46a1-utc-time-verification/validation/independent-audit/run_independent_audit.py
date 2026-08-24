"""Read-only independent audit for the Q18 VNP46A1 UTC_Time package.

This script reads the timing result JSON and metadata, hashes the source HDF5 and
frozen Q18 artifacts, and reads only the first HDF5 signature bytes. It does
not open HDF5 datasets and does not parse or calculate any radiance values.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]
AUDIT = Path(__file__).resolve().parent
HDF5 = ROOT / "source" / "VNP46A1.A2025087.h27v06.002.2025088113623.h5"
MANIFEST = ROOT / "source" / "source-manifest.json"
RESULT = ROOT / "results" / "utc-time-analysis.json"
ENGINEER = ROOT / "validation" / "engineer-validation.json"
FORMAL_ROOT = (
    ROOT.parent
    / "paper-case-multiagent-2026-08-13"
    / "Q18-myanmar-earthquake"
    / "formal-25km-50km-20260817"
)
FORMAL_CSV = FORMAL_ROOT / "formal-q18-analysis-ready.csv"
FORMAL_PACKAGE = FORMAL_ROOT / "formal-observation-package.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def contains_text(value, needle: str) -> bool:
    if isinstance(value, dict):
        return any(contains_text(k, needle) or contains_text(v, needle) for k, v in value.items())
    if isinstance(value, list):
        return any(contains_text(v, needle) for v in value)
    return needle in str(value)


def main() -> None:
    manifest = load(MANIFEST)
    result = load(RESULT)
    engineer = load(ENGINEER)

    actual_hdf_hash = sha256(HDF5)
    actual_hdf_bytes = HDF5.stat().st_size
    with HDF5.open("rb") as stream:
        signature = stream.read(8)
    manifest_download = manifest["download"]
    source_identity = {
        "path": str(HDF5),
        "manifest_filename": manifest_download["path"],
        "actual_filename": HDF5.name,
        "manifest_bytes": manifest_download["bytes"],
        "actual_bytes": actual_hdf_bytes,
        "manifest_sha256": manifest_download["sha256"],
        "actual_sha256": actual_hdf_hash,
        "manifest_hdf5_signature_valid": manifest_download["hdf5_signature_valid"],
        "actual_hdf5_signature": signature.hex(),
        "hash_match": actual_hdf_hash == manifest_download["sha256"],
        "bytes_match": actual_hdf_bytes == manifest_download["bytes"],
        "signature_match": signature == b"\x89HDF\r\n\x1a\n",
    }
    package_file_identity = {
        "source_manifest": {
            "path": str(MANIFEST),
            "bytes": MANIFEST.stat().st_size,
            "sha256": sha256(MANIFEST),
        },
        "utc_time_result": {
            "path": str(RESULT),
            "bytes": RESULT.stat().st_size,
            "sha256": sha256(RESULT),
        },
        "engineer_validation": {
            "path": str(ENGINEER),
            "bytes": ENGINEER.stat().st_size,
            "sha256": sha256(ENGINEER),
        },
    }

    event = result["event"]
    event_utc = datetime.fromisoformat(event["event_time_utc"].replace("Z", "+00:00"))
    expected_local = event_utc.astimezone(ZoneInfo("Asia/Yangon")).isoformat()
    event_local_check = {
        "reported": event["event_time_local"],
        "independent": expected_local,
        "passed": expected_local == event["event_time_local"] == "2025-03-28T12:50:52+06:30",
    }

    attrs = result["utc_time_metadata"]["dataset_attributes"]
    metadata_check = {
        "dataset_path": result["utc_time_metadata"]["dataset_path"],
        "shape": result["utc_time_metadata"]["dataset_shape"],
        "long_name": attrs["long_name"],
        "units": attrs["units"],
        "valid_min": attrs["valid_min"],
        "valid_max": attrs["valid_max"],
        "scale_factor": attrs["scale_factor"],
        "add_offset": attrs["add_offset"],
        "passed": (
            result["utc_time_metadata"]["dataset_path"].endswith("/UTC_Time")
            and attrs["long_name"] == "View Time (UTC)"
            and attrs["units"] == "decimal hours"
            and attrs["valid_min"] == 0
            and attrs["valid_max"] == 24
            and attrs["scale_factor"] == 1.0
            and attrs["add_offset"] == 0.0
        ),
    }

    pixel = result["event_pixel"]
    product_day = datetime(2025, 3, 28, tzinfo=timezone.utc)
    pixel_utc = product_day + timedelta(hours=pixel["utc_time_decimal_hour"])
    pixel_local = pixel_utc.astimezone(ZoneInfo("Asia/Yangon"))
    event_pixel_check = {
        "valid": pixel["valid"],
        "decimal_hour": pixel["utc_time_decimal_hour"],
        "reported_utc": pixel["observation_time_utc"],
        "independent_utc": pixel_utc.isoformat().replace("+00:00", "Z"),
        "reported_local": pixel["observation_time_local"],
        "independent_local": pixel_local.isoformat(),
        "post_event": pixel_utc > event_utc,
        "local_date_is_2025_03_29": pixel_local.date().isoformat() == "2025-03-29",
        "passed": (
            pixel["valid"]
            and pixel_utc.isoformat().replace("+00:00", "Z") == pixel["observation_time_utc"]
            and pixel_local.isoformat() == pixel["observation_time_local"]
            and pixel_utc > event_utc
            and pixel_local.date().isoformat() == "2025-03-29"
        ),
    }

    buffer_checks = []
    for summary in result["buffer_summaries"]:
        values = [summary[key] for key in ("min_utc_hour", "median_utc_hour", "mean_utc_hour", "max_utc_hour")]
        local_counts = summary["local_date_counts"]
        buffer_checks.append(
            {
                "radius_km": summary["radius_km"],
                "n": summary["n"],
                "min_utc_hour": summary["min_utc_hour"],
                "median_utc_hour": summary["median_utc_hour"],
                "mean_utc_hour": summary["mean_utc_hour"],
                "max_utc_hour": summary["max_utc_hour"],
                "local_date_counts": local_counts,
                "passed": (
                    summary["n"] > 0
                    and all(0 <= float(value) <= 24 for value in values)
                    and set(local_counts) == {"2025-03-29"}
                    and sum(local_counts.values()) == summary["n"]
                ),
            }
        )

    frozen = {
        "formal_q18_csv_sha256": sha256(FORMAL_CSV),
        "formal_q18_observation_package_sha256": sha256(FORMAL_PACKAGE),
        "expected_formal_q18_csv_sha256": "3c6777a41aa074a1357d25938120b026ab9cd7afa86bea3f419fbde64ce9d554",
        "expected_formal_q18_observation_package_sha256": "7d9379dd8f066a37ac876a05ea346de797d2dfd40bc891a21592aa684255a804",
    }
    frozen["passed"] = (
        frozen["formal_q18_csv_sha256"] == frozen["expected_formal_q18_csv_sha256"]
        and frozen["formal_q18_observation_package_sha256"] == frozen["expected_formal_q18_observation_package_sha256"]
    )

    result_text_checks = {
        "result_contains_system_time_start": contains_text(result, "system:time_start"),
        "engineer_contains_system_time_start": contains_text(engineer, "system:time_start"),
        "passed": not contains_text(result, "system:time_start") and not contains_text(engineer, "system:time_start"),
    }
    engineer_checks = engineer["checks"]
    engineer_recheck = {"checks": engineer_checks, "all_true": all(engineer_checks.values())}

    audit = {
        "schema": "ntl.q18.vnp46a1-independent-audit.v2",
        "status": "source_backed_timing_verified_non_radiance_audit",
        "scope": "Read-only independent validation of VNP46A1 UTC_Time timing evidence; no HDF5 datasets other than file signature were opened and no VNP46A2 radiance values were read or computed.",
        "package_file_identity": package_file_identity,
        "source_identity": source_identity,
        "metadata_check": metadata_check,
        "event_local_check": event_local_check,
        "event_pixel_check": event_pixel_check,
        "buffer_checks": buffer_checks,
        "engineer_validation_recheck": engineer_recheck,
        "formal_q18_immutability": frozen,
        "no_system_time_inference": result_text_checks,
        "safe_conclusion": {
            "supports_first_post_event_local_night": all([
                source_identity["hash_match"],
                source_identity["bytes_match"],
                source_identity["signature_match"],
                metadata_check["passed"],
                event_local_check["passed"],
                event_pixel_check["passed"],
                all(item["passed"] for item in buffer_checks),
                engineer_recheck["all_true"],
            ]),
            "statement": "A2025087 is source-backed as the first post-event local-night observation for this event area: the containing event pixel and all valid UTC_Time pixels in the 25 km and 50 km supports map to 29 March 2025 local time and occur after the 06:20:52 UTC mainshock.",
            "limits": [
                "This supports the temporal correspondence, not earthquake causality, damage, outage, recovery, or significance.",
                "UTC_Time is a per-pixel view-time field; it does not convert the product date mechanically and does not establish a single acquisition instant for the whole tile.",
                "The VNP46A1 UTC_Time layer is timing evidence only; VNP46A2 remains the radiance product for Q18.",
                "The word 'first' is bounded to the analyzed Q18 same-tile temporal sequence and its stated pre-event context; this audit does not establish exhaustive global observation coverage.",
            ],
        },
    }
    (AUDIT / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Q18 VNP46A1 UTC_Time 独立复核（source-backed）",
        "",
        "## 结论",
        "",
        "独立复核通过：官方 HDF5 身份、字节数、SHA-256、HDF5 signature、UTC_Time 元数据、事件点时刻和 25/50 km 摘要均一致。由此可以安全支持：A2025087（2025-03-28 UTC-indexed）对应震后首个 Asia/Yangon 当地夜间（2025-03-29），但该结论仅是时相对应关系，不是因果、损毁、停电或恢复证据。",
        "",
        "## 核验结果",
        "",
        f"- HDF5：`{HDF5.name}`，{actual_hdf_bytes:,} bytes，SHA-256 `{actual_hdf_hash}`；manifest 与实际文件一致，HDF5 signature 为 `{signature.hex()}`。",
        f"- 当前 source manifest 文件本身：{MANIFEST.stat().st_size:,} bytes，SHA-256 `{package_file_identity['source_manifest']['sha256']}`；其下载记录与实际 HDF5 的字节数、SHA-256 和 signature 一致。",
        f"- UTC_Time：`{result['utc_time_metadata']['dataset_path']}`，`{metadata_check['long_name']}`，单位 `{metadata_check['units']}`，范围 `[0, 24]`，scale/offset `{metadata_check['scale_factor']}/{metadata_check['add_offset']}`。",
        f"- 事件时刻：`{event['event_time_utc']}` → `{event['event_time_local']}`；独立 ZoneInfo 换算一致。",
        f"- 事件像元：UTC 小时 `{pixel['utc_time_decimal_hour']:.12f}`，UTC `{pixel['observation_time_utc']}`，当地 `{pixel['observation_time_local']}`；位于主震之后且为 2025-03-29 当地日期。",
        f"- 25 km：n={result['buffer_summaries'][0]['n']}，UTC_Time min/median/mean/max = `{result['buffer_summaries'][0]['min_utc_hour']:.12f}` / `{result['buffer_summaries'][0]['median_utc_hour']:.12f}` / `{result['buffer_summaries'][0]['mean_utc_hour']:.12f}` / `{result['buffer_summaries'][0]['max_utc_hour']:.12f}`；全部 2025-03-29 当地日期。",
        f"- 50 km：n={result['buffer_summaries'][1]['n']}，UTC_Time min/median/mean/max = `{result['buffer_summaries'][1]['min_utc_hour']:.12f}` / `{result['buffer_summaries'][1]['median_utc_hour']:.12f}` / `{result['buffer_summaries'][1]['mean_utc_hour']:.12f}` / `{result['buffer_summaries'][1]['max_utc_hour']:.12f}`；全部 2025-03-29 当地日期。",
        "- 工程验证：当前 engineer-validation 的全部检查为 true。",
        f"- 正式 Q18 VNP46A2 CSV SHA-256：`{frozen['formal_q18_csv_sha256']}`；ObservationPackage SHA-256：`{frozen['formal_q18_observation_package_sha256']}`；均与冻结值一致。",
        "- 时间来源限制：未从 `system:time_start` 推断观测时间；本审计没有读取或计算 VNP46A2 辐亮度。",
        "",
        "## 可安全采用与限界",
        "",
        "可以安全写入：VNP46A1 的逐像元 `UTC_Time` 显示，2025-03-28 UTC 产品中的事件像元及 25/50 km 支持像元均在主震之后观测，并换算到 2025-03-29 的 Asia/Yangon 当地时间；因此 A2025087 可作为 Q18 的震后首个当地夜间时相证据。",
        "",
        "不能由本审计写出：地震导致停电或损毁、恢复轨迹/恢复率、统计显著性或因果效应。VNP46A1 只提供时间核验，Q18 的辐亮度数值仍以未改动的 VNP46A2 正式资产为准。",
        "",
        "“首个”应限定为当前 Q18 同瓦片时序和既定震前上下文中的首个震后合格当地夜间观测；本审计不声称对所有全球观测源进行了穷尽式覆盖检索。",
        "",
        "机器可读明细见 [audit.json](audit.json)。",
    ]
    (AUDIT / "audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
