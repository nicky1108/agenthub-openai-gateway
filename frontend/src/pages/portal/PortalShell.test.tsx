import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../api";
import { messages } from "../../i18n";
import { PortalShell } from "./PortalShell";

vi.mock("../../api", () => ({
  createUserApiKey: vi.fn(async () => ({ api_key: "agk_demo_secret", id: 1 })),
  deleteUserApiKey: vi.fn(async () => ({ status: "revoked" })),
  deleteUserProvider: vi.fn(async () => ({ status: "deleted" })),
  getPortalCatalog: vi.fn(async () => ({
    platform_providers: [],
    platform_models: [],
    custom_models: [],
  })),
  getPortalDashboard: vi.fn(async () => ({
    credits_balance: 12.5,
    request_count_24h: 8,
    request_count_7d: 44,
    platform_requests_24h: 5,
    custom_requests_24h: 3,
    local_provider_count: 0,
  })),
  getUserApiKeys: vi.fn(async () => []),
  getUserProviders: vi.fn(async () => []),
  logoutSession: vi.fn(async () => ({ status: "ok" })),
  addUserProvider: vi.fn(async () => ({})),
  probeSavedUserProvider: vi.fn(async () => ({})),
  probeUserProvider: vi.fn(async () => ({
    models_endpoint_supported: false,
    detected_models: [],
    completion_probe_ok: false,
    completion_probe_model: null,
    detail: null,
  })),
  retryPortalSync: vi.fn(async () => ({ status: "retried", sync_queue: { pending: 0, failed: 0 } })),
  updateUserApiKey: vi.fn(async () => ({
    id: 1,
    name: "primary",
    key_prefix: "903f369d",
    created_at: null,
    last_used_at: null,
    per_minute: null,
    per_hour: null,
    per_day: null,
    total_requests: 0,
    limited_requests: 0,
  })),
  updateUserProvider: vi.fn(async () => ({})),
}));

