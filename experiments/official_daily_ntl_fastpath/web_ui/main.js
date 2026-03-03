const AUTO_REFRESH_MS = 180000;
const DEFAULT_LAYER_ID = "VIIRS_NOAA20_DayNightBand";
const DEFAULT_QUERY_DAYS = 10;
const DEFAULT_QUERY_SOURCES = "nrt_priority";
const ROGUE_SKY_URL = "https://sky.rogue.space/";
const PRIMARY_ORBIT_SLOT = {
  slot: "snpp_viirs",
  defaultSearch: "NPP",
  defaultLabelZh: "SNPP VIIRS",
  defaultLabelEn: "SNPP VIIRS"
};
const ORBIT_SEARCH_CHOICES = [
  { search: "NPP", labelZh: "SNPP VIIRS", labelEn: "SNPP VIIRS" },
  { search: "SDGSAT", labelZh: "SDGSAT-1", labelEn: "SDGSAT-1" },
  // Rogue Sky query parser does not decode `%20`/`+` reliably.
  // Use no-space INTLDES aliases that are proven searchable in Rogue Sky.
  { search: "2017-073A", labelZh: "NOAA 20 VIIRS", labelEn: "NOAA 20 VIIRS" },
  { search: "2022-150A", labelZh: "NOAA 21 VIIRS", labelEn: "NOAA 21 VIIRS" },
  { search: "JILIN", labelZh: "吉林1号", labelEn: "JILIN 1" },
  { search: "LUOJIA", labelZh: "LUOJIA-1", labelEn: "LUOJIA-1" }
];

const GEE_SOURCE_LIST = [
  { id: "NASA/VIIRS/002/VNP46A2", label: "VNP46A2 (Daily)", band: "Gap_Filled_DNB_BRDF_Corrected_NTL" },
  { id: "NOAA/VIIRS/001/VNP46A1", label: "VNP46A1 (Daily)", band: "DNB_At_Sensor_Radiance_500m" },
  { id: "NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG", label: "VCMSLCFG (Monthly)", band: "avg_rad" },
  { id: "NOAA/VIIRS/DNB/ANNUAL_V22", label: "VIIRS Annual V22", band: "average" },
  { id: "NOAA/VIIRS/DNB/ANNUAL_V21", label: "VIIRS Annual V21", band: "average" },
  { id: "NOAA/DMSP-OLS/NIGHTTIME_LIGHTS", label: "DMSP-OLS Annual", band: "avg_vis" },
  { id: "projects/sat-io/open-datasets/npp-viirs-ntl", label: "NPP-VIIRS-Like (Annual)", band: "b1" }
];

const STUDY_AREA_FALLBACK = {
  countries: ["China", "Myanmar", "United States of America", "Japan", "India"],
  provincesByCountry: {
    China: [
      "Beijing", "Tianjin", "Shanghai", "Chongqing",
      "Hebei", "Shanxi", "Liaoning", "Jilin", "Heilongjiang",
      "Jiangsu", "Zhejiang", "Anhui", "Fujian", "Jiangxi", "Shandong",
      "Henan", "Hubei", "Hunan", "Guangdong", "Hainan",
      "Sichuan", "Guizhou", "Yunnan", "Shaanxi", "Gansu", "Qinghai",
      "Inner Mongolia", "Guangxi", "Tibet", "Ningxia", "Xinjiang",
      "Hong Kong", "Macau", "Taiwan"
    ],
    Myanmar: ["Yangon", "Mandalay"],
    "United States of America": ["California", "New York"],
    Japan: ["Tokyo", "Osaka"],
    India: ["Maharashtra", "Delhi"]
  },
  citiesByCountryProvince: {
    "China||Beijing": ["Beijing"],
    "China||Tianjin": ["Tianjin"],
    "China||Shanghai": ["Shanghai"],
    "China||Chongqing": ["Chongqing"],
    "China||Hebei": ["Shijiazhuang"],
    "China||Shanxi": ["Taiyuan"],
    "China||Liaoning": ["Shenyang"],
    "China||Jilin": ["Changchun"],
    "China||Heilongjiang": ["Harbin"],
    "China||Guangdong": ["Guangzhou", "Shenzhen"],
    "China||Jiangsu": ["Nanjing", "Suzhou"],
    "China||Zhejiang": ["Hangzhou", "Ningbo"],
    "China||Anhui": ["Hefei"],
    "China||Fujian": ["Fuzhou", "Xiamen"],
    "China||Jiangxi": ["Nanchang"],
    "China||Shandong": ["Jinan", "Qingdao"],
    "China||Henan": ["Zhengzhou"],
    "China||Hubei": ["Wuhan"],
    "China||Hunan": ["Changsha"],
    "China||Hainan": ["Haikou"],
    "China||Sichuan": ["Chengdu"],
    "China||Guizhou": ["Guiyang"],
    "China||Yunnan": ["Kunming"],
    "China||Shaanxi": ["Xi'an"],
    "China||Gansu": ["Lanzhou"],
    "China||Qinghai": ["Xining"],
    "China||Inner Mongolia": ["Hohhot"],
    "China||Guangxi": ["Nanning"],
    "China||Tibet": ["Lhasa"],
    "China||Ningxia": ["Yinchuan"],
    "China||Xinjiang": ["Urumqi"],
    "China||Hong Kong": ["Hong Kong"],
    "China||Macau": ["Macau"],
    "China||Taiwan": ["Taipei"],
    "Myanmar||Yangon": ["Yangon"],
    "Myanmar||Mandalay": ["Mandalay"],
    "United States of America||California": ["Los Angeles"],
    "United States of America||New York": ["New York"],
    "Japan||Tokyo": ["Tokyo"],
    "Japan||Osaka": ["Osaka"],
    "India||Maharashtra": ["Mumbai"],
    "India||Delhi": ["Delhi"]
  }
};

const GEE_BAND_OPTIONS = {
  "NASA/VIIRS/002/VNP46A2": [
    "DNB_BRDF_Corrected_NTL",
    "Gap_Filled_DNB_BRDF_Corrected_NTL",
    "DNB_Lunar_Irradiance",
    "Latest_High_Quality_Retrieval",
    "Mandatory_Quality_Flag",
    "QF_Cloud_Mask",
    "Snow_Flag"
  ],
  "NOAA/VIIRS/001/VNP46A1": [
    "DNB_At_Sensor_Radiance_500m",
    "BrightnessTemperature_M12",
    "BrightnessTemperature_M13",
    "BrightnessTemperature_M15",
    "BrightnessTemperature_M16",
    "Glint_Angle",
    "Granule",
    "Lunar_Zenith",
    "Lunar_Azimuth",
    "Moon_Illumination_Fraction",
    "Moon_Phase_Angle",
    "QF_Cloud_Mask",
    "QF_DNB",
    "QF_VIIRS_M10",
    "QF_VIIRS_M11",
    "QF_VIIRS_M12",
    "QF_VIIRS_M13",
    "QF_VIIRS_M15",
    "QF_VIIRS_M16",
    "Radiance_M10",
    "Radiance_M11",
    "Sensor_Zenith",
    "Sensor_Azimuth",
    "Solar_Zenith",
    "Solar_Azimuth",
    "UTC_Time"
  ],
  "NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG": [
    "avg_rad",
    "cf_cvg"
  ],
  "NOAA/VIIRS/DNB/ANNUAL_V22": [
    "average",
    "average_masked",
    "cf_cvg",
    "cvg",
    "maximum",
    "median",
    "median_masked",
    "minimum"
  ],
  "NOAA/VIIRS/DNB/ANNUAL_V21": [
    "average",
    "average_masked",
    "cf_cvg",
    "cvg",
    "maximum",
    "median",
    "median_masked",
    "minimum"
  ],
  "NOAA/DMSP-OLS/NIGHTTIME_LIGHTS": [
    "avg_vis",
    "stable_lights",
    "cf_cvg",
    "avg_lights_x_pct"
  ],
  "projects/sat-io/open-datasets/npp-viirs-ntl": [
    "b1"
  ]
};

