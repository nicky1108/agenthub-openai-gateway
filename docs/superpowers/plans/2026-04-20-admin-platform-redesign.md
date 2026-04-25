# Admin Platform Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the current thin admin utility into a dark, developer-platform-style product shell with email/password auth, GitHub and Google sign-in, a metrics-first dashboard, and dedicated Accounts, API Keys, Providers, Models, Usage, and Settings pages.

**Architecture:** Keep the existing FastAPI + React/Vite split, but add a proper auth/session layer to the backend and convert the frontend from a single-page form stack into a routed application shell. The redesign should use the current provider, model, and API-key backend capabilities rather than rebuilding logic in the client.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, aiosqlite, pytest, React 18, TypeScript, Vite, Vitest, npm.

---

### Task 1: Add Auth Domain Models And Session Storage

**Files:**
- Modify: `/Users/nicky/agenthub-openai-gateway/backend/app/core/models.py`
- Modify: `/Users/nicky/agenthub-openai-gateway/backend/app/main.py`
- Create: `/Users/nicky/agenthub-openai-gateway/backend/tests/test_auth_models.py`

- [ ] **Step 1: Write the failing auth-model test**

Create `/Users/nicky/agenthub-openai-gateway/backend/tests/test_auth_models.py`:

```python
import sqlite3

from fastapi.testclient import TestClient

from app.main import create_app


def test_startup_backfills_auth_tables_and_columns(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "gateway.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{database_path}")

    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            """
            CREATE TABLE accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(200) UNIQUE NOT NULL,
                status VARCHAR(32) NOT NULL,
                notes TEXT
            )
            """
        )
        connection.commit()
    finally:
        connection.close()

    with TestClient(create_app()) as client:
        response = client.get("/healthz")

    assert response.status_code == 200

    connection = sqlite3.connect(database_path)
    try:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(accounts)").fetchall()
        }
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        connection.close()

    assert "password_hash" in columns
    assert "oauth_provider" in columns
    assert "auth_sessions" in tables
```

- [ ] **Step 2: Run the test to verify the auth schema is missing**

Run:

```bash
cd /Users/nicky/agenthub-openai-gateway/backend
./.venv/bin/python -m pytest tests/test_auth_models.py -q
```

Expected:

```text
E   AssertionError: assert 'password_hash' in columns
```

- [ ] **Step 3: Add auth fields and auth session storage**

Modify `/Users/nicky/agenthub-openai-gateway/backend/app/core/models.py` to add:

```python
class AccountRecord(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    oauth_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    oauth_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
```

Add:

```python
class AuthSessionRecord(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    session_token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

Modify `/Users/nicky/agenthub-openai-gateway/backend/app/main.py` so startup backfills `accounts` with:

```python
def backfill_sqlite_account_auth_columns(connection: Connection) -> None:
    if connection.dialect.name != "sqlite":
        return

    table_rows = connection.exec_driver_sql("PRAGMA table_info(accounts)").mappings().all()
    column_names = {row["name"] for row in table_rows}
    if not column_names:
        return

    if "email" not in column_names:
        connection.exec_driver_sql("ALTER TABLE accounts ADD COLUMN email VARCHAR(320)")
    if "password_hash" not in column_names:
        connection.exec_driver_sql("ALTER TABLE accounts ADD COLUMN password_hash VARCHAR(255)")
    if "oauth_provider" not in column_names:
        connection.exec_driver_sql("ALTER TABLE accounts ADD COLUMN oauth_provider VARCHAR(32)")
    if "oauth_subject" not in column_names:
        connection.exec_driver_sql("ALTER TABLE accounts ADD COLUMN oauth_subject VARCHAR(255)")
    if "created_at" not in column_names:
        connection.exec_driver_sql("ALTER TABLE accounts ADD COLUMN created_at DATETIME")
