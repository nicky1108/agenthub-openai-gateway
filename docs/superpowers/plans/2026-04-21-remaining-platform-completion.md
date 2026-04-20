# Remaining Platform Completion Plan

## Goal

Finish the product gaps that still leave the admin platform feeling incomplete:

1. replace the fake `24h / 7d` dashboard toggle with real time-window traffic data
2. replace the Settings placeholder with a real control-plane overview
3. replace OAuth placeholder routes and buttons with configurable GitHub / Google flows and graceful disabled states

## Scope

- backend admin APIs for dashboard series and settings overview
- backend auth OAuth start/callback routes with environment-driven enablement
- frontend dashboard wiring for live 24h/7d charts
- frontend settings page with runtime/auth visibility
- frontend auth screen wiring for real OAuth entry behavior

## Execution Order

1. add backend tests for dashboard series, settings overview, and OAuth route behavior
2. implement backend APIs and OAuth service/settings support
3. add frontend tests for dashboard window switching and settings/auth rendering
4. wire the frontend to the new APIs and remove the remaining placeholders
5. run backend and frontend verification, restart local services, and push the finished work

## Risks

- real OAuth cannot be fully live-tested without provider credentials
- dashboard bucketing must stay simple and reliable across SQLite and future databases
- settings data must avoid leaking secrets while still being operationally useful

## Verification

- backend `pytest -q`
- frontend `npm test`
- frontend `npm run build`
- local backend and frontend smoke on `127.0.0.1:8787` and `127.0.0.1:3000`