const I18N = {
  zh: {
    title: "官方 Daily NTL 快速监控",
    subtitle: "NRT 优先可用性 + GIBS 影像渲染。",
    language: "语言",
    studyArea: "研究区域",
    studyCountry: "国家",
    studyProvince: "省份/州",
    studyCity: "市级",
    studyCountryDefault: "请选择国家",
    studyProvinceDefault: "请选择省份/州",
    studyCityDefault: "请选择市级",
    studyCatalogOfficial: "研究区域目录：官方 GAUL（国家 {countries} | 省州 {provinces} | 市级 {cities}）",
    studyCatalogFallback: "研究区域目录：回退列表（有限），可重启服务启用官方目录",
    bbox: "边界框",
    queryBtn: "查询可用性",
    autoRefresh: "每 3 分钟自动刷新",
    downloadSection: "数据下载",
    testingPhase: "测试阶段",
    downloadProvider: "下载通道",
    providerGee: "GEE",
    providerOfficial: "官方源",
    downloadSource: "下载数据源",
    downloadFormat: "下载格式",
    fmtRawH5: "原始 .h5/.nc",
    fmtClippedTif: "裁剪 .tif",
    timeStart: "开始日期",
    timeEnd: "结束日期",
    geeBand: "GEE 波段",
    downloadDataBtn: "下载数据",
    colSource: "Source",
    colGlobalLatest: "全局最新",
    colGlobalLag: "全局滞后(天)",
    colBBoxLatest: "区域最新",
    colBBoxLag: "区域滞后(天)",
    viewMode: "视图",
    view2d: "二维影像",
    view3d: "三维轨道",
    layer: "图层",
    renderMode: "渲染模式",
    modeTiles: "全球瓦片",
    modeSnapshot: "区域快照",
    region: "区域",
    regionGlobal: "全球",
    regionChina: "中国",
    regionShanghai: "上海",
    regionCustom: "自定义(使用 BBox)",
    loadBtn: "加载影像",
    date: "日期",
    opacity: "透明度",
    snapshotPx: "快照像素",
    mapNote: "瓦片源：NASA GIBS WMTS EPSG:3857。URL 由浏览器基于图层+日期生成。",

    dataStatusFmt: "数据状态：{text}",
    dataReady: "就绪",
    dataQuerying: "正在查询最新可用性...",
    dataUpdated: "已更新 {ts} | 窗口 {start} -> {end}",
    dataFailed: "失败：{msg}",
    dataDownloadPreparing: "正在下载 {source} ({format})...",
    dataDownloadDone: "下载完成：{filename}",
    dataDownloadFailed: "下载失败：{msg}",

    layerStatusFmt: "图层状态：{text}",
    layerWaitingQuery: "等待查询",
    layerDirtyDefault: "参数已更新，请点击“加载影像”",
    layerDirtyConfirmed: "参数已确认，请点击“加载影像”",
    layerDirtyApiFailed: "API 失败，等待手动加载",
    layerDirtyCustomBbox: "自定义 BBox 已更新，请点击“加载影像”",
    layerLoadingSnapshot: "正在加载快照 {layer} ({date})...",
    layerSuccessSnapshot: "快照加载成功 {layer} ({date})",
    layerFailedSnapshot: "快照加载失败 {layer} ({date})",
    layerLoadingTiles: "正在加载瓦片 {layer} ({date})...",
    layerFirstTileOk: "{layer} ({date}) 首个瓦片加载成功",
    layerTileErrors: "{layer} ({date}) 瓦片错误数={errors}",
    layerSuccessTiles: "成功 ({loaded}/{requested} 瓦片)",
    layerPartialTiles: "部分成功 ({loaded} 成功, {errors} 失败)",
    layerFailedTiles: "失败 (0 成功, {errors} 错误)",
    layerOpacityUpdated: "透明度已更新",
    orbitStatusFmt: "轨道状态：{text}",
    orbitIdle: "未加载",
    orbitFailed: "轨道加载失败：{msg}",
    orbitRogueLoadingMulti: "正在加载同页卫星窗口（共 {total} 个）...",
    orbitRogueReadyMulti: "同页卫星窗口加载完成（{loaded}/{total}）",
    orbitRoguePartialMulti: "同页卫星窗口部分加载（{loaded}/{total}）",
    orbitRogueBlocked: "Rogue Sky 嵌入失败，请点击下方链接在新标签页打开",
    orbitHintsLabel: "可搜索卫星",
    rogueOpenNewTab: "在新标签页打开",
    rogueWindowOpen: "打开"
  },
  en: {
    title: "Official Daily NTL Fast Monitor",
    subtitle: "NRT priority availability + global render (GIBS).",
    language: "Language",
    studyArea: "Study Area",
    studyCountry: "Country",
    studyProvince: "Province/State",
    studyCity: "City",
    studyCountryDefault: "Select country",
    studyProvinceDefault: "Select province/state",
    studyCityDefault: "Select city",
    studyCatalogOfficial: "Study area catalog: official GAUL (countries {countries} | provinces {provinces} | cities {cities})",
    studyCatalogFallback: "Study area catalog: fallback list (limited); restart server to enable official catalog",
    bbox: "BBox",
    queryBtn: "Query Availability",
    autoRefresh: "Auto refresh every 3 minutes",
    downloadSection: "Data Download",
    testingPhase: "Testing",
    downloadProvider: "Provider",
    providerGee: "GEE",
    providerOfficial: "Official",
    downloadSource: "Download Source",
    downloadFormat: "Download Format",
    fmtRawH5: "Raw .h5/.nc",
    fmtClippedTif: "Clipped .tif",
    timeStart: "Start Date",
    timeEnd: "End Date",
    geeBand: "GEE Band",
    downloadDataBtn: "Download Data",
    colSource: "Source",
    colGlobalLatest: "Global Latest",
    colGlobalLag: "Global Lag (d)",
    colBBoxLatest: "BBox Latest",
    colBBoxLag: "BBox Lag (d)",
    viewMode: "View",
    view2d: "2D Imagery",
    view3d: "3D Orbit",
    layer: "Layer",
    renderMode: "Render Mode",
    modeTiles: "Global Tiles",
    modeSnapshot: "Region Snapshot",
    region: "Region",
    regionGlobal: "Global",
    regionChina: "China",
    regionShanghai: "Shanghai",
    regionCustom: "Custom (use BBox)",
    loadBtn: "Load Imagery",
    date: "Date",
    opacity: "Opacity",
    snapshotPx: "Snapshot px",
    mapNote: "Tiles: NASA GIBS WMTS EPSG:3857. URL generated in browser from selected layer/date.",

    dataStatusFmt: "Data status: {text}",
    dataReady: "ready",
    dataQuerying: "querying latest availability ...",
    dataUpdated: "Updated {ts} | window {start} -> {end}",
    dataFailed: "failed: {msg}",
    dataDownloadPreparing: "downloading {source} ({format}) ...",
    dataDownloadDone: "downloaded: {filename}",
    dataDownloadFailed: "download failed: {msg}",

    layerStatusFmt: "Layer status: {text}",
    layerWaitingQuery: "waiting for query",
    layerDirtyDefault: "parameters updated, click \"Load Imagery\".",
    layerDirtyConfirmed: "parameters confirmed, click \"Load Imagery\".",
    layerDirtyApiFailed: "waiting for manual load (API failed).",
    layerDirtyCustomBbox: "custom bbox updated, click \"Load Imagery\".",
    layerLoadingSnapshot: "loading snapshot {layer} ({date}) ...",
    layerSuccessSnapshot: "success snapshot {layer} ({date})",
    layerFailedSnapshot: "failed snapshot {layer} ({date})",
    layerLoadingTiles: "loading tiles {layer} ({date}) ...",
    layerFirstTileOk: "loaded {layer} ({date}), first tile OK",
    layerTileErrors: "tile errors={errors} for {layer} ({date})",
    layerSuccessTiles: "success ({loaded}/{requested} tiles)",
    layerPartialTiles: "partial ({loaded} ok, {errors} failed)",
    layerFailedTiles: "failed (0 loaded, {errors} errors)",
    layerOpacityUpdated: "opacity updated",
    orbitStatusFmt: "Orbit status: {text}",
    orbitIdle: "idle",
    orbitFailed: "orbit failed: {msg}",
    orbitRogueLoadingMulti: "loading in-page orbit windows ({total}) ...",
    orbitRogueReadyMulti: "in-page orbit windows loaded ({loaded}/{total})",
    orbitRoguePartialMulti: "in-page orbit windows partial ({loaded}/{total})",
    orbitRogueBlocked: "Rogue Sky embed failed, open it in a new tab",
    orbitHintsLabel: "Searchable Satellites",
    rogueOpenNewTab: "Open in new tab",
    rogueWindowOpen: "Open"
  }
};

