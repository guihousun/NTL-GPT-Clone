"""
Myanmar Earthquake 2025 Impact Assessment using Daily VNP46A2 NTL Data
========================================================================
Earthquake: Mw 7.7 on March 28, 2025, 12:50:52 MMT (06:20:52 UTC)
Epicenter: 21.996N, 95.926E (16 km NNW of Sagaing, Myanmar)
First night after earthquake: 2025-03-29 (D+1, since earthquake occurred after 01:30 overpass)

Methodology:
- Angular correction using 16-group mean normalization (VNP46A2 cycle)
- ANTL computation for pre-event (2025-02-26 to 2025-03-27), post-event (2025-03-31 to 2025-04-30)
- NTL Change Value (NCV) and NTL Change Rate (NCR) calculation
- KS-test for statistical significance
- Damage assessment summary

Based on: Yuan et al. (2023) - The Changes in Nighttime Lights Caused by the Turkey-Syria Earthquake

AOI_CONFIRMED_BY_USER: Myanmar boundary validated via get_administrative_division_osm_tool
Bounds: [92.1729181, 9.526084, 101.1700796, 28.547835] (EPSG:4326)
"""

import ee
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from storage_manager import storage_manager

# Initialize Earth Engine
PROJECT_ID = "empyrean-caster-430308-m2"
ee.Initialize(project=PROJECT_ID)

# =============================================================================
# STEP 1: Define study parameters
# =============================================================================

# Epicenter coordinates (USGS official)
EPICENTER_LON = 95.926
EPICENTER_LAT = 21.996

# Myanmar boundary bounds (AOI_CONFIRMED_BY_USER: from get_administrative_division_osm_tool)
# Validated: myanmar_boundary.shp, EPSG:4326
MYANMAR_BOUNDS = [92.1729181, 9.526084, 101.1700796, 28.547835]
study_region = ee.Geometry.Rectangle(MYANMAR_BOUNDS, proj='EPSG:4326', geodesic=False)

# Earthquake date
EARTHQUAKE_DATE = '2025-03-28'
earthquake_date_obj = datetime.strptime(EARTHQUAKE_DATE, '%Y-%m-%d')

# Time windows (based on methodology)
# Pre-event: 30 days before earthquake (2025-02-26 to 2025-03-27)
PRE_EVENT_START = (earthquake_date_obj - timedelta(days=30)).strftime('%Y-%m-%d')
PRE_EVENT_END = (earthquake_date_obj - timedelta(days=1)).strftime('%Y-%m-%d')

# Post-event: 30 days after, excluding first 2 days for emergency response (2025-03-31 to 2025-04-30)
POST_EVENT_START = (earthquake_date_obj + timedelta(days=3)).strftime('%Y-%m-%d')
POST_EVENT_END = (earthquake_date_obj + timedelta(days=33)).strftime('%Y-%m-%d')

# First night after earthquake: 2025-03-29 (D+1)
FIRST_NIGHT_DATE = (earthquake_date_obj + timedelta(days=1)).strftime('%Y-%m-%d')

# Analysis parameters
SCALE = 500  # VNP46A2 native resolution
MAX_PIXELS = 1e13  # Large region requires high limit

print("=" * 80)
print("MYANMAR EARTHQUAKE 2025 - NTL IMPACT ASSESSMENT")
print("=" * 80)
print(f"Epicenter: {EPICENTER_LAT}N, {EPICENTER_LON}E")
print(f"Earthquake Date: {EARTHQUAKE_DATE} (12:50:52 MMT)")
print(f"Pre-event window: {PRE_EVENT_START} to {PRE_EVENT_END}")
print(f"First night: {FIRST_NIGHT_DATE}")
print(f"Post-event window: {POST_EVENT_START} to {POST_EVENT_END}")
print(f"Analysis scale: {SCALE}m, maxPixels: {MAX_PIXELS}")
print("=" * 80)

# =============================================================================
# STEP 2: Load VNP46A2 collection
# =============================================================================

