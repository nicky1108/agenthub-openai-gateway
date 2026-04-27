import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../api";
import { AdminShell } from "./AdminShell";

vi.mock("../../api", () => ({
  adjustAdminAccountCredits: vi.fn(async () => ({})),
  cancelAdminHermesTask: vi.fn(async () => ({})),
  createAdminAccount: vi.fn(async () => ({
    id: 2,
    name: "Demo Account",
    email: "demo@example.com",
    status: "active",
    is_admin: false,
    credit_balance: 0,
    public_account_id: null,
    public_workspace_id: null,
    notes: null,
    created_at: null,
  })),
  createAdminApiKey: vi.fn(async () => ({})),
  createAdminHermesTask: vi.fn(async () => ({})),
  createAdminProvider: vi.fn(async () => ({})),
  createAdminProviderModel: vi.fn(async () => ({})),
  deleteAdminAccount: vi.fn(async () => ({})),
  deleteAdminApiKey: vi.fn(async () => ({})),
  deleteAdminProvider: vi.fn(async () => ({})),
  deleteAdminProviderModel: vi.fn(async () => ({})),
  getAdminAccountCreditLedger: vi.fn(async () => ({
    items: [],
    total: 0,
    limit: 10,
    offset: 0,
  })),
  getAdminAccountModelAccess: vi.fn(async (_adminSecret: string, accountId: number) => ({
    account_id: accountId,
    platform_model_access_mode: "all",
    allowed_model_ids: [],
    available_models: [],
  })),
  getAdminAccountSyncSummary: vi.fn(async () => ({
    total_accounts: 1,
    mirrored_accounts: 1,
    accounts_needing_backfill: 0,
    accounts_with_pending_sync: 0,
    accounts_with_failed_sync: 0,
    accounts_fully_converged: 1,
  })),
  getAdminAccounts: vi.fn(async () => [
    {
      id: 1,
      name: "Existing Account",
      email: "existing@example.com",
      status: "active",
      is_admin: true,
      credit_balance: 0,
      public_account_id: null,
      public_workspace_id: null,
      notes: null,
      created_at: null,
    },
  ]),
  getAdminApiKeys: vi.fn(async () => []),
  getAdminDashboardSummary: vi.fn(async () => ({
    total_requests: 0,
    active_api_keys: 0,
    error_rate: 0,
    rate_limit_hits: 0,
  })),
  getAdminDashboardTimeseries: vi.fn(async () => ({
    window: "24h",
    buckets: [],
  })),
  getAdminHealth: vi.fn(async () => []),
  getAdminHermesOverview: vi.fn(async () => ({
    enabled: false,
    api_base: "http://127.0.0.1:8642/v1",
    api_key_configured: false,
    model: "hermes",
    model_id: null,
    runner_active: false,
    max_concurrent_tasks: 1,
  })),
  getAdminHermesTask: vi.fn(async () => ({})),
  getAdminHermesTaskEvents: vi.fn(async () => []),
  getAdminHermesTasks: vi.fn(async () => ({
    items: [],
    total: 0,
    limit: 20,
    offset: 0,
  })),
  getAdminProviderModels: vi.fn(async () => []),
  getAdminProviders: vi.fn(async () => []),
  getAdminSettingsOverview: vi.fn(async () => ({
    gateway_host: "127.0.0.1",
    gateway_port: 8000,
    frontend_base_url: "http://localhost:5173",
    database_scheme: "sqlite",
    email_password_enabled: true,
    github_oauth_enabled: false,
    google_oauth_enabled: false,
    admin_secret_configured: true,
  })),
  getAdminUsageOverview: vi.fn(async () => ({
    key_activity: [],
    by_provider: {},
    by_model: {},
  })),
  getAdminUsageRecords: vi.fn(async () => ({
    items: [],
    total: 0,
    limit: 25,
    offset: 0,
  })),
  patchAdminProviderModel: vi.fn(async () => ({})),
  patchAdminProviderModelPricing: vi.fn(async () => ({})),
  rediscoverAdminProviderModels: vi.fn(async () => []),
  refreshAdminProviderPricing: vi.fn(async () => ({})),
  sendAdminTestChat: vi.fn(async () => ({ choices: [{ message: { content: "" } }] })),
  streamAdminTestChat: vi.fn(async function* () {}),
  updateAdminAccount: vi.fn(async () => ({})),
  updateAdminAccountModelAccess: vi.fn(async () => ({})),
  updateAdminApiKey: vi.fn(async () => ({})),
  updateAdminProvider: vi.fn(async () => ({})),
}));

describe("AdminShell", () => {
  beforeEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("shows CRUD success feedback as a floating toast", async () => {
    render(<AdminShell adminSecret="test-secret" locale="zh" onLogout={() => {}} />);

    fireEvent.click(screen.getByRole("button", { name: "Accounts" }));
    await screen.findByRole("heading", { name: "Accounts" });

    fireEvent.click(screen.getByRole("button", { name: "新建" }));
    fireEvent.change(screen.getByLabelText("账户名称"), { target: { value: "Demo Account" } });
    fireEvent.change(screen.getByLabelText("邮箱"), { target: { value: "demo@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    const toast = screen.getByRole("status");
    expect(toast.textContent).toContain("账户已创建。");
    expect(toast.classList.contains("admin-toast")).toBe(true);
    expect(toast.classList.contains("inline-success")).toBe(false);
    expect(api.createAdminAccount).toHaveBeenCalledWith("test-secret", {
      name: "Demo Account",
      email: "demo@example.com",
      is_admin: false,
      notes: null,
    });
  });

  it("documents Hermes task API usage inside the admin console", async () => {
    render(<AdminShell adminSecret="test-secret" locale="zh" onLogout={() => {}} />);

    fireEvent.click(screen.getByRole("button", { name: "Hermes" }));

    expect(await screen.findByRole("heading", { name: "Hermes 控制台" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "接口调用文档" })).toBeTruthy();
    expect(screen.getByText(/POST \/v1\/hermes\/tasks/)).toBeTruthy();
    expect(screen.getByText(/GET \/v1\/hermes\/tasks\/\{task_id\}\/events/)).toBeTruthy();
    expect(screen.getAllByText(/Authorization: Bearer YOUR_GATEWAY_API_KEY/).length).toBeGreaterThan(0);
    expect(screen.getByText(/发起任务先扣 10 点/)).toBeTruthy();
  });
});