const FALLBACK_GIBS_LAYERS = [
  { id: "VIIRS_NOAA20_DayNightBand", label: "NOAA20 DayNightBand (NRT)", matrix_set: "GoogleMapsCompatible_Level7", format: "jpg" },
  { id: "VIIRS_SNPP_DayNightBand", label: "SNPP DayNightBand (NRT)", matrix_set: "GoogleMapsCompatible_Level7", format: "jpg" },
  { id: "VIIRS_NOAA21_DayNightBand", label: "NOAA21 DayNightBand", matrix_set: "GoogleMapsCompatible_Level7", format: "jpg" }
];

const state = {
  autoTimer: null,
  gibsLayers: [],
  viewMode: "2d",
  overlay: null,
  map: null,
  rogueSkyBound: false,
  rogueSkyLoadTimer: null,
  rogueSkyCycle: 0,
  rogueSkyTotalCount: 0,
  rogueSkyLoadedCount: 0,
  rogueSkyFailedCount: 0,
  orbitSearchChoice: ORBIT_SEARCH_CHOICES[0],
  overlayStats: null,
  hasRenderedLayer: false,
  lang: "zh",
  statusModel: { key: "dataReady", vars: {}, isError: false },
  layerStatusModel: { key: "layerWaitingQuery", vars: {}, level: "warn" },
  orbitStatusModel: { key: "orbitIdle", vars: {}, level: "warn" },
  latestRows: [],
  studyAreaCatalog: {
    countries: [],
    provinces: [],
    cities: []
  },
  studyAreaCatalogMode: "fallback"
};

function qs(id) {
  return document.getElementById(id);
}

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function t(key, vars = {}) {
  const dict = I18N[state.lang] || I18N.en;
  const template = dict[key] ?? I18N.en[key] ?? key;
  return template.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? ""));
}

function setStatusModel(key, vars = {}, isError = false) {
  state.statusModel = { key, vars, isError };
  renderStatus();
}

function renderStatus() {
  const el = qs("status");
  const msg = t(state.statusModel.key, state.statusModel.vars);
  el.textContent = t("dataStatusFmt", { text: msg });
  el.style.color = state.statusModel.isError ? "#ff9f9f" : "#44d7b6";
}

function setLayerStatusModel(key, vars = {}, level = "ok") {
  state.layerStatusModel = { key, vars, level };
  renderLayerStatus();
}

function renderLayerStatus() {
  const el = qs("layerStatus");
  if (!el) return;
  const msg = t(state.layerStatusModel.key, state.layerStatusModel.vars);
  el.textContent = t("layerStatusFmt", { text: msg });
  el.classList.remove("ok", "warn", "err");
  if (state.layerStatusModel.level) {
    el.classList.add(state.layerStatusModel.level);
  }
}

function setOrbitStatusModel(key, vars = {}, level = "warn") {
  state.orbitStatusModel = { key, vars, level };
  renderOrbitStatus();
}

function renderOrbitStatus() {
  const el = qs("orbitStatus");
  if (!el) return;
  const msg = t(state.orbitStatusModel.key, state.orbitStatusModel.vars);
  el.textContent = t("orbitStatusFmt", { text: msg });
  el.classList.remove("ok", "warn", "err", "hidden");
  if (state.orbitStatusModel.level) {
    el.classList.add(state.orbitStatusModel.level);
  }
  if (state.viewMode !== "3d") {
    el.classList.add("hidden");
  }
}

function markLayerDirty(key = "layerDirtyDefault") {
  setLayerStatusModel(key, {}, "warn");
}

function renderStudyAreaStatus() {
  const el = qs("studyAreaStatus");
  if (!el) return;
  const countries = _toNameList(state.studyAreaCatalog.countries).length;
  const provinces = _toNameList(state.studyAreaCatalog.provinces).length;
  const cities = _toNameList(state.studyAreaCatalog.cities).length;
  const key = state.studyAreaCatalogMode === "official" ? "studyCatalogOfficial" : "studyCatalogFallback";
  el.textContent = t(key, { countries, provinces, cities });
}