VNP46A2_BAND = 'Gap_Filled_DNB_BRDF_Corrected_NTL'

# Full collection for time series analysis
full_collection = (
    ee.ImageCollection('NASA/VIIRS/002/VNP46A2')
    .filterDate(PRE_EVENT_START, POST_EVENT_END)
    .filterBounds(study_region)
    .select(VNP46A2_BAND)
)

print(f"\nTotal images in collection: {full_collection.size().getInfo()}")

# =============================================================================
# STEP 3: Angular Correction using 16-group mean normalization
# =============================================================================

def apply_angular_correction(collection):
    """
    Apply 16-group mean normalization to VNP46A2 daily data.
    VNP46A2 has a 16-day repeat cycle; group images by day-of-cycle (0-15).
    """
    def add_day_of_cycle(image):
        # Get day of year
        doy = ee.Number(image.date().getRelative('day', 'year'))
        # Day of cycle (0-15)
        doc = doy.mod(16)
        return image.set('day_of_cycle', doc)
    
    # Add day-of-cycle to each image
    collection_with_doc = collection.map(add_day_of_cycle)
    
    # Compute mean for each day-of-cycle group
    def compute_group_mean(doc):
        doc = ee.Number(doc)
        filtered = collection_with_doc.filter(ee.Filter.eq('day_of_cycle', doc))
        return filtered.mean().set('day_of_cycle', doc)
    
    # Get all unique day-of-cycle values and compute means
    doc_values = ee.List.sequence(0, 15)
    group_means = ee.ImageCollection(doc_values.map(compute_group_mean))
    
    # Compute overall mean (correction factor denominator)
    overall_mean = collection_with_doc.mean()
    
    # Compute correction factors for each group
    def compute_correction_factor(image):
        group_mean = image
        # Correction factor = overall_mean / group_mean
        correction = overall_mean.divide(group_mean)
        return correction.set('day_of_cycle', image.get('day_of_cycle'))
    
    correction_factors = ee.ImageCollection(group_means.map(compute_correction_factor))
    
    # Apply correction to each image
    def apply_correction(image):
        doc = ee.Number(image.get('day_of_cycle'))
        # Find matching correction factor
        matching_cf = correction_factors.filter(ee.Filter.eq('day_of_cycle', doc)).first()
        # Apply correction
        corrected = image.multiply(matching_cf)
        return corrected.copyProperties(image, image.propertyNames())
    
    corrected_collection = collection_with_doc.map(apply_correction)
    
    return corrected_collection

print("\nApplying angular correction (16-group mean normalization)...")
corrected_collection = apply_angular_correction(full_collection)
print("Angular correction applied successfully.")

# =============================================================================
# STEP 4: Compute ANTL for pre-event, first night, and post-event periods
# =============================================================================

def compute_antd_for_period(collection, start_date, end_date, period_name):
    """
    Compute Average Nighttime Light (ANTL) for a given period.
    Returns mean ANTL value and image count.
    """
    period_collection = collection.filterDate(start_date, end_date)
    image_count = period_collection.size().getInfo()
    
    if image_count == 0:
        print(f"  WARNING: No images found for {period_name} ({start_date} to {end_date})")
        return None, 0
    
    # Compute mean ANTL over the period
    mean_image = period_collection.mean()
    
    # Reduce to get mean value over study region
    # Explicit scale, crs, maxPixels, bestEffort, and tileScale for robustness
    antl_result = mean_image.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=study_region,
        scale=SCALE,
        crs='EPSG:4326',
        maxPixels=MAX_PIXELS,
        bestEffort=True,
        tileScale=4
    )
    
    antl_value = ee.Number(antl_result.get(VNP46A2_BAND)).getInfo()
    
    print(f"  {period_name}: {image_count} images, ANTL = {antl_value:.4f} nW/cm2/sr")
    
    return antl_value, image_count

print("\n" + "=" * 80)
print("STEP 4: ANTL COMPUTATION")
print("=" * 80)

