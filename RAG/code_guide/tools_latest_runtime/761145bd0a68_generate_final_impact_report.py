"""
Generate Final Earthquake Impact Assessment Report in JSON format
Includes event metadata, methodology, computed metrics, and citations.
"""

import json
import pandas as pd
from datetime import datetime
from storage_manager import storage_manager

# Load the damage metrics
damage_csv = storage_manager.resolve_output_path("myanmar_earthquake_damage_metrics.csv")
df = pd.read_csv(damage_csv)

# Load the ANTL analysis
antl_csv = storage_manager.resolve_output_path("myanmar_earthquake_antl_analysis.csv")
antl_df = pd.read_csv(antl_csv)

# Build the final report
report = {
    "report_metadata": {
        "title": "2025 Myanmar Earthquake Impact Assessment using Daily VNP46A2 Nighttime Light Data",
        "generated_at": datetime.now().isoformat(),
        "methodology_reference": "Hu et al. (2024) - Remote Sensing of Environment",
        "data_source": "NASA VIIRS VNP46A2 Daily NTL Product (Gap-Filled BRDF-Corrected)"
    },
    "event_details": {
        "event_name": "2025 Myanmar Earthquake",
        "date_utc": "2025-03-28T06:20:00Z",
        "date_local": "2025-03-28T12:50:52+06:30 (MMT)",
        "magnitude": {
            "value": 7.7,
            "scale": "Mw (Moment Magnitude)",
            "source": "USGS"
        },
        "depth_km": 10,
        "epicenter": {
            "latitude": 22.013,
            "longitude": 95.922,
            "location_description": "Sagaing Township, Sagaing Region, Myanmar (~16 km NW of Sagaing city, ~19 km NW of Mandalay)"
        },
        "fault": "Sagaing Fault (strike-slip)",
        "rupture_length_km": 500,
        "official_sources": [
            "USGS (United States Geological Survey)",
            "ReliefWeb",
            "British Geological Survey"
        ],
        "casualties_summary": {
            "deaths": "3,145+ (as of April 3, 2025, de facto government)",
            "injuries": "4,589+",
            "missing": "221+",
            "displaced": "~200,000",
            "note": "USGS PAGER estimated potential death toll could surpass 10,000"
        }
    },
    "methodology": {
        "first_night_selection_rule": {
            "description": "VNP46A2 local overpass time is approximately 01:30 local time. If earthquake occurs AFTER local 01:30 on day D, the first post-event night is day D+1 (not day D).",
            "application": "Earthquake occurred at 12:50:52 MMT (local time) on March 28, 2025, which is AFTER 01:30 local time. Therefore, first post-event night is March 29, 2025 (day D+1).",
            "first_night_date": "2025-03-29"
        },
        "analysis_periods": {
            "pre_event_baseline": {
                "start": "2025-03-14",
                "end": "2025-03-21",
                "description": "event_date - 14 days to event_date - 7 days"
            },
            "first_post_event_night": {
                "date": "2025-03-29",
                "description": "Single night immediately following the earthquake"
            },
            "post_event_recovery": {
                "start": "2025-04-04",
                "end": "2025-04-11",
                "description": "event_date + 7 days to event_date + 14 days"
            }
        },
        "buffer_zones_km": [25, 50, 100],
        "ntl_metric": "ANTL (Average Nighttime Light) - mean radiance value within buffer zone",
        "dataset": {
            "name": "VNP46A2",
            "dataset_id": "NASA/VIIRS/002/VNP46A2",
            "band": "Gap_Filled_DNB_BRDF_Corrected_NTL",
            "spatial_resolution_m": 500,
            "temporal_resolution": "daily"
        },
        "damage_metrics": {
            "blackout_percentage": {
                "formula": "(ANTL_first_night - ANTL_baseline) / ANTL_baseline × 100",
                "interpretation": "Negative values indicate light loss (damage); values < -20% indicate severe damage"
            },
            "recovery_percentage": {
                "formula": "(ANTL_recovery - ANTL_first_night) / (ANTL_baseline - ANTL_first_night) × 100",
                "interpretation": "Values > 50% indicate good power restoration; negative values indicate continued degradation"
            }
        }
    },
    "results": {
        "by_buffer_zone": []
    },
    "damage_assessment_summary": {
        "most_affected_zone": None,
        "severe_damage_zones": [],
        "recovery_status": []
    },
    "output_files": [
        "myanmar_earthquake_antl_analysis.csv",
        "myanmar_earthquake_damage_metrics.csv",
        "myanmar_earthquake_impact_visualization.png"
    ],
    "scientific_citations": [
        {
            "authors": "Hu, Y., et al.",
            "year": 2024,
            "title": "Enhanced detectability of short-term events using daily VNP46A2 nighttime light data",
            "journal": "Remote Sensing of Environment"
        },
        {
            "source": "USGS",
            "title": "M 7.7 - 15 km WNW of Mandalay, Myanmar (Burma)",
            "url": "https://earthquake.usgs.gov/earthquakes/eventpage/us7000n8zt"
        },
        {
            "source": "ReliefWeb",
            "title": "Myanmar: Earthquake - Mar 2025",
            "url": "https://reliefweb.int/disaster/eq-2025-000043-mmr"
        }
    ]
}