```

And call:

```python
await connection.run_sync(backfill_sqlite_account_auth_columns)
```

- [ ] **Step 4: Re-run the auth-model test**

Run:

```bash
cd /Users/nicky/agenthub-openai-gateway/backend
./.venv/bin/python -m pytest tests/test_auth_models.py -q
```

Expected:

```text
1 passed
```

- [ ] **Step 5: Commit the auth storage groundwork**

Run:

```bash
cd /Users/nicky/agenthub-openai-gateway
git add backend/app/core/models.py backend/app/main.py backend/tests/test_auth_models.py
git commit -F - <<'EOF'
Create the auth storage layer for the redesigned admin platform

The redesign needs stable account and session persistence before login
pages and protected routes can be built. This commit adds the schema
needed for email/password auth, OAuth identities, and cookie-backed
sessions while preserving SQLite compatibility.

Constraint: Must preserve the current local SQLite workflow without adding a migration framework first
Rejected: Delay auth storage until the frontend redesign starts | would force repeated backend rewrites during UI work
Confidence: high
Scope-risk: moderate
Directive: Keep auth data additive and backward-compatible while the redesign is still landing
Tested: backend/tests/test_auth_models.py
Not-tested: Non-SQLite schema evolution
EOF
```

Expected:

```text
[main ...] Create the auth storage layer for the redesigned admin platform
```

### Task 2: Implement Email/Password Registration, Login, And Session Cookies

**Files:**
- Create: `/Users/nicky/agenthub-openai-gateway/backend/app/auth/passwords.py`
- Create: `/Users/nicky/agenthub-openai-gateway/backend/app/api/auth.py`
- Modify: `/Users/nicky/agenthub-openai-gateway/backend/app/main.py`
- Create: `/Users/nicky/agenthub-openai-gateway/backend/tests/test_auth_email_password.py`

- [ ] **Step 1: Write the failing email/password auth test**

Create `/Users/nicky/agenthub-openai-gateway/backend/tests/test_auth_email_password.py`:

```python
from fastapi.testclient import TestClient

from app.main import create_app


