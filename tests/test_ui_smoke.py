import os
import sys

import pytest

from UK_news_scraper.profiles import ProfileLoadReport, default_profile


pytestmark = pytest.mark.skipif(
    sys.platform.startswith("linux") and not os.environ.get("DISPLAY"),
    reason="Tk requires a display on Linux",
)


def test_desktop_app_builds_recovery_run_and_result_controls(monkeypatch):
    from UK_news_scraper import ui

    profile = default_profile()
    monkeypatch.setattr(
        ui,
        "load_profiles_with_recovery",
        lambda: ProfileLoadReport({profile.profile_id: profile}),
    )
    monkeypatch.setattr(ui, "load_run_history", lambda _path: [])

    app = ui.UKNewsApp()
    try:
        app.update_idletasks()

        assert str(app.cancel_button["state"]) == "disabled"
        assert str(app.retry_button["state"]) == "disabled"
        assert app.result_min_score_var.get() == 0
        assert app.result_max_score_var.get() == 999
        assert app.history_tree.get_children() == ()
    finally:
        app.destroy()
