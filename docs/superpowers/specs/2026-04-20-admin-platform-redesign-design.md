# Admin Platform Redesign Design

## Summary

Redesign the current thin admin utility UI into a real product-grade management platform for the local-first OpenAI-compatible gateway.

This redesign keeps the current gateway backend capabilities, but changes the product surface in four major ways:

1. Add a real authentication system with email/password as the primary entry path.
2. Add GitHub and Google sign-in as secondary login options.
3. Replace the current utilitarian admin page with a dark, developer-platform-style application shell.
4. Make the post-login experience dashboard-first, with platform runtime metrics, token activity, account/key management, provider management, and usage visibility.

The initial product remains effectively single-tenant in daily use, but the data model and UI structure should be prepared for a future multi-account system where each account can own multiple API keys.

## Product Direction

### Deployment Shape

Current choice:

- single-instance product today
- multi-account capable data model
- future multi-tenant evolution is preserved but not fully implemented now

This means the redesign should avoid hardcoding assumptions that make future account isolation or team concepts impossible, even if the first real user experience is intentionally simple.

### Visual Direction

The visual direction is a dark developer platform, not a generic ops console and not a shallow admin CRUD tool.

Key characteristics:

- dark-first interface
- dense but readable information hierarchy
- product-grade shell, not a debug page
- charts and metrics with strong visual emphasis
- serious platform tone similar to API platforms and developer consoles

The interface should feel like a runtime control plane for a real product rather than an internal maintenance page.

## Authentication

### Sign-In Priorities

Primary sign-in method:

- email + password

Secondary sign-in methods:

- GitHub OAuth
- Google OAuth

All three should appear on the login page, but email/password is the primary visual action and GitHub/Google are secondary actions below or alongside it.

### Registration Policy

Registration policy:

- open registration
- administrators can disable accounts later

This keeps onboarding light while preserving operational control.

### Account Model

Each account can own multiple API keys.

The product should expose accounts as first-class objects. Keys, usage, and quotas are scoped to accounts.

At minimum, account records should support:

- `account_id`
- `name`
- `status`
- `notes`
- `created_at`

Status must support at least:

- `active`
- `disabled`

Disabled accounts must not be able to authenticate or use API keys.

## Application Shell

### Navigation

The signed-in left navigation should use this information architecture:

- `Dashboard`
- `Providers`
- `Models`
- `Accounts`
- `API Keys`
- `Usage`
- `Settings`

This navigation should remain stable even as capabilities expand.

### Shell Behavior

The shell should include:

- persistent sidebar navigation
- top bar with account/session controls
- a primary content area optimized for dashboards and management tables
- responsive behavior for narrower widths

The shell should feel like a product console, not like multiple unrelated forms stacked on one page.

## Dashboard

### Primary Role

The dashboard is the first screen after login and is platform-metrics-first.

It is not primarily an account list, provider list, or settings page. Its first job is to answer:

- Is the gateway healthy?
- Is traffic up or down?
- Are keys being used?
- Are rate limits or errors spiking?
- Which providers/models are hottest?

### First-Screen Priority

The first screen should prioritize platform runtime indicators over management-action indicators.

Recommended top metrics:

- total requests
- active API keys
- error rate
- rate-limit hits

### Time Windows

Dashboard charts must support:

- last 24 hours
- last 7 days

Default view:

- last 24 hours

The time-range selector should be available without making the interface feel like an analytics product first.

### Core Dashboard Modules

The initial dashboard should include:

1. KPI row for platform health
2. main traffic/activity chart
3. top models or top providers block
4. provider health block
5. recent auth or usage events block

The KPI row should be visually strong and immediately scannable.

The main chart should be the visual anchor of the page.

## Accounts And API Keys

### Accounts Page

The Accounts page should support:

- create account
- view account status
- disable account
- inspect account-level summaries

The first version does not need team membership, org roles, or nested RBAC.