function _toNameList(values) {
  if (!Array.isArray(values)) return [];
  const out = [];
  const seen = new Set();
  for (const v of values) {
    const s = String(v || "").trim();
    if (!s || seen.has(s)) continue;
    seen.add(s);
    out.push(s);
  }
  return out;
}

async function _fetchStudyAreaCatalog(params = {}) {
  const q = new URLSearchParams();
  if (params.country) q.set("country", params.country);
  if (params.province) q.set("province", params.province);
  q.set("limit", "2000");
  const url = `/api/study_areas?${q.toString()}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({}));
    throw new Error(payload.error || `HTTP ${res.status}`);
  }
  return await res.json();
}

function populateStudyCountries(selectedCountry = "China") {
  const select = qs("studyCountry");
  if (!select) return;
  select.innerHTML = "";

  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = t("studyCountryDefault");
  select.appendChild(placeholder);

  const countries = _toNameList(state.studyAreaCatalog.countries);
  countries.forEach((country) => {
    const opt = document.createElement("option");
    opt.value = country;
    opt.textContent = country;
    if (country === selectedCountry) opt.selected = true;
    select.appendChild(opt);
  });
}

function populateStudyProvinces(selectedProvince = "") {
  const countryVal = (qs("studyCountry")?.value || "").trim();
  const select = qs("studyProvince");
  if (!select) return;
  select.innerHTML = "";

  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = t("studyProvinceDefault");
  select.appendChild(placeholder);

  const provinces = _toNameList(state.studyAreaCatalog.provinces);
  provinces.forEach((province) => {
    const opt = document.createElement("option");
    opt.value = province;
    opt.textContent = province;
    if (province === selectedProvince) opt.selected = true;
    select.appendChild(opt);
  });
}

function populateStudyCities(selectedCity = "") {
  const select = qs("studyCity");
  if (!select) return;
  select.innerHTML = "";

  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = t("studyCityDefault");
  select.appendChild(placeholder);

  const cities = _toNameList(state.studyAreaCatalog.cities);
  cities.forEach((city) => {
    const opt = document.createElement("option");
    opt.value = city;
    opt.textContent = city;
    if (city === selectedCity) opt.selected = true;
    select.appendChild(opt);
  });
}

async function initStudyAreaSelectors() {
  const fallbackCountry = "China";
  const fallbackProvince = "Shanghai";
  const fallbackCity = "Shanghai";

  try {
    const payload = await _fetchStudyAreaCatalog();
    const countries = _toNameList(payload.countries);
    state.studyAreaCatalog.countries = countries.length ? countries : STUDY_AREA_FALLBACK.countries;
    state.studyAreaCatalogMode = countries.length ? "official" : "fallback";
  } catch (_err) {
    state.studyAreaCatalog.countries = STUDY_AREA_FALLBACK.countries;
    state.studyAreaCatalogMode = "fallback";
  }

  const selectedCountry = state.studyAreaCatalog.countries.includes(fallbackCountry)
    ? fallbackCountry
    : (state.studyAreaCatalog.countries[0] || "");
  populateStudyCountries(selectedCountry);

  await loadStudyProvinces(selectedCountry, fallbackProvince);
  await loadStudyCities(selectedCountry, qs("studyProvince").value || fallbackProvince, fallbackCity);
}

async function loadStudyProvinces(country, preferred = "") {
  let provinces = [];
  try {
    const payload = await _fetchStudyAreaCatalog({ country });
    provinces = _toNameList(payload.provinces);
    if (provinces.length) state.studyAreaCatalogMode = "official";
  } catch (_err) {
    provinces = STUDY_AREA_FALLBACK.provincesByCountry[country] || [];
    state.studyAreaCatalogMode = "fallback";
  }
  state.studyAreaCatalog.provinces = provinces;
  const selected = provinces.includes(preferred) ? preferred : (provinces[0] || "");
  populateStudyProvinces(selected);
}

async function loadStudyCities(country, province, preferred = "") {
  let cities = [];
  try {
    const payload = await _fetchStudyAreaCatalog({ country, province });
    cities = _toNameList(payload.cities);
    if (cities.length) state.studyAreaCatalogMode = "official";
  } catch (_err) {
    const key = `${country}||${province}`;
    cities = STUDY_AREA_FALLBACK.citiesByCountryProvince[key] || [];
    state.studyAreaCatalogMode = "fallback";
  }
  state.studyAreaCatalog.cities = cities;
  const selected = cities.includes(preferred) ? preferred : (cities[0] || "");
  populateStudyCities(selected);
  renderStudyAreaStatus();
}

function getSelectedStudyArea() {
  const city = (qs("studyCity")?.value || "").trim();
  const province = (qs("studyProvince")?.value || "").trim();
  const country = (qs("studyCountry")?.value || "").trim();
  if (city) return country && !city.toLowerCase().includes(country.toLowerCase()) ? `${city}, ${country}` : city;
  if (province) return country && !province.toLowerCase().includes(country.toLowerCase()) ? `${province}, ${country}` : province;
  return country;
}

function applyI18n() {
  document.documentElement.lang = state.lang;
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  const c = (qs("studyCountry")?.value || "").trim();
  const p = (qs("studyProvince")?.value || "").trim();
  const city = (qs("studyCity")?.value || "").trim();
  populateStudyCountries(c);
  populateStudyProvinces(p);
  populateStudyCities(city);
  renderStudyAreaStatus();
  const autoWrap = qs("autoRefreshText")?.parentElement;
  if (autoWrap) {
    autoWrap.title = t("autoRefresh");
  }
  renderOrbitHintChips();
  renderRogueSkyCardTexts();
  renderStatus();
  renderLayerStatus();
  renderOrbitStatus();
}

function setLanguage(lang) {
  state.lang = lang === "en" ? "en" : "zh";
  localStorage.setItem("ntl_fast_monitor_lang", state.lang);
  applyI18n();
}

function buildApiUrl() {
  const params = new URLSearchParams();
  const studyArea = getSelectedStudyArea();
  const bbox = qs("bbox").value.trim();
  if (studyArea) params.set("study_area", studyArea);
  if (bbox) params.set("bbox", bbox);
  params.set("days", String(DEFAULT_QUERY_DAYS));
  params.set("sources", DEFAULT_QUERY_SOURCES);
  return `/api/latest?${params.toString()}`;
}

function parseBboxInput(raw) {
  if (!raw) return null;
  const parts = raw.split(",").map((x) => Number(x.trim()));
  if (parts.length !== 4 || parts.some((x) => Number.isNaN(x))) return null;
  const [minLon, minLat, maxLon, maxLat] = parts;
  if (maxLon < minLon || maxLat < minLat) return null;
  return { minLon, minLat, maxLon, maxLat };
}

function resolveRegionBounds() {
  const preset = qs("regionPreset").value;
  if (preset === "china") return { minLon: 73, minLat: 18, maxLon: 135, maxLat: 54 };
  if (preset === "shanghai") return { minLon: 120.85, minLat: 30.65, maxLon: 122.25, maxLat: 31.9 };
  if (preset === "custom") {
    const custom = parseBboxInput(qs("bbox").value.trim());
    if (custom) return custom;
  }
  return { minLon: -180, minLat: -85, maxLon: 180, maxLat: 85 };
}

function buildRogueSatelliteUrl(searchToken, slotId) {
  const base = ROGUE_SKY_URL.replace(/\/+$/, "").replace(/\?+$/, "");
  const search = String(searchToken || "").trim();
  const slot = String(slotId || "").trim();
  const query = [
    `search=${encodeURIComponent(search)}`,
    `slot=${encodeURIComponent(slot)}`,
    "from=ntl_fast_monitor"
  ].join("&");
  return `${base}/?${query}`;
}

function getOrbitChoiceLabel(choice) {
  if (!choice) return state.lang === "zh" ? PRIMARY_ORBIT_SLOT.defaultLabelZh : PRIMARY_ORBIT_SLOT.defaultLabelEn;
  return state.lang === "zh" ? choice.labelZh : choice.labelEn;
}

function renderOrbitHintChips() {
  const wrap = qs("orbitHintChips");
  if (!wrap) return;
  if (!wrap.dataset.bound) {
    wrap.innerHTML = "";
    for (const choice of ORBIT_SEARCH_CHOICES) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "orbit-chip";
      btn.dataset.search = choice.search;
      btn.addEventListener("click", () => {
        const selected = ORBIT_SEARCH_CHOICES.find((x) => x.search === choice.search);
        if (!selected) return;
        state.orbitSearchChoice = selected;
        renderOrbitHintChips();
        renderRogueSkyCardTexts();
        if (state.viewMode === "3d") {
          activateRogueSkyView(true);
        }
      });
      wrap.appendChild(btn);
    }
    wrap.dataset.bound = "1";
  }

  const activeSearch = state.orbitSearchChoice?.search || PRIMARY_ORBIT_SLOT.defaultSearch;
  wrap.querySelectorAll(".orbit-chip").forEach((btn) => {
    const search = btn.dataset.search || "";
    const choice = ORBIT_SEARCH_CHOICES.find((x) => x.search === search);
    btn.textContent = getOrbitChoiceLabel(choice);
    btn.classList.toggle("active", search === activeSearch);
  });
}

function renderRogueSkyCardTexts() {
  const grid = qs("rogueSkyGrid");
  if (!grid) return;
  const choice = state.orbitSearchChoice || ORBIT_SEARCH_CHOICES[0];
  const titleText = getOrbitChoiceLabel(choice);
  const slotTag = String(choice.search || PRIMARY_ORBIT_SLOT.defaultSearch).toLowerCase();
  const url = buildRogueSatelliteUrl(choice.search, slotTag);

  grid.querySelectorAll(".rogue-card").forEach((card) => {
    const title = card.querySelector(".rogue-card-title");
    const link = card.querySelector(".rogue-card-link");
    const frame = card.querySelector(".rogue-card-frame");
    if (title) title.textContent = titleText;
    if (link) {
      link.textContent = t("rogueWindowOpen");
      link.href = url;
    }
    if (frame) {
      frame.title = titleText;
      frame.dataset.search = choice.search;
      frame.dataset.slot = slotTag;
    }
  });
}

function _updateRogueLoadStatus() {
  const loaded = state.rogueSkyLoadedCount;
  const total = state.rogueSkyTotalCount;
  const failed = state.rogueSkyFailedCount;
  const done = loaded + failed;
  if (done < total) return;

  if (state.rogueSkyLoadTimer) {
    clearTimeout(state.rogueSkyLoadTimer);
    state.rogueSkyLoadTimer = null;
  }

  if (loaded === total) {
    setOrbitStatusModel("orbitRogueReadyMulti", { loaded, total }, "ok");
    return;
  }
  if (loaded > 0) {
    setOrbitStatusModel("orbitRoguePartialMulti", { loaded, total }, "warn");
    return;
  }
  setOrbitStatusModel("orbitRogueBlocked", {}, "warn");
}

function _buildRogueSkyGrid() {
  const grid = qs("rogueSkyGrid");
  if (!grid || state.rogueSkyBound) return;
  grid.innerHTML = "";
  const choice = state.orbitSearchChoice || ORBIT_SEARCH_CHOICES[0];
  const slotTag = String(choice.search || PRIMARY_ORBIT_SLOT.defaultSearch).toLowerCase();
  const card = document.createElement("section");
  card.className = "rogue-card";
  card.dataset.slot = slotTag;

  const head = document.createElement("div");
  head.className = "rogue-card-head";

  const title = document.createElement("h3");
  title.className = "rogue-card-title";
  title.textContent = getOrbitChoiceLabel(choice);
  head.appendChild(title);

  const link = document.createElement("a");
  link.className = "rogue-card-link";
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = t("rogueWindowOpen");
  link.href = buildRogueSatelliteUrl(choice.search, slotTag);
  head.appendChild(link);

  const frame = document.createElement("iframe");
  frame.className = "rogue-card-frame";
  frame.loading = "lazy";
  frame.referrerPolicy = "no-referrer-when-downgrade";
  frame.allowFullscreen = true;
  frame.title = getOrbitChoiceLabel(choice);
  frame.dataset.slot = slotTag;
  frame.dataset.search = choice.search;

  frame.addEventListener("load", () => {
    const cycle = Number(frame.dataset.loadCycle || "0");
    if (!cycle || cycle !== state.rogueSkyCycle) return;
    state.rogueSkyLoadedCount += 1;
    _updateRogueLoadStatus();
  });
  frame.addEventListener("error", () => {
    const cycle = Number(frame.dataset.loadCycle || "0");
    if (!cycle || cycle !== state.rogueSkyCycle) return;
    state.rogueSkyFailedCount += 1;
    _updateRogueLoadStatus();
  });

  card.appendChild(head);
  card.appendChild(frame);
  grid.appendChild(card);
  state.rogueSkyBound = true;
  renderRogueSkyCardTexts();
  renderOrbitHintChips();
}

function activateRogueSkyView(forceReload = false) {
  _buildRogueSkyGrid();
  const grid = qs("rogueSkyGrid");
  const frames = Array.from(grid?.querySelectorAll(".rogue-card-frame") || []);
  if (frames.length === 0) {
    setOrbitStatusModel("orbitFailed", { msg: "missing rogue iframe grid" }, "err");
    return;
  }

  if (!forceReload && frames.every((frame) => !!frame.src)) {
    setOrbitStatusModel("orbitRogueReadyMulti", { loaded: frames.length, total: frames.length }, "ok");
    return;
  }

  if (state.rogueSkyLoadTimer) {
    clearTimeout(state.rogueSkyLoadTimer);
    state.rogueSkyLoadTimer = null;
  }

  state.rogueSkyCycle += 1;
  const cycle = state.rogueSkyCycle;
  state.rogueSkyTotalCount = frames.length;
  state.rogueSkyLoadedCount = 0;
  state.rogueSkyFailedCount = 0;

  setOrbitStatusModel("orbitRogueLoadingMulti", { total: frames.length }, "warn");

  frames.forEach((frame) => {
    const slot = frame.dataset.slot || "";
    const search = frame.dataset.search || "";
    frame.dataset.loadCycle = String(cycle);
    frame.src = buildRogueSatelliteUrl(search, slot);
  });

  state.rogueSkyLoadTimer = setTimeout(() => {
    if (state.viewMode !== "3d" || cycle !== state.rogueSkyCycle) return;
    const loaded = state.rogueSkyLoadedCount;
    const total = state.rogueSkyTotalCount;
    if (loaded > 0) {
      setOrbitStatusModel("orbitRoguePartialMulti", { loaded, total }, "warn");
    } else {
      setOrbitStatusModel("orbitRogueBlocked", {}, "warn");
    }
  }, 15000);
}

function _applyViewModeLayout() {
  const is3d = state.viewMode === "3d";
  qs("map")?.classList.toggle("hidden", is3d);
  qs("rogueSkyWrap")?.classList.toggle("hidden", !is3d);
  qs("layerStatus")?.classList.toggle("hidden", is3d);
  qs("orbitStatus")?.classList.toggle("hidden", !is3d);
  qs("orbitSearchHints")?.classList.toggle("hidden", !is3d);
  qs("renderModeWrap")?.classList.toggle("hidden", is3d);
  qs("regionPresetWrap")?.classList.toggle("hidden", is3d);
  qs("layerWrap")?.classList.toggle("hidden", is3d);
  qs("mapDateWrap")?.classList.toggle("hidden", is3d);
  qs("snapshotSizeWrap")?.classList.toggle("hidden", is3d);
  qs("opacityWrap")?.classList.toggle("hidden", is3d);
  qs("applyLayerWrap")?.classList.toggle("hidden", is3d);
  qs("mapNote")?.classList.toggle("hidden", is3d);
  if (!is3d) {
    setOrbitStatusModel("orbitIdle", {}, "warn");
    if (state.map) {
      setTimeout(() => state.map.invalidateSize(), 80);
    }
  } else {
    renderOrbitHintChips();
    activateRogueSkyView(false);
  }
  renderOrbitStatus();
}

async function setViewMode(mode) {
  state.viewMode = mode === "3d" ? "3d" : "2d";
  qs("viewMode").value = state.viewMode;
  _applyViewModeLayout();
  if (state.viewMode === "3d") {
    activateRogueSkyView(false);
  }
}

function renderTable(rows) {
  const tbody = qs("resultTable").querySelector("tbody");
  tbody.innerHTML = "";
  for (const row of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.source || ""}</td>
      <td>${row.latest_global_date || "-"}</td>
      <td>${row.latest_global_lag_days ?? "-"}</td>
      <td>${row.latest_bbox_date || "-"}</td>
      <td>${row.latest_bbox_lag_days ?? "-"}</td>
    `;
    tbody.appendChild(tr);
  }
}