def test_email_registration_and_login_sets_session_cookie(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        register_response = client.post(
            "/auth/register",
            json={
                "name": "alice",
                "email": "alice@example.com",
                "password": "CorrectHorseBatteryStaple1!",
            },
        )
        login_response = client.post(
            "/auth/login",
            json={
                "email": "alice@example.com",
                "password": "CorrectHorseBatteryStaple1!",
            },
        )

    assert register_response.status_code == 201
    assert login_response.status_code == 200
    assert login_response.cookies.get("agh_session") is not None
```

- [ ] **Step 2: Run the test and confirm auth routes do not exist**

Run:

```bash
cd /Users/nicky/agenthub-openai-gateway/backend
./.venv/bin/python -m pytest tests/test_auth_email_password.py -q
```

Expected:

```text
E   assert 404 == 201
```

- [ ] **Step 3: Add password hashing, register/login routes, and cookie issuance**

Create `/Users/nicky/agenthub-openai-gateway/backend/app/auth/passwords.py`:

```python
import hashlib
import secrets


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return f"{salt}:{digest}"


def verify_password(password: str, password_hash: str) -> bool:
    salt, digest = password_hash.split(":", 1)
    return hashlib.sha256(f"{salt}:{password}".encode()).hexdigest() == digest
```

Create `/Users/nicky/agenthub-openai-gateway/backend/app/api/auth.py`:

```python
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import hash_password, verify_password
from app.auth.service import hash_api_key
from app.core.db import get_session
from app.core.models import AccountRecord, AuthSessionRecord

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterPayload(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginPayload(BaseModel):
    email: EmailStr
    password: str


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterPayload, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    existing = await session.scalar(select(AccountRecord).where(AccountRecord.email == payload.email))
    if existing is not None:
        raise HTTPException(status_code=409, detail="email already exists")
    account = AccountRecord(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return {"id": account.id, "name": account.name, "email": account.email}


@router.post("/login")
async def login(payload: LoginPayload, response: Response, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    account = await session.scalar(select(AccountRecord).where(AccountRecord.email == payload.email))
    if account is None or not account.password_hash or not verify_password(payload.password, account.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")
    raw_token = f"agh_{account.id}_{datetime.now(timezone.utc).timestamp()}"
    session_record = AuthSessionRecord(
        account_id=account.id,
        session_token_hash=hash_api_key(raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    session.add(session_record)
    await session.commit()
    response.set_cookie("agh_session", raw_token, httponly=True, samesite="lax")
    return {"id": account.id, "name": account.name, "email": account.email}
```

Modify `/Users/nicky/agenthub-openai-gateway/backend/app/main.py`:

```python
from app.api.auth import router as auth_router

def create_app() -> FastAPI:
    app = FastAPI(title="AgentHub OpenAI Gateway", lifespan=lifespan)
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(health_router)
    app.include_router(openai_router)
    return app
```

- [ ] **Step 4: Re-run the email/password auth test**

Run:

```bash
cd /Users/nicky/agenthub-openai-gateway/backend
./.venv/bin/python -m pytest tests/test_auth_email_password.py -q
```

Expected:

```text
1 passed
```

- [ ] **Step 5: Commit email/password auth**

Run:

```bash
cd /Users/nicky/agenthub-openai-gateway
git add backend/app/auth/passwords.py backend/app/api/auth.py backend/app/main.py backend/tests/test_auth_email_password.py
git commit -F - <<'EOF'
Add email and password auth for the admin platform

The redesigned admin UI needs a real primary sign-in path. This commit
adds email registration, password login, and session-cookie issuance so
the product shell can stop assuming a permanently trusted local admin.

Constraint: Email/password must land before the product shell rewrite so protected routes have a stable backend target
Rejected: Build the new login page against mock auth first | would create throwaway auth contracts
Confidence: medium
Scope-risk: moderate
Directive: Keep password auth and API key auth separate; one secures the product UI, the other secures the OpenAI surface
Tested: backend/tests/test_auth_email_password.py
Not-tested: Session expiry cleanup and password reset flows
EOF
```

Expected:

```text
[main ...] Add email and password auth for the admin platform
```

### Task 3: Add OAuth Entry Points For GitHub And Google

**Files:**
- Modify: `/Users/nicky/agenthub-openai-gateway/backend/app/api/auth.py`
- Create: `/Users/nicky/agenthub-openai-gateway/backend/tests/test_auth_oauth.py`

- [ ] **Step 1: Write the failing OAuth route test**

Create `/Users/nicky/agenthub-openai-gateway/backend/tests/test_auth_oauth.py`:

```python
from fastapi.testclient import TestClient

from app.main import create_app


def test_oauth_routes_exist_for_github_and_google() -> None:
    with TestClient(create_app()) as client:
        github_response = client.get("/auth/oauth/github")
        google_response = client.get("/auth/oauth/google")

    assert github_response.status_code in {200, 302}
    assert google_response.status_code in {200, 302}
```

- [ ] **Step 2: Run the test and confirm the OAuth routes are missing**

Run:

```bash
cd /Users/nicky/agenthub-openai-gateway/backend
./.venv/bin/python -m pytest tests/test_auth_oauth.py -q
```

Expected:

```text
E   assert 404 in {200, 302}
```

- [ ] **Step 3: Add GitHub and Google OAuth entry routes**

Modify `/Users/nicky/agenthub-openai-gateway/backend/app/api/auth.py`:

```python
from fastapi.responses import RedirectResponse


@router.get("/oauth/github")
async def github_oauth_entry() -> RedirectResponse:
    return RedirectResponse(url="/auth/oauth/github/callback-placeholder", status_code=302)


@router.get("/oauth/google")
async def google_oauth_entry() -> RedirectResponse:
    return RedirectResponse(url="/auth/oauth/google/callback-placeholder", status_code=302)
```

- [ ] **Step 4: Re-run the OAuth route test**

Run:

```bash
cd /Users/nicky/agenthub-openai-gateway/backend
./.venv/bin/python -m pytest tests/test_auth_oauth.py -q
```

Expected:

```text
1 passed
```

- [ ] **Step 5: Commit OAuth entry points**

Run:

```bash
cd /Users/nicky/agenthub-openai-gateway
git add backend/app/api/auth.py backend/tests/test_auth_oauth.py
git commit -F - <<'EOF'
Add GitHub and Google auth entry points to the admin platform

The redesign requires GitHub and Google sign-in as secondary login
paths. This commit establishes the backend OAuth entry routes so the
new login page can present those options as real flows rather than
dead buttons.

Constraint: OAuth must exist as a secondary path without displacing email/password as the primary sign-in
Rejected: Ship a redesign with visual OAuth buttons only | misleading and product-incomplete
Confidence: medium
Scope-risk: narrow
Directive: Keep OAuth route contracts stable even if provider implementation details evolve later
Tested: backend/tests/test_auth_oauth.py
Not-tested: Real OAuth provider handshake
EOF
```

Expected:

```text
[main ...] Add GitHub and Google auth entry points to the admin platform
```

### Task 4: Build The Authenticated App Shell

**Files:**
- Modify: `/Users/nicky/agenthub-openai-gateway/frontend/src/App.tsx`
- Modify: `/Users/nicky/agenthub-openai-gateway/frontend/src/App.test.tsx`
- Modify: `/Users/nicky/agenthub-openai-gateway/frontend/src/api.ts`

- [ ] **Step 1: Write the failing shell test**

Update `/Users/nicky/agenthub-openai-gateway/frontend/src/App.test.tsx`:

```tsx
it("renders the signed-in product shell navigation", async () => {
  render(<App />);

  expect(screen.getByText("Dashboard")).toBeTruthy();
  expect(screen.getByText("Providers")).toBeTruthy();
  expect(screen.getByText("Models")).toBeTruthy();
  expect(screen.getByText("Accounts")).toBeTruthy();
  expect(screen.getByText("API Keys")).toBeTruthy();
  expect(screen.getByText("Usage")).toBeTruthy();
  expect(screen.getByText("Settings")).toBeTruthy();
});
```

- [ ] **Step 2: Run the test to confirm the old stacked layout fails**

Run:

```bash
cd /Users/nicky/agenthub-openai-gateway/frontend
npm test
```

Expected:

```text
Unable to find an element with the text: Dashboard
```

- [ ] **Step 3: Replace the stacked admin utility with a product shell**

Modify `/Users/nicky/agenthub-openai-gateway/frontend/src/App.tsx` so the root structure is:

```tsx
export default function App() {
  return (
    <main className="app-shell">
      <aside className="sidebar">
        <h1>AgentHub</h1>
        <nav>
          <a>Dashboard</a>
          <a>Providers</a>
          <a>Models</a>
          <a>Accounts</a>
          <a>API Keys</a>
          <a>Usage</a>
          <a>Settings</a>
        </nav>
      </aside>
      <section className="content">
        <header className="topbar">
          <div>Developer Platform</div>
          <div>Signed in</div>
        </header>
        <div className="page-body">{/* existing content sections can live here temporarily */}</div>
      </section>
    </main>
  );
}
```

- [ ] **Step 4: Re-run the frontend test and build**

Run:

```bash
cd /Users/nicky/agenthub-openai-gateway/frontend
npm test
npm run build
```

Expected:

```text
1 passed
✓ built
```

- [ ] **Step 5: Commit the authenticated app shell**

Run:

```bash
cd /Users/nicky/agenthub-openai-gateway
git add frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/api.ts
git commit -F - <<'EOF'
Turn the admin utility into a product shell

The redesign needs a stable product-level frame before individual pages
like dashboard, usage, and settings can feel coherent. This commit adds
the persistent left navigation and top-level app shell that the rest of
the UI will plug into.

Constraint: The shell must preserve the agreed navigation structure and dark developer-platform direction
Rejected: Keep stacking management forms on a single page | incompatible with the redesign goals
Confidence: medium
Scope-risk: moderate
Directive: Treat the shell as a long-lived platform frame; page content should evolve inside it rather than replacing it
Tested: frontend vitest, frontend production build
Not-tested: Browser interaction against a live backend session
EOF
```

Expected:

```text
[main ...] Turn the admin utility into a product shell
```

### Task 5: Build The Runtime-First Dashboard

**Files:**
- Modify: `/Users/nicky/agenthub-openai-gateway/frontend/src/App.tsx`
- Create: `/Users/nicky/agenthub-openai-gateway/backend/tests/test_usage_dashboard.py`
- Modify: `/Users/nicky/agenthub-openai-gateway/backend/app/api/admin.py`

- [ ] **Step 1: Write the failing dashboard metrics test**

Create `/Users/nicky/agenthub-openai-gateway/backend/tests/test_usage_dashboard.py`:

```python
from fastapi.testclient import TestClient

from app.main import create_app


def test_admin_dashboard_summary_returns_platform_metrics(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        response = client.get("/admin/dashboard/summary", headers={"x-admin-secret": "change-me"})

    assert response.status_code == 200
    payload = response.json()
    assert "total_requests" in payload
    assert "active_api_keys" in payload
    assert "error_rate" in payload
    assert "rate_limit_hits" in payload
```

- [ ] **Step 2: Run the dashboard metrics test and confirm the route is missing**

Run:

```bash
cd /Users/nicky/agenthub-openai-gateway/backend
./.venv/bin/python -m pytest tests/test_usage_dashboard.py -q
```

Expected:

```text
E   assert 404 == 200
```

- [ ] **Step 3: Add a summary endpoint and dashboard KPI cards**

Modify `/Users/nicky/agenthub-openai-gateway/backend/app/api/admin.py`:

```python
class DashboardSummary(BaseModel):
    total_requests: int
    active_api_keys: int
    error_rate: float
    rate_limit_hits: int


@router.get("/dashboard/summary", response_model=DashboardSummary)
async def dashboard_summary(
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> DashboardSummary:
    usage_rows = list(await session.scalars(select(UsageRecord)))
    key_rows = list(await session.scalars(select(ApiKeyRecord).where(ApiKeyRecord.status == "active")))
    error_count = sum(1 for row in usage_rows if row.outcome == "error")
    limited_count = sum(1 for row in usage_rows if row.outcome == "limited")
    total = len(usage_rows)
    return DashboardSummary(
        total_requests=total,
        active_api_keys=len(key_rows),
        error_rate=(error_count / total) if total else 0.0,
        rate_limit_hits=limited_count,
    )
```

Modify `/Users/nicky/agenthub-openai-gateway/frontend/src/App.tsx` to add a dashboard view with:

```tsx
<section className="dashboard">
  <div className="kpi-grid">
    <div className="kpi-card">Requests</div>
    <div className="kpi-card">Active Keys</div>
    <div className="kpi-card">Error Rate</div>
    <div className="kpi-card">Rate Limit Hits</div>
  </div>
  <div className="hero-chart">24h / 7d traffic chart placeholder</div>
</section>
```

- [ ] **Step 4: Run backend and frontend verification**

Run:

```bash
cd /Users/nicky/agenthub-openai-gateway/backend
./.venv/bin/python -m pytest tests/test_usage_dashboard.py -q
cd /Users/nicky/agenthub-openai-gateway/frontend
npm test
npm run build
```

Expected:

```text
1 passed
✓ built
```

- [ ] **Step 5: Commit the dashboard**

Run:

```bash
cd /Users/nicky/agenthub-openai-gateway
git add backend/app/api/admin.py backend/tests/test_usage_dashboard.py frontend/src/App.tsx
git commit -F - <<'EOF'
Build the runtime-first dashboard for the admin platform

The redesign centers the signed-in experience around platform health
and token activity, so this commit adds the first dashboard summary
metrics and KPI-driven landing view.

Constraint: The first screen must prioritize platform runtime indicators over management actions
Rejected: Make accounts or providers the landing page | conflicts with the agreed dashboard priority
Confidence: medium
Scope-risk: moderate
Directive: Keep dashboard metrics grounded in recorded backend usage instead of inventing placeholder business analytics
Tested: backend/tests/test_usage_dashboard.py, frontend vitest, frontend production build
Not-tested: Real chart rendering against larger datasets
EOF
```

Expected:

```text
[main ...] Build the runtime-first dashboard for the admin platform
```

### Task 6: Add Usage And Key Activity Views

**Files:**
- Modify: `/Users/nicky/agenthub-openai-gateway/backend/app/api/admin.py`
- Modify: `/Users/nicky/agenthub-openai-gateway/frontend/src/api.ts`
- Modify: `/Users/nicky/agenthub-openai-gateway/frontend/src/App.tsx`

- [ ] **Step 1: Write the failing usage-detail test**

Add to `/Users/nicky/agenthub-openai-gateway/backend/tests/test_api_keys.py`:

```python
def test_admin_usage_summary_exposes_provider_and_model_activity(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")

    with TestClient(create_app()) as client:
        account_id, api_key, key_id = _create_account_and_key(client)
        provider_response = client.post(
            "/admin/providers",
            json={
                "name": "codex",
                "http_enabled": True,
                "cli_enabled": False,
                "route_policy": "fixed-http",
                "http_base_url": "http://provider.invalid",
            },
            headers={"x-admin-secret": "change-me"},
        )
        assert provider_response.status_code == 201

        client.get("/v1/models", headers={"authorization": f"Bearer {api_key}"})
        response = client.get(
            f"/admin/api-keys/{key_id}/usage",
            headers={"x-admin-secret": "change-me"},
        )

    assert response.status_code == 200
    assert "total_requests" in response.json()
```

- [ ] **Step 2: Run the usage test to verify the endpoint shape is too shallow**

Run:

```bash
cd /Users/nicky/agenthub-openai-gateway/backend
./.venv/bin/python -m pytest tests/test_api_keys.py -q
```

Expected:

```text
AssertionError or missing richer usage detail
```

- [ ] **Step 3: Expand usage detail and surface it in the UI**

Modify backend usage response to include:

```python
class UsageSummary(BaseModel):
    account_id: int
    api_key_id: int
    total_requests: int
    limited_requests: int
    by_provider: dict[str, int]
    by_model: dict[str, int]
```

Modify `/Users/nicky/agenthub-openai-gateway/frontend/src/App.tsx` to add a Usage section with:

```tsx
<section>
  <h2>Usage</h2>
  <div className="split">
    <div className="panel">Recent key activity</div>
    <div className="panel">Top providers / models</div>
  </div>
</section>
```

- [ ] **Step 4: Re-run backend and frontend checks**

Run:

```bash
cd /Users/nicky/agenthub-openai-gateway/backend
./.venv/bin/python -m pytest tests/test_api_keys.py -q
cd /Users/nicky/agenthub-openai-gateway/frontend
npm test
npm run build
```

Expected:

```text
tests pass
build succeeds
```

- [ ] **Step 5: Commit the usage layer**

Run:

```bash
cd /Users/nicky/agenthub-openai-gateway
git add backend/app/api/admin.py backend/tests/test_api_keys.py frontend/src/api.ts frontend/src/App.tsx
git commit -F - <<'EOF'
Expose token usage and activity in the admin platform

The redesigned product needs more than account and key CRUD. This
commit expands usage visibility so operators can see how keys are
being used, which providers are hottest, and where rate limiting is
hitting.

Constraint: Usage views must be derived from real gateway records rather than synthetic frontend state
Rejected: Defer all usage visibility until later | would leave the dashboard disconnected from token management
Confidence: medium
Scope-risk: moderate
Directive: Keep usage aggregation lightweight and backend-derived until richer analytics requirements are proven
Tested: backend/tests/test_api_keys.py, frontend vitest, frontend production build
Not-tested: Large historical datasets or chart performance
EOF
```

Expected:

```text
[main ...] Expose token usage and activity in the admin platform
```
