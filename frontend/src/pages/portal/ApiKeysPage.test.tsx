import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { messages } from "../../i18n";
import { ApiKeysPage } from "./ApiKeysPage";

describe("ApiKeysPage", () => {
  afterEach(() => {
    cleanup();
  });

  it("forwards delete clicks to the shell", () => {
    const onDelete = vi.fn(async () => {});

    render(
      <ApiKeysPage
        apiKeys={[
          {
            id: 1,
            name: "primary",
            key_prefix: "agk_1234",
            created_at: null,
            last_used_at: null,
            per_minute: 10,
            per_hour: null,
            per_day: 1000,
            total_requests: 12,
            limited_requests: 2,
          },
        ]}
        copy={messages.zh}
        createdKey={null}
        keyName=""
        limitDay=""
        limitHour=""
        limitMinute=""
        onCreate={async () => {}}
        onDelete={onDelete}
        onUpdate={async () => {}}
        onKeyNameChange={() => {}}
        onLimitDayChange={() => {}}
        onLimitHourChange={() => {}}
        onLimitMinuteChange={() => {}}
        onDismissCreatedKey={() => {}}
      />,
    );

    expect(screen.getByText("每分钟限额: 10")).toBeTruthy();
    expect(screen.getByText("每小时限额: 不限")).toBeTruthy();
    expect(screen.getByText("每天限额: 1000")).toBeTruthy();
    expect(screen.getByText("12 total")).toBeTruthy();
    expect(screen.getByText("2 limited")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "删除" }));

    expect(onDelete).toHaveBeenCalledWith(1);
  });

  it("renders optional rate limit fields for key creation", () => {
    const onLimitMinuteChange = vi.fn();

    render(
      <ApiKeysPage
        apiKeys={[]}
        copy={messages.zh}
        createdKey={null}
        keyName="primary"
        limitDay=""
        limitHour=""
        limitMinute="60"
        onCreate={async () => {}}
        onDelete={async () => {}}
        onUpdate={async () => {}}
        onKeyNameChange={() => {}}
        onLimitDayChange={() => {}}
        onLimitHourChange={() => {}}
        onLimitMinuteChange={onLimitMinuteChange}
        onDismissCreatedKey={() => {}}
      />,
    );

    fireEvent.change(screen.getByLabelText("每分钟限额"), { target: { value: "120" } });

    expect(screen.getByLabelText("每小时限额")).toBeTruthy();
    expect(screen.getByLabelText("每天限额")).toBeTruthy();
    expect(onLimitMinuteChange).toHaveBeenCalledWith("120");
  });

  it("edits existing API key limits", () => {
    const onUpdate = vi.fn(async () => {});

    render(
      <ApiKeysPage
        apiKeys={[
          {
            id: 7,
            name: "primary",
            key_prefix: "agk_7777",
            created_at: null,
            last_used_at: null,
            per_minute: 10,
            per_hour: null,
            per_day: 1000,
            total_requests: 4,
            limited_requests: 1,
          },
        ]}
        copy={messages.zh}
        createdKey={null}
        keyName=""
        limitDay=""
        limitHour=""
        limitMinute=""
        onCreate={async () => {}}
        onDelete={async () => {}}
        onUpdate={onUpdate}
        onKeyNameChange={() => {}}
        onLimitDayChange={() => {}}
        onLimitHourChange={() => {}}
        onLimitMinuteChange={() => {}}
        onDismissCreatedKey={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "编辑 primary" }));
    fireEvent.change(screen.getByLabelText("编辑 Key 名称"), { target: { value: "production" } });
    fireEvent.change(screen.getByLabelText("编辑每分钟限额"), { target: { value: "30" } });
    fireEvent.change(screen.getByLabelText("编辑每小时限额"), { target: { value: "500" } });
    fireEvent.change(screen.getByLabelText("编辑每天限额"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "保存限额" }));

    expect(onUpdate).toHaveBeenCalledWith(7, {
      name: "production",
      per_minute: 30,
      per_hour: 500,
      per_day: null,
    });
  });
});