function mergeRowsWithGee(payload) {
  const officialRows = Array.isArray(payload?.rows) ? [...payload.rows] : [];
  const geeRowsRaw = Array.isArray(payload?.gee_rows) ? payload.gee_rows : [];
  if (geeRowsRaw.length === 0) {
    const fallback = {
      source: "GEE (no gee_rows in /api/latest; restart monitor_server)",
      latest_global_date: "-",
      latest_global_lag_days: "-",
      latest_bbox_date: "-",
      latest_bbox_lag_days: "-"
    };
    return [fallback, ...officialRows];
  }
  const geeRows = geeRowsRaw.map((row) => ({
    source: row.error ? `${row.source} (error)` : row.source,
    latest_global_date: row.latest_global_date || "-",
    latest_global_lag_days: row.latest_global_lag_days ?? "-",
    latest_bbox_date: row.latest_bbox_date || "-",
    latest_bbox_lag_days: row.latest_bbox_lag_days ?? "-"
  }));
  return [...geeRows, ...officialRows];
}

function populateLayerSelect(gibsLayers) {
  const select = qs("layerSelect");
  if (!gibsLayers || gibsLayers.length === 0) return;
  const current = select.value || (gibsLayers.some((x) => x.id === DEFAULT_LAYER_ID) ? DEFAULT_LAYER_ID : "");
  select.innerHTML = "";
  gibsLayers.forEach((item, idx) => {
    const opt = document.createElement("option");
    opt.value = item.id;
    opt.textContent = item.label;
    opt.dataset.matrixSet = item.matrix_set;
    opt.dataset.format = item.format;
    if ((current && current === item.id) || (!current && idx === 0)) opt.selected = true;
    select.appendChild(opt);
  });
}