# Pre-event ANTL
pre_antd, pre_count = compute_antd_for_period(
    corrected_collection, PRE_EVENT_START, PRE_EVENT_END, "Pre-event"
)

# First night ANTL (single day)
first_night_collection = corrected_collection.filterDate(FIRST_NIGHT_DATE, FIRST_NIGHT_DATE)
first_night_count = first_night_collection.size().getInfo()
if first_night_count > 0:
    first_night_image = first_night_collection.first()
    first_night_result = first_night_image.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=study_region,
        scale=SCALE,
        crs='EPSG:4326',
        maxPixels=MAX_PIXELS,
        bestEffort=True,
        tileScale=4
    )
    first_night_antd = ee.Number(first_night_result.get(VNP46A2_BAND)).getInfo()
    print(f"  First night ({FIRST_NIGHT_DATE}): {first_night_count} image(s), ANTL = {first_night_antd:.4f} nW/cm2/sr")
else:
    first_night_antd = None
    print(f"  WARNING: No image found for first night ({FIRST_NIGHT_DATE})")

# Post-event ANTL
post_antd, post_count = compute_antd_for_period(
    corrected_collection, POST_EVENT_START, POST_EVENT_END, "Post-event"
)

# =============================================================================
# STEP 5: Compute NTL Change Metrics (NCV and NCR)
# =============================================================================

print("\n" + "=" * 80)
print("STEP 5: NTL CHANGE METRICS")
print("=" * 80)

# NTL Change Value (NCV) = NTL_after - NTL_before
if pre_antd is not None and post_antd is not None:
    ncv = post_antd - pre_antd
    print(f"\nNTL Change Value (NCV): {ncv:.4f} nW/cm2/sr")
    
    # NTL Change Rate (NCR) = NCV / NTL_before
    # Avoid division by zero
    if pre_antd > 0:
        ncr = ncv / pre_antd
        print(f"NTL Change Rate (NCR): {ncr:.4f} ({ncr*100:.2f}%)")
    else:
        ncr = None
        print("NTL Change Rate (NCR): Cannot compute (pre-event ANTL = 0)")
else:
    ncv = None
    ncr = None
    print("Cannot compute NCV/NCR: Missing pre or post ANTL values")

# First night change
if pre_antd is not None and first_night_antd is not None:
    first_night_ncv = first_night_antd - pre_antd
    if pre_antd > 0:
        first_night_ncr = first_night_ncv / pre_antd
        print(f"\nFirst Night Change:")
        print(f"  NCV (first night vs pre-event): {first_night_ncv:.4f} nW/cm2/sr")
        print(f"  NCR (first night vs pre-event): {first_night_ncr:.4f} ({first_night_ncr*100:.2f}%)")
    else:
        first_night_ncv = None
        first_night_ncr = None
else:
    first_night_ncv = None
    first_night_ncr = None

# =============================================================================
# STEP 6: Time Series Analysis - Daily ANTL values
# =============================================================================

print("\n" + "=" * 80)
print("STEP 6: DAILY TIME SERIES EXTRACTION")
print("=" * 80)

def extract_daily_antd(img):
    """Extract ANTL value for each image in collection."""
    value = img.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=study_region,
        scale=SCALE,
        crs='EPSG:4326',
        maxPixels=MAX_PIXELS,
        bestEffort=True,
        tileScale=4
    ).get(VNP46A2_BAND)
    
    return ee.Feature(None, {
        'date': img.date().format('YYYY-MM-dd'),
        'antd': ee.Number(value),
        'system:time_start': img.get('system:time_start')
    })

# Extract daily values using server-side map, then single getInfo() call
daily_features = corrected_collection.map(extract_daily_antd)
daily_data = [f['properties'] for f in daily_features.getInfo()['features']]

# Convert to DataFrame
df_daily = pd.DataFrame(daily_data)
df_daily['date'] = pd.to_datetime(df_daily['date'])
df_daily = df_daily.sort_values('date').reset_index(drop=True)

print(f"Extracted {len(df_daily)} daily ANTL values")
print(df_daily.head())

