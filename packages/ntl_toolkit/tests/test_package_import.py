def test_package_exposes_version() -> None:
    import ntl_toolkit

    assert ntl_toolkit.__version__ == "0.1.0"