function getDownloadDateRange() {
  const start = (qs("downloadStartDate")?.value || todayIso()).trim();
  const end = (qs("downloadEndDate")?.value || start).trim();
  if (end < start) {
    throw new Error("end_date must be >= start_date");
  }
  return { start, end };
}

function getMapDate() {
  const value = (qs("mapDate")?.value || todayIso()).trim();
  return value || todayIso();
}

function populateDownloadSources() {
  const provider = (qs("downloadProvider")?.value || "gee").trim().toLowerCase();
  const select = qs("downloadSource");
  const current = select.value;
  select.innerHTML = "";

  if (provider === "official") {
    const rows = state.latestRows || [];
    const seen = new Set();
    const sources = [];
    for (const row of rows) {
      const s = String(row.source || "").trim();
      if (!s || seen.has(s)) continue;
      seen.add(s);
      sources.push(s);
    }
    if (sources.length === 0) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "-";
      select.appendChild(opt);
      return;
    }
    sources.forEach((s) => {
      const opt = document.createElement("option");
      opt.value = s;
      opt.textContent = s;
      if (current && current === s) opt.selected = true;
      select.appendChild(opt);
    });
    return;
  }

  GEE_SOURCE_LIST.forEach((o, idx) => {
    const opt = document.createElement("option");
    opt.value = o.id;
    opt.textContent = o.label;
    opt.dataset.defaultBand = o.band;
    if ((current && current === o.id) || (!current && idx === 0)) opt.selected = true;
    select.appendChild(opt);
  });
  populateGeeBandOptions();
}

function populateGeeBandOptions() {
  const provider = (qs("downloadProvider")?.value || "gee").trim().toLowerCase();
  const bandSelect = qs("geeBand");
  if (!bandSelect) return;
  const previous = bandSelect.value;
  const selectedSource = qs("downloadSource")?.selectedOptions?.[0];
  const defaultBand = selectedSource?.dataset?.defaultBand || "";
  bandSelect.innerHTML = "";
  if (provider !== "gee") return;

  const datasetId = qs("downloadSource")?.value || "";
  const bands = GEE_BAND_OPTIONS[datasetId] || [];
  if (bands.length === 0) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "-";
    bandSelect.appendChild(opt);
    return;
  }

  bands.forEach((band, idx) => {
    const opt = document.createElement("option");
    opt.value = band;
    opt.textContent = band;
    if ((previous && previous === band) || (!previous && idx === 0)) {
      opt.selected = true;
    }
    bandSelect.appendChild(opt);
  });

  if (defaultBand && bands.includes(defaultBand)) {
    bandSelect.value = defaultBand;
  }
}