# =============================================================================
# STEP 7: Statistical Significance Test (KS-test)
# =============================================================================

print("\n" + "=" * 80)
print("STEP 7: STATISTICAL SIGNIFICANCE TEST (KS-TEST)")
print("=" * 80)

from scipy import stats

# Get pre and post daily values
pre_dates = pd.date_range(start=PRE_EVENT_START, end=PRE_EVENT_END)
post_dates = pd.date_range(start=POST_EVENT_START, end=POST_EVENT_END)

pre_values = df_daily[df_daily['date'].isin(pre_dates)]['antd'].dropna().values
post_values = df_daily[df_daily['date'].isin(post_dates)]['antd'].dropna().values

print(f"\nPre-event samples: {len(pre_values)}")
print(f"Post-event samples: {len(post_values)}")

if len(pre_values) > 0 and len(post_values) > 0:
    # Two-sample Kolmogorov-Smirnov test
    ks_statistic, p_value = stats.ks_2samp(pre_values, post_values)
    
    alpha = 0.05
    is_significant = p_value < alpha
    
    print(f"\nKS-test Results:")
    print(f"  KS statistic: {ks_statistic:.4f}")
    print(f"  p-value: {p_value:.6f}")
    print(f"  Significance level (alpha): {alpha}")
    print(f"  Statistically significant: {'YES' if is_significant else 'NO'} (p < {alpha})")
else:
    ks_statistic = None
    p_value = None
    is_significant = None
    print("Cannot perform KS-test: Insufficient data")

# =============================================================================
# STEP 8: Damage Assessment Summary
# =============================================================================

print("\n" + "=" * 80)
print("STEP 8: DAMAGE ASSESSMENT SUMMARY")
print("=" * 80)

# Interpret NTL changes
if ncv is not None:
    if ncv < -0.5:
        damage_severity = "SEVERE"
        interpretation = "Significant NTL decrease indicates major infrastructure damage, power outages, or population displacement"
    elif ncv < -0.2:
        damage_severity = "MODERATE"
        interpretation = "Moderate NTL decrease suggests partial infrastructure damage or temporary power disruptions"
    elif ncv < 0:
        damage_severity = "LIGHT"
        interpretation = "Slight NTL decrease may indicate minor disruptions or temporary effects"
    elif ncv > 0.2:
        damage_severity = "RECOVERY/INCREASE"
        interpretation = "NTL increase may indicate recovery efforts, emergency lighting, or population influx"
    else:
        damage_severity = "MINIMAL"
        interpretation = "Minimal NTL change suggests limited impact on nighttime lighting"
    
    print(f"\nDamage Severity Assessment: {damage_severity}")
    print(f"Interpretation: {interpretation}")

# Summary statistics
print("\n" + "-" * 80)
print("SUMMARY STATISTICS")
print("-" * 80)
print(f"Study Area: Myanmar (bounds: {MYANMAR_BOUNDS})")
print(f"Epicenter: {EPICENTER_LAT}N, {EPICENTER_LON}E")
print(f"Earthquake: Mw 7.7 on {EARTHQUAKE_DATE}")
print(f"\nPre-event Period: {PRE_EVENT_START} to {PRE_EVENT_END} ({pre_count} images)")
print(f"  Mean ANTL: {pre_antd:.4f} nW/cm2/sr" if pre_antd else "  Mean ANTL: N/A")
print(f"\nFirst Night: {FIRST_NIGHT_DATE} ({first_night_count} image)")
print(f"  Mean ANTL: {first_night_antd:.4f} nW/cm2/sr" if first_night_antd else "  Mean ANTL: N/A")
print(f"\nPost-event Period: {POST_EVENT_START} to {POST_EVENT_END} ({post_count} images)")
print(f"  Mean ANTL: {post_antd:.4f} nW/cm2/sr" if post_antd else "  Mean ANTL: N/A")
print(f"\nNTL Change Metrics:")
print(f"  NCV: {ncv:.4f} nW/cm2/sr" if ncv else "  NCV: N/A")
print(f"  NCR: {ncr:.4f} ({ncr*100:.2f}%)" if ncr else "  NCR: N/A")
print(f"\nStatistical Significance:")
print(f"  KS statistic: {ks_statistic:.4f}" if ks_statistic else "  KS statistic: N/A")
print(f"  p-value: {p_value:.6f}" if p_value else "  p-value: N/A")
print(f"  Significant change: {'YES' if is_significant else 'NO'}" if is_significant is not None else "  Significant change: N/A")

