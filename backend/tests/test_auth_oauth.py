from fastapi.testclient import TestClient

from app.main import create_app


def test_oauth_routes_exist_for_github_and_google() -> None:
    with TestClient(create_app()) as client:
        github_response = client.get("/auth/oauth/github", follow_redirects=False)
        google_response = client.get("/auth/oauth/google", follow_redirects=False)

    assert github_response.status_code in {200, 302}
    assert google_response.status_code in {200, 302}
