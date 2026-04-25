import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { messages } from "../../i18n";
import { DashboardPage } from "./DashboardPage";

describe("DashboardPage", () => {
  it("renders account sync state when present", () => {
    render(
      <DashboardPage
        apiKeyCount={2}
        copy={messages.zh}
        dashboard={{
          credits_balance: 12.5,
          request_count_24h: 8,
          request_count_7d: 44,
          platform_requests_24h: 5,
          custom_requests_24h: 3,
          local_provider_count: 1,
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
                  name: "primary",
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
        }}
        onRetrySync={async () => {}}
        providerCount={1}
        syncRetrying={false}
      />,
    );

    expect(screen.getByText("Workspace status")).toBeTruthy();
    expect(screen.getByText("Your account is connected and ready to serve requests.")).toBeTruthy();
    expect(screen.getByText((_, element) => element?.textContent === "Updates pending 2")).toBeTruthy();
    expect(screen.getByText("A recent account change is still being applied.")).toBeTruthy();
    expect(screen.getByText("1 update needs manual review.")).toBeTruthy();
    expect(screen.getByText("1 key copy is active for managed model access.")).toBeTruthy();
  });

  it("fires retry sync action from account sync panel", () => {
    let called = 0;

    render(
      <DashboardPage
        apiKeyCount={2}
        copy={messages.zh}
        dashboard={{
          account_sync: {
            linked: true,
            local_account_id: "1",
            upstream_account_id: "8",
            upstream_workspace_id: "ws_test_account_8",
            sync_queue: {
              pending: 1,
              failed: 0,
            },
          },
        }}
        onRetrySync={async () => {
          called += 1;
        }}
        providerCount={1}
        syncRetrying={false}
      />,
    );

    const retryButtons = screen.getAllByRole("button", { name: "Refresh status" });
    fireEvent.click(retryButtons[retryButtons.length - 1]);
    expect(called).toBe(1);
  });

  it("does not crash when unified local mirror omits api key details", () => {
    render(
      <DashboardPage
        apiKeyCount={2}
        copy={messages.zh}
        dashboard={{
          account_sync: {
            linked: true,
            local_account_id: "1",
            upstream_account_id: null,
            upstream_workspace_id: null,
            local_mirror: {
              status: "unified",
            },
            sync_queue: {
              pending: 0,
              failed: 0,
            },
          },
        }}
        onRetrySync={async () => {}}
        providerCount={0}
        syncRetrying={false}
      />,
    );

    expect(screen.getByText("2 key copies are active for managed model access.")).toBeTruthy();
  });
});
