from actual_starling_connector import __version__, main


def test_version() -> None:
    assert __version__ == "0.0.1"


def test_main_is_callable() -> None:
    assert callable(main)