### API Keys Page

The API Keys page should support:

- create key under an account
- list keys
- revoke key
- view key status
- view limit configuration
- view last used timestamp

Generated key secrets should be shown once at creation time and not displayed again.

### Quotas

Each key supports request-count limits at:

- per-minute
- per-hour
- per-day

The first version measures request counts, not provider-specific tokens or billing units.

### Usage Visibility

At minimum, key usage should support:

- total request count
- rate-limited count
- recent activity visibility
- provider/model attribution where available

The dashboard and usage pages should make token/key activity visible, not buried in raw logs.

## Providers And Models

### Providers Page

The Providers page should remain productized, not purely operational.

It should expose:

- provider name
- route policy
- transport enablement
- provider health summary
- discovery actions

Provider creation/editing remains necessary, but the experience should feel integrated into the platform shell.

### Models Page

The Models page should show the provider model catalog introduced in the current backend.

It should support:

- viewing discovered models
- manual override status
- enabling/disabling exposed models
- changing exposed model IDs
- rediscovery trigger visibility

This page is especially important now that `codex` and `gemini` can expose more than a single `default` model.

## Usage Page

The Usage page should be distinct from Dashboard.

Dashboard is the high-level operating picture.

Usage is the deeper drill-down for:

- per-account activity
- per-key activity
- provider/model distribution
- limit hits
- recent request patterns

The first version does not need a full BI surface, but it should support meaningful operational filtering and summaries.

## Settings

The Settings page should hold product-level configuration that does not fit naturally into the other pages.

Likely examples:

- auth provider configuration status
- gateway defaults
- admin metadata
- future branding or environment metadata

Settings should not become a dumping ground for every table that lacks a home.

## OAuth Considerations

### GitHub

GitHub sign-in is required as a secondary auth path.

The UX should make it feel like a first-class login option, but clearly secondary to email/password in visual hierarchy.

### Google

Google sign-in is required as a secondary auth path.

Because the earlier user wording referenced Gmail, the implementation should treat this as Google account sign-in rather than email inbox access.

The product should not imply Gmail mailbox permissions unless that is later added explicitly.

## Backend Alignment

This redesign must align with the current backend evolution:

- provider management already exists
- provider model catalog already exists
- API key auth and quotas are being added
- runtime usage exists and can be extended

The UI redesign should consume these backend capabilities instead of building shadow logic in the frontend.

## Scope For The Redesign Implementation

In scope for the upcoming implementation:

- auth pages and authenticated shell
- dashboard redesign
- left-nav app shell
- accounts and API keys management surfaces
- provider and model pages brought into the new design system
- usage page with the first useful token activity view
- dark developer-platform visual treatment

Out of scope for this redesign pass:

- full organization/team/RBAC system
- billing or payment workflows
- full charting analytics product behavior
- invite-only registration system
- deep profile/settings ecosystem

## Risks

### Scope Creep

This redesign touches authentication, shell architecture, navigation, dashboard, and data pages. It is easy for it to grow into a full SaaS platform build. The implementation must keep its focus on the current gateway product.

### Auth Complexity

Adding email/password plus GitHub and Google sign-in can easily explode backend scope if handled ad hoc. The implementation should centralize session handling and avoid custom one-off auth behavior per provider.

### Visual Overreach

The current backend is strong enough to justify a real product shell, but the UI must not promise observability or workflow depth that the backend does not yet expose.

### Data Availability

Some dashboard metrics may require extending the current usage recording or aggregation logic. The implementation should expose only metrics that are grounded in actual recorded data.

## Recommendation

Build this redesign as a dark developer platform with:

- email/password primary auth
- GitHub and Google secondary auth
- a stable left-nav product shell
- a runtime-first dashboard
- dedicated accounts, API keys, providers, models, usage, and settings pages

Keep the first real user experience single-instance and straightforward, but preserve account ownership and future multi-account evolution in the data model and page structure.