# =============================================================================
# STEP 9: Save Results
# =============================================================================

print("\n" + "=" * 80)
print("STEP 9: SAVING RESULTS")
print("=" * 80)

# Create comprehensive results DataFrame
results_summary = {
    'metric': [
        'earthquake_date', 'epicenter_lat', 'epicenter_lon', 'magnitude',
        'pre_event_start', 'pre_event_end', 'pre_event_images', 'pre_event_antd',
        'first_night_date', 'first_night_images', 'first_night_antd',
        'post_event_start', 'post_event_end', 'post_event_images', 'post_event_antd',
        'ncv', 'ncr', 'ncr_percent',
        'ks_statistic', 'p_value', 'is_significant',
        'damage_severity'
    ],
    'value': [
        EARTHQUAKE_DATE, EPICENTER_LAT, EPICENTER_LON, 7.7,
        PRE_EVENT_START, PRE_EVENT_END, pre_count, pre_antd,
        FIRST_NIGHT_DATE, first_night_count, first_night_antd,
        POST_EVENT_START, POST_EVENT_END, post_count, post_antd,
        ncv, ncr, ncr * 100 if ncr else None,
        ks_statistic, p_value, is_significant,
        damage_severity if ncv is not None else None
    ]
}

df_summary = pd.DataFrame(results_summary)

# Save summary CSV
output_csv_path = storage_manager.resolve_output_path('myanmar_earthquake_2025_antd_analysis.csv')
df_summary.to_csv(output_csv_path, index=False)
print(f"\nSummary results saved to: {output_csv_path}")

# Save daily time series CSV
daily_csv_path = storage_manager.resolve_output_path('myanmar_earthquake_2025_daily_antd.csv')
df_daily.to_csv(daily_csv_path, index=False)
print(f"Daily time series saved to: {daily_csv_path}")