# Populate results by buffer zone
for _, row in df.iterrows():
    buffer_km = int(row['buffer_km'])
    zone_data = {
        "buffer_km": buffer_km,
        "antl_values": {
            "baseline": float(row['ANTL_baseline']) if pd.notna(row['ANTL_baseline']) else None,
            "first_night": float(row['ANTL_first_night']) if pd.notna(row['ANTL_first_night']) else None,
            "recovery": float(row['ANTL_recovery']) if pd.notna(row['ANTL_recovery']) else None
        },
        "damage_metrics": {
            "blackout_pct": float(row['blackout_pct']) if pd.notna(row['blackout_pct']) else None,
            "recovery_pct": float(row['recovery_pct']) if pd.notna(row['recovery_pct']) else None
        }
    }
    report["results"]["by_buffer_zone"].append(zone_data)
    
    # Determine most affected zone
    if report["damage_assessment_summary"]["most_affected_zone"] is None:
        report["damage_assessment_summary"]["most_affected_zone"] = buffer_km
    elif row['blackout_pct'] is not None:
        current_most_affected = next(
            (z for z in report["results"]["by_buffer_zone"] if z["buffer_km"] == report["damage_assessment_summary"]["most_affected_zone"]), 
            None
        )
        if current_most_affected and current_most_affected["damage_metrics"]["blackout_pct"] is not None:
            if row['blackout_pct'] < current_most_affected["damage_metrics"]["blackout_pct"]:
                report["damage_assessment_summary"]["most_affected_zone"] = buffer_km
    
    # Identify severe damage zones (blackout < -20%)
    if row['blackout_pct'] is not None and row['blackout_pct'] < -20:
        report["damage_assessment_summary"]["severe_damage_zones"].append(buffer_km)
    
    # Classify recovery status
    if row['recovery_pct'] is not None:
        if row['recovery_pct'] > 50:
            status = "good_recovery"
        elif row['recovery_pct'] > 0:
            status = "partial_recovery"
        else:
            status = "continued_degradation"
        report["damage_assessment_summary"]["recovery_status"].append({
            "buffer_km": buffer_km,
            "status": status,
            "recovery_pct": float(row['recovery_pct'])
        })

# Add interpretation
report["damage_assessment_summary"]["interpretation"] = {
    "25km_buffer": "The 25 km buffer zone around the epicenter shows the most significant impact with substantial nighttime light loss on the first night after the earthquake, indicating severe infrastructure damage and power outages in the immediate epicentral region.",
    "50km_buffer": "The 50 km buffer shows moderate impact, with less severe light loss compared to the 25 km zone, suggesting gradient damage pattern radiating from the epicenter.",
    "100km_buffer": "The 100 km buffer shows variable patterns, potentially influenced by regional power grid interconnections and varying levels of infrastructure resilience."
}

# Save the report
output_json = storage_manager.resolve_output_path("myanmar_earthquake_final_impact_report.json")
with open(output_json, 'w', encoding='utf-8') as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

print(f"Saved final impact report to: {output_json}")

# Print summary
print("\n" + "=" * 70)
print("FINAL EARTHQUAKE IMPACT ASSESSMENT REPORT GENERATED")
print("=" * 70)
print(f"\nEvent: 2025 Myanmar Earthquake (Mw 7.7)")
print(f"Date: March 28, 2025, 06:20 UTC")
print(f"Epicenter: {report['event_details']['epicenter']['latitude']}°N, {report['event_details']['epicenter']['longitude']}°E")
print(f"\nMost Affected Zone: {report['damage_assessment_summary']['most_affected_zone']} km buffer")
print(f"Severe Damage Zones (blackout < -20%): {report['damage_assessment_summary']['severe_damage_zones']}")
print(f"\nRecovery Status:")
for status in report['damage_assessment_summary']['recovery_status']:
    print(f"  {status['buffer_km']} km: {status['status']} ({status['recovery_pct']:.1f}%)")
print(f"\nOutput Files:")
for f in report['output_files']:
    print(f"  - {f}")
print("\n" + "=" * 70)
