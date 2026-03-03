from pathlib import Path


def _read(path: str) -> str:
    return (Path(__file__).resolve().parent.parent / path).read_text(encoding='utf-8')


def test_gee_download_global_geoboundaries_supports_adm3_adm4():
    content = _read('tools/GEE_download.py')
    assert 'WM/geoLab/geoBoundaries/600/ADM3' in content
    assert 'WM/geoLab/geoBoundaries/600/ADM4' in content
    assert 'Literal["country", "province", "city", "county", "district"]' in content


def test_data_searcher_tools_prefers_geoboundaries_over_osm():
    content = _read('tools/__init__.py')
    assert 'get_administrative_division_geoboundaries_tool' in content
    # Non-target variation: OSM tool remains importable for backward compatibility, but should not be in active data_searcher_tools list.
    active_list = content.split('data_searcher_tools =', 1)[1]
    assert 'get_administrative_division_osm_tool' not in active_list


def test_geoboundaries_tool_defaults_to_shp_conversion():
    content = _read('tools/global_admin_boundary_fetch.py')
    assert 'output_format: str = "shp"' in content
    assert 'convert_geojson_to_shp: bool = True' in content