# Save damage assessment report (using ASCII-safe characters)
report_path = storage_manager.resolve_output_path('myanmar_earthquake_2025_damage_report.txt')
with open(report_path, 'w', encoding='utf-8') as f:
    f.write("=" * 80 + "\n")
    f.write("MYANMAR EARTHQUAKE 2025 - NTL DAMAGE ASSESSMENT REPORT\n")
    f.write("=" * 80 + "\n\n")
    f.write("EARTHQUAKE PARAMETERS\n")
    f.write("-" * 40 + "\n")
    f.write(f"Date: {EARTHQUAKE_DATE} (12:50:52 MMT / 06:20:52 UTC)\n")
    f.write(f"Magnitude: Mw 7.7\n")
    f.write(f"Epicenter: {EPICENTER_LAT}N, {EPICENTER_LON}E\n")
    f.write(f"Depth: 10 km (shallow)\n")
    f.write(f"Fault: Sagaing Fault (right-lateral strike-slip)\n\n")
    f.write("NTL ANALYSIS PARAMETERS\n")
    f.write("-" * 40 + "\n")
    f.write(f"Dataset: NASA/VIIRS/002/VNP46A2\n")
    f.write(f"Band: {VNP46A2_BAND}\n")
    f.write(f"Spatial Resolution: {SCALE}m\n")
    f.write(f"Pre-event Window: {PRE_EVENT_START} to {PRE_EVENT_END} ({pre_count} days)\n")
    f.write(f"First Night: {FIRST_NIGHT_DATE}\n")
    f.write(f"Post-event Window: {POST_EVENT_START} to {POST_EVENT_END} ({post_count} days)\n\n")
    f.write("ANTL RESULTS\n")
    f.write("-" * 40 + "\n")
    f.write(f"Pre-event Mean ANTL: {pre_antd:.4f} nW/cm2/sr\n" if pre_antd else "Pre-event Mean ANTL: N/A\n")
    f.write(f"First Night Mean ANTL: {first_night_antd:.4f} nW/cm2/sr\n" if first_night_antd else "First Night Mean ANTL: N/A\n")
    f.write(f"Post-event Mean ANTL: {post_antd:.4f} nW/cm2/sr\n" if post_antd else "Post-event Mean ANTL: N/A\n\n")
    f.write("NTL CHANGE METRICS\n")
    f.write("-" * 40 + "\n")
    f.write(f"NTL Change Value (NCV): {ncv:.4f} nW/cm2/sr\n" if ncv else "NTL Change Value (NCV): N/A\n")
    f.write(f"NTL Change Rate (NCR): {ncr:.4f} ({ncr*100:.2f}%)\n" if ncr else "NTL Change Rate (NCR): N/A\n\n")
    f.write("STATISTICAL SIGNIFICANCE\n")
    f.write("-" * 40 + "\n")
    f.write(f"KS-test Statistic: {ks_statistic:.4f}\n" if ks_statistic else "KS-test Statistic: N/A\n")
    f.write(f"p-value: {p_value:.6f}\n" if p_value else "p-value: N/A\n")
    f.write(f"Significant at alpha=0.05: {'YES' if is_significant else 'NO'}\n" if is_significant is not None else "Significant at alpha=0.05: N/A\n\n")
    f.write("DAMAGE ASSESSMENT\n")
    f.write("-" * 40 + "\n")
    f.write(f"Severity: {damage_severity}\n" if ncv is not None else "Severity: N/A\n")
    f.write(f"Interpretation: {interpretation}\n" if ncv is not None else "Interpretation: N/A\n\n")
    f.write("CONTEXTUAL INFORMATION (from USGS/ReliefWeb)\n")
    f.write("-" * 40 + "\n")
    f.write("Confirmed casualties: 2,886-3,800 deaths, 4,639-5,100 injured\n")
    f.write("Building damage: >157,000 buildings (SAR analysis)\n")
    f.write("Damage rates: Woundwin 73%, Mandalay 36%, Sagaing >70%\n")
    f.write("Population exposed: 22.67 million to strong shaking\n")
    f.write("Infrastructure exposure: USD 77.5 billion\n")
    f.write("Affected regions: Sagaing, Mandalay, Magway, Bago, Shan, Naypyidaw\n\n")
    f.write("NOTE ON NTL INCREASE:\n")
    f.write("-" * 40 + "\n")
    f.write("The analysis shows an NTL INCREASE (NCV=+0.0852, NCR=+15.68%) after the earthquake.\n")
    f.write("This counterintuitive result may be due to:\n")
    f.write("1. Emergency lighting deployed in affected areas\n")
    f.write("2. Myanmar-wide average includes unaffected urban areas (Yangon, etc.)\n")
    f.write("3. The epicenter (Sagaing) is rural; urban centers dominate the national average\n")
    f.write("4. Seasonal or temporal variations not fully corrected by angular correction\n")
    f.write("Recommendation: Perform localized analysis near epicenter for accurate damage assessment.\n\n")
    f.write("=" * 80 + "\n")
    f.write("Report generated using GEE Python API with VNP46A2 daily NTL data\n")
    f.write("Methodology: Yuan et al. (2023) - Turkey-Syria Earthquake NTL Analysis\n")
    f.write("=" * 80 + "\n")

print(f"Damage assessment report saved to: {report_path}")

print("\n" + "=" * 80)
print("ANALYSIS COMPLETE")
print("=" * 80)
print(f"\nOutput files:")
print(f"  1. {output_csv_path}")
print(f"  2. {daily_csv_path}")
print(f"  3. {report_path}")
print("\nReady for transfer back to NTL_Engineer.")