describe("PortalShell", () => {
  beforeEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
    vi.mocked(api.getUserApiKeys).mockResolvedValue([]);
    vi.mocked(api.getUserProviders).mockResolvedValue([]);
    vi.mocked(api.getPortalCatalog).mockResolvedValue({
      platform_providers: [],
      platform_models: [],
      custom_models: [],
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("auto-dismisses success notices after actions complete", async () => {
    render(
      <PortalShell
        copy={messages.zh}
        locale="zh"
        onLogout={() => {}}
        onNavigate={() => {}}
        onToggleLocale={() => {}}
        pathname="/portal/api-keys"
        user={{ account_id: "acct_123", workspace_id: "ws_123", name: "Nicky", email: "nicky@example.com" }}
      />,
    );

    await screen.findByRole("heading", { name: "API Key 管理" });

    vi.useFakeTimers();
    fireEvent.change(screen.getByPlaceholderText("Key 名称"), { target: { value: "demo" } });
    fireEvent.change(screen.getByLabelText("每分钟限额"), { target: { value: "60" } });
    fireEvent.change(screen.getByLabelText("每小时限额"), { target: { value: "1000" } });
    fireEvent.change(screen.getByLabelText("每天限额"), { target: { value: "5000" } });
    fireEvent.click(screen.getByRole("button", { name: "创建" }));

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(screen.getByText("API key 已创建。")).toBeTruthy();
    expect(api.createUserApiKey).toHaveBeenCalledWith({
      name: "demo",
      per_minute: 60,
      per_hour: 1000,
      per_day: 5000,
    });

    await act(async () => {
      vi.advanceTimersByTime(2600);
    });

    expect(screen.queryByText("API key 已创建。")).toBeNull();

    vi.useRealTimers();
  });

  it("shows an in-app confirmation dialog before deleting a provider", async () => {
    vi.mocked(api.getUserProviders).mockResolvedValue([
      {
        id: 3,
        account_id: "acct_123",
        slug: "minimax-cn",
        name: "minimax-cn",
        protocol: "openai",
        base_url: "https://api.minimaxi.com/v1",
        description: null,
        status: "active",
        last_probe_at: null,
        last_probe_ok: null,
        last_probe_model: null,
        last_probe_detail: null,
        last_detected_models: [],
      },
    ]);
    vi.mocked(api.getPortalCatalog).mockResolvedValue({
      platform_providers: [],
      platform_models: [],
      custom_models: [{ id: "minimax-cn:MiniMax-M2.7", provider: "minimax-cn", source: "custom", enabled: true }],
    });

    render(
      <PortalShell
        copy={messages.zh}
        locale="zh"
        onLogout={() => {}}
        onNavigate={() => {}}
        onToggleLocale={() => {}}
        pathname="/portal/providers"
        user={{ account_id: "acct_123", workspace_id: "ws_123", name: "Nicky", email: "nicky@example.com" }}
      />,
    );

    await screen.findByRole("heading", { name: "自定义 Provider" });
    fireEvent.click(screen.getByRole("button", { name: "删除" }));

    expect(screen.getByRole("dialog", { name: "确认删除 Provider" })).toBeTruthy();
    expect(screen.getByText(/这个动作会立即生效/)).toBeTruthy();
  });

  it("offers a retry path when portal data loading fails", async () => {
    vi.mocked(api.getPortalDashboard)
      .mockRejectedValueOnce(new Error("request failed"))
      .mockResolvedValueOnce({
        credits_balance: 12.5,
        request_count_24h: 8,
        request_count_7d: 44,
        platform_requests_24h: 5,
        custom_requests_24h: 3,
        local_provider_count: 0,
      });

    render(
      <PortalShell
        copy={messages.zh}
        locale="zh"
        onLogout={() => {}}
        onNavigate={() => {}}
        onToggleLocale={() => {}}
        pathname="/portal"
        user={{ account_id: "acct_123", workspace_id: "ws_123", name: "Nicky", email: "nicky@example.com" }}
      />,
    );

    expect(await screen.findByText("request failed")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "重试加载" }));

    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeTruthy();
  });

  it("retries account sync from dashboard", async () => {
    vi.mocked(api.getPortalDashboard).mockResolvedValue({
      credits_balance: 12.5,
      request_count_24h: 8,
      request_count_7d: 44,
      platform_requests_24h: 5,
      custom_requests_24h: 3,
      local_provider_count: 0,
      account_sync: {
        linked: true,
        local_account_id: "1",
        upstream_account_id: "8",
        upstream_workspace_id: "ws_test_account_8",
        local_mirror: {
          public_account_id: "1",
          workspace_id: "ws_public_account_1",
          local_account_id: "17",
          email: "portal@example.com",
          status: "active",
          api_keys: [
            {
              public_api_key_id: "5",
              local_api_key_id: "15",
              name: "tunnel-primary",
              key_prefix: "903f369d",
              status: "active",
            },
          ],
        },
        sync_queue: {
          pending: 2,
          failed: 1,
        },
      },
    });

    render(
      <PortalShell
        copy={messages.zh}
        locale="zh"
        onLogout={() => {}}
        onNavigate={() => {}}
        onToggleLocale={() => {}}
        pathname="/portal"
        user={{ account_id: "acct_123", workspace_id: "ws_123", name: "Nicky", email: "nicky@example.com" }}
      />,
    );

    expect(await screen.findByRole("button", { name: "Refresh status" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Refresh status" }));

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(api.retryPortalSync).toHaveBeenCalledTimes(1);
    expect(screen.getByText("状态已刷新。")).toBeTruthy();
  });

  it("updates and reprobes a saved provider from the portal", async () => {
    vi.mocked(api.getUserProviders).mockResolvedValue([
      {
        id: 3,
        account_id: "acct_123",
        slug: "claude",
        name: "claude",
        protocol: "anthropic",
        base_url: "https://api.yourouter.ai/anthropic",
        description: null,
        status: "active",
        last_probe_at: null,
        last_probe_ok: null,
        last_probe_model: null,
        last_probe_detail: null,
        last_detected_models: [],
      },
    ]);

    render(
      <PortalShell
        copy={messages.zh}
        locale="zh"
        onLogout={() => {}}
        onNavigate={() => {}}
        onToggleLocale={() => {}}
        pathname="/portal/providers"
        user={{ account_id: "acct_123", workspace_id: "ws_123", name: "Nicky", email: "nicky@example.com" }}
      />,
    );

    await screen.findByRole("heading", { name: "自定义 Provider" });
    fireEvent.click(screen.getByRole("button", { name: "编辑 claude" }));
    fireEvent.change(screen.getByLabelText("编辑 Provider API Key"), { target: { value: "new-secret" } });
    fireEvent.click(screen.getByRole("button", { name: "保存 Provider" }));

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(api.updateUserProvider).toHaveBeenCalledWith(3, {
      name: "claude",
      protocol: "anthropic",
      base_url: "https://api.yourouter.ai/anthropic",
      api_key: "new-secret",
      description: undefined,
    });
    expect(api.probeSavedUserProvider).toHaveBeenCalledWith(3);
  });
});
