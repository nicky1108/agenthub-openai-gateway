from fastapi.testclient import TestClient

from app.main import create_app


def test_oauth_routes_exist_for_github_and_google() -> None:
    with TestClient(create_app()) as client:
        github_response = client.get("/auth/oauth/github")
        google_response = client.get("/auth/oauth/google")

    assert github_response.status_code == 200
    assert github_response.json() == {
        "provider": "github",
        "status": "not_implemented",
        "detail": "OAuth entry point placeholder",
    }
    assert google_response.status_code == 200
    assert google_response.json() == {
        "provider": "google",
        "status": "not_implemented",
        "detail": "OAuth entry point placeholder",
    }