function updateDownloadModeUI() {
  const provider = (qs("downloadProvider")?.value || "gee").trim().toLowerCase();
  const isGee = provider === "gee";
  qs("officialFormatWrap")?.classList.toggle("hidden", isGee);
  qs("geeBandWrap")?.classList.toggle("hidden", !isGee);

  populateDownloadSources();
  if (isGee) {
    populateGeeBandOptions();
    syncGeeDefaults();
  }
}

function syncGeeDefaults() {
  const selected = qs("downloadSource").selectedOptions[0];
  if (selected) {
    const defaultBand = selected.dataset.defaultBand || "";
    const bandSelect = qs("geeBand");
    const hasCurrent = Array.from(bandSelect.options).some((opt) => opt.value === bandSelect.value);
    if (defaultBand && !hasCurrent) bandSelect.value = defaultBand;
    if (!bandSelect.value && defaultBand) bandSelect.value = defaultBand;
  }
}

async function downloadDataFile() {
  const provider = (qs("downloadProvider").value || "gee").trim().toLowerCase();
  const source = qs("downloadSource").value.trim();
  if (!source) {
    setStatusModel("dataDownloadFailed", { msg: "source not selected" }, true);
    return;
  }

  const params = new URLSearchParams();
  params.set("provider", provider);
  params.set("source", source);

  const studyArea = getSelectedStudyArea();
  const bbox = qs("bbox").value.trim();
  if (studyArea) params.set("study_area", studyArea);
  if (bbox) params.set("bbox", bbox);
  let dateRange;
  try {
    dateRange = getDownloadDateRange();
  } catch (err) {
    setStatusModel("dataDownloadFailed", { msg: err.message || String(err) }, true);
    return;
  }
  params.set("start_date", dateRange.start);
  params.set("end_date", dateRange.end);

  let formatLabel = provider;
  if (provider === "official") {
    const outputFormat = qs("downloadFormat").value.trim();
    params.set("format", outputFormat);
    formatLabel = `${outputFormat} ${dateRange.start}${dateRange.end !== dateRange.start ? `..${dateRange.end}` : ""}`;
  } else {
    const band = qs("geeBand").value.trim();
    if (band) params.set("band", band);
    params.set("scale", "500");
    formatLabel = `${dateRange.start}${dateRange.end !== dateRange.start ? `..${dateRange.end}` : ""}`;
  }

  setStatusModel("dataDownloadPreparing", { source, format: formatLabel });
  const btn = qs("downloadDataBtn");
  btn.disabled = true;
  try {
    const res = await fetch(`/api/download_data?${params.toString()}`, { cache: "no-store" });
    if (!res.ok) {
      let errMsg = `HTTP ${res.status}`;
      if (res.status === 404) {
        errMsg = "download API route not found. Please restart monitor_server.py with latest code.";
      }
      try {
        const errPayload = await res.json();
        errMsg = errPayload.error || errMsg;
      } catch (_err) {}
      throw new Error(errMsg);
    }

    const blob = await res.blob();
    if (!blob || blob.size <= 0) {
      throw new Error("empty file");
    }

    const disposition = res.headers.get("Content-Disposition") || "";
    const fileNameMatch = disposition.match(/filename=\"?([^\";]+)\"?/i);
    const fallbackExt = provider === "official" && qs("downloadFormat").value === "clipped_tif" ? "tif" : "tif";
    const filename = fileNameMatch ? fileNameMatch[1] : `${source}.${fallbackExt}`;

    const href = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = href;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(href);

    setStatusModel("dataDownloadDone", { filename });
  } catch (err) {
    setStatusModel("dataDownloadFailed", { msg: err.message || String(err) }, true);
  } finally {
    btn.disabled = false;
  }
}

async function updateOverlayLayer() {
  if (state.viewMode === "3d") {
    activateRogueSkyView(false);
    return;
  }
  const select = qs("layerSelect");
  const date = getMapDate();
  const opacity = Number(qs("opacity").value) / 100;
  const selected = select.options[select.selectedIndex];
  if (!selected || !state.map) return;

  const layerId = selected.value;
  const matrixSet = selected.dataset.matrixSet || "GoogleMapsCompatible_Level7";
  const format = selected.dataset.format || "jpg";
  const renderMode = qs("renderMode").value;
  const region = resolveRegionBounds();
  const snapshotSize = Math.max(512, Math.min(4096, Number(qs("snapshotSize").value || 2048)));

  if (state.overlay) state.map.removeLayer(state.overlay);
  state.hasRenderedLayer = true;
  state.overlayStats = { requested: 0, loaded: 0, errors: 0, layerId, date };

  if (renderMode === "snapshot") {
    const bboxWms = `${region.minLat},${region.minLon},${region.maxLat},${region.maxLon}`;
    const url = new URL("https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi");
    url.searchParams.set("SERVICE", "WMS");
    url.searchParams.set("REQUEST", "GetMap");
    url.searchParams.set("VERSION", "1.3.0");
    url.searchParams.set("LAYERS", layerId);
    url.searchParams.set("STYLES", "");
    url.searchParams.set("FORMAT", "image/png");
    url.searchParams.set("TRANSPARENT", "TRUE");
    url.searchParams.set("HEIGHT", String(snapshotSize));
    url.searchParams.set("WIDTH", String(snapshotSize));
    url.searchParams.set("CRS", "EPSG:4326");
    url.searchParams.set("BBOX", bboxWms);
    url.searchParams.set("TIME", date);

    const bounds = [[region.minLat, region.minLon], [region.maxLat, region.maxLon]];
    setLayerStatusModel("layerLoadingSnapshot", { layer: layerId, date }, "warn");
    state.overlay = L.imageOverlay(url.toString(), bounds, { opacity });
    state.overlay.on("load", () => setLayerStatusModel("layerSuccessSnapshot", { layer: layerId, date }, "ok"));
    state.overlay.on("error", () => setLayerStatusModel("layerFailedSnapshot", { layer: layerId, date }, "err"));
    state.overlay.addTo(state.map);
    state.map.fitBounds(bounds, { animate: false, padding: [20, 20] });
    return;
  }

  const tileUrl = `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/${layerId}/default/${date}/${matrixSet}/{z}/{y}/{x}.${format}`;
  setLayerStatusModel("layerLoadingTiles", { layer: layerId, date }, "warn");

  state.overlay = L.tileLayer(tileUrl, { opacity, attribution: "NASA GIBS" });
  state.overlay.on("tileloadstart", () => {
    if (!state.overlayStats) return;
    state.overlayStats.requested += 1;
  });
  state.overlay.on("tileload", () => {
    if (!state.overlayStats) return;
    state.overlayStats.loaded += 1;
    if (state.overlayStats.loaded === 1) {
      setLayerStatusModel("layerFirstTileOk", { layer: state.overlayStats.layerId, date: state.overlayStats.date }, "ok");
    }
  });
  state.overlay.on("tileerror", () => {
    if (!state.overlayStats) return;
    state.overlayStats.errors += 1;
    setLayerStatusModel("layerTileErrors", { errors: state.overlayStats.errors, layer: state.overlayStats.layerId, date: state.overlayStats.date }, "err");
  });
  state.overlay.on("load", () => {
    if (!state.overlayStats) return;
    const s = state.overlayStats;
    if (s.loaded > 0 && s.errors === 0) return setLayerStatusModel("layerSuccessTiles", { loaded: s.loaded, requested: s.requested }, "ok");
    if (s.loaded > 0 && s.errors > 0) return setLayerStatusModel("layerPartialTiles", { loaded: s.loaded, errors: s.errors }, "warn");
    setLayerStatusModel("layerFailedTiles", { errors: s.errors }, "err");
  });
  state.overlay.addTo(state.map);
}

async function refresh() {
  setStatusModel("dataQuerying");
  try {
    const res = await fetch(buildApiUrl(), { cache: "no-store" });
    const payload = await res.json();
    if (!res.ok || payload.ok === false) {
      throw new Error(payload.error || `HTTP ${res.status}`);
    }

    state.latestRows = payload.rows || [];
    renderTable(mergeRowsWithGee(payload));

    state.gibsLayers = payload.gibs_layers || FALLBACK_GIBS_LAYERS;
    populateLayerSelect(state.gibsLayers);
    populateDownloadSources();

    if (!state.hasRenderedLayer) markLayerDirty("layerDirtyConfirmed");

    setStatusModel("dataUpdated", {
      ts: payload.generated_at_utc,
      start: payload.start_date,
      end: payload.end_date
    });
    if (state.viewMode === "3d") {
      activateRogueSkyView(false);
    }
  } catch (err) {
    state.latestRows = [];
    renderTable([]);
    state.gibsLayers = FALLBACK_GIBS_LAYERS;
    populateLayerSelect(state.gibsLayers);
    populateDownloadSources();
    if (!state.hasRenderedLayer) markLayerDirty("layerDirtyApiFailed");
    setStatusModel("dataFailed", { msg: err.message }, true);
    if (state.viewMode === "3d") {
      setOrbitStatusModel("orbitRogueBlocked", {}, "warn");
    }
  }
}

function setupMap() {
  const map = L.map("map", { zoomControl: true }).setView([20, 0], 2);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
    attribution: "&copy; OpenStreetMap &copy; CARTO"
  }).addTo(map);
  state.map = map;
}

