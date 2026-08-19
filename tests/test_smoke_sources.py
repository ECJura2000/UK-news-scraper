from scripts.smoke_sources import SOURCES


def test_smoke_sources_track_dsit_successor_departments():
    assert "DSIT" not in SOURCES
    assert SOURCES["BIST"].endswith(
        "/department-for-business-innovation-science-and-trade"
    )
    assert SOURCES["DCMS"].endswith("/department-for-culture-media-and-sport")
