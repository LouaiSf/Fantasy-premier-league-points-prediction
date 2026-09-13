from __future__ import annotations

from webapp.app import app


def test_platform_shell_exposes_every_primary_surface() -> None:
    # Given the production Flask application.
    client = app.test_client()

    # When the platform shell is requested.
    response = client.get("/")

    # Then every primary product surface is present in the server-rendered DOM.
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    for surface in (
        "My Team",
        "Transfer Studio",
        "Player Comparison",
        "Captain &amp; Form",
        "News Wire",
        "Fixture Matrix",
    ):
        assert surface in body