function setupEvents() {
  qs("queryForm").addEventListener("submit", (e) => {
    e.preventDefault();
    refresh();
  });
  qs("applyLayerBtn").addEventListener("click", () => {
    updateOverlayLayer();
  });
  qs("downloadDataBtn").addEventListener("click", downloadDataFile);
  qs("viewMode").addEventListener("change", async (e) => {
    await setViewMode(e.target.value);
  });

  const markDirtyHandler = () => markLayerDirty();
  qs("layerSelect").addEventListener("change", markDirtyHandler);
  qs("renderMode").addEventListener("change", markDirtyHandler);
  qs("regionPreset").addEventListener("change", markDirtyHandler);
  qs("studyCountry").addEventListener("change", async () => {
    const country = (qs("studyCountry").value || "").trim();
    await loadStudyProvinces(country, "");
    const province = (qs("studyProvince").value || "").trim();
    await loadStudyCities(country, province, "");
    markLayerDirty();
  });
  qs("studyProvince").addEventListener("change", async () => {
    const country = (qs("studyCountry").value || "").trim();
    const province = (qs("studyProvince").value || "").trim();
    await loadStudyCities(country, province, "");
    markLayerDirty();
  });
  qs("studyCity").addEventListener("change", markDirtyHandler);
  qs("downloadStartDate").addEventListener("change", () => {
    if (!qs("downloadEndDate").value) qs("downloadEndDate").value = qs("downloadStartDate").value;
    markLayerDirty();
  });
  qs("downloadEndDate").addEventListener("change", markDirtyHandler);
  qs("mapDate").addEventListener("change", markDirtyHandler);
  qs("snapshotSize").addEventListener("change", markDirtyHandler);
  qs("bbox").addEventListener("change", () => {
    if (qs("regionPreset").value === "custom") markLayerDirty("layerDirtyCustomBbox");
  });
  qs("opacity").addEventListener("input", () => {
    const opacity = Number(qs("opacity").value) / 100;
    if (state.viewMode === "3d") {
      return;
    } else if (state.overlay) {
      state.overlay.setOpacity(opacity);
      setLayerStatusModel("layerOpacityUpdated", {}, "ok");
    } else {
      markLayerDirty();
    }
  });

  qs("downloadProvider").addEventListener("change", updateDownloadModeUI);
  qs("downloadSource").addEventListener("change", () => {
    if ((qs("downloadProvider").value || "gee") === "gee") {
      populateGeeBandOptions();
      syncGeeDefaults();
    }
  });

  qs("autoRefresh").addEventListener("change", () => {
    const enabled = qs("autoRefresh").checked;
    if (state.autoTimer) {
      clearInterval(state.autoTimer);
      state.autoTimer = null;
    }
    if (enabled) state.autoTimer = setInterval(refresh, AUTO_REFRESH_MS);
  });
  qs("langSelect").addEventListener("change", (e) => setLanguage(e.target.value));
}

function init() {
  qs("downloadStartDate").value = todayIso();
  qs("downloadEndDate").value = todayIso();
  qs("mapDate").value = todayIso();
  qs("viewMode").value = "2d";

  const savedLang = localStorage.getItem("ntl_fast_monitor_lang");
  const browserLang = (navigator.language || "en").toLowerCase();
  state.lang = savedLang === "en" || savedLang === "zh" ? savedLang : (browserLang.startsWith("zh") ? "zh" : "en");
  qs("langSelect").value = state.lang;

  applyI18n();
  setLayerStatusModel("layerWaitingQuery", {}, "warn");
  setupMap();
  setupEvents();
  _applyViewModeLayout();

  state.gibsLayers = FALLBACK_GIBS_LAYERS;
  populateLayerSelect(state.gibsLayers);
  updateDownloadModeUI();

  markLayerDirty();
  initStudyAreaSelectors()
    .then(() => {
      refresh();
      state.autoTimer = setInterval(refresh, AUTO_REFRESH_MS);
    })
    .catch(() => {
      refresh();
      state.autoTimer = setInterval(refresh, AUTO_REFRESH_MS);
    });
}

window.addEventListener("DOMContentLoaded", init);
