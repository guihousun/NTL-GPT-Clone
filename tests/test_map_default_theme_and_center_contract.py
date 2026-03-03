from pathlib import Path


def test_map_default_center_and_zoom_are_china_scoped():
    text = Path("app_ui.py").read_text(encoding="utf-8")

    assert "default_map_center = [35.0, 104.0]" in text
    assert "default_map_zoom = 4" in text


def test_map_default_base_layer_is_dark_and_satellite_remains_available():
    text = Path("app_ui.py").read_text(encoding="utf-8")

    assert "folium.Map(location=default_map_center, zoom_start=default_map_zoom, control_scale=True, tiles=None)" in text
    assert 'folium.TileLayer("CartoDB dark_matter", name="Dark Canvas", show=True).add_to(m)' in text
    assert 'name="Satellite"' in text and "show=False" in text
    assert 'map_component_key = f"main_map_{thread_id}_{map_nonce}"' in text
