import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { messages } from "../../i18n";
import { ModelsPage } from "./ModelsPage";

describe("ModelsPage", () => {
  beforeEach(() => {
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
  });

  it("switches between non-stream and stream curl examples", async () => {
    render(
      <ModelsPage
        copy={messages.zh}
        customModels={[
          { id: "minimax-cn:MiniMax-M2.7", provider: "minimax-cn", source: "custom", enabled: true },
          { id: "minimax-cn:MiniMax-M2.5", provider: "minimax-cn", source: "custom", enabled: true },
        ]}
        platformModels={[{ id: "codex:gpt-5.4", provider: "codex", source: "platform", enabled: true }]}
        providers={[
          {
            id: 3,
            account_id: "1",
            slug: "minimax-cn",
            name: "minimax-cn",
            protocol: "openai",
            base_url: "https://api.minimaxi.com/v1",
            description: null,
            status: "active",
            last_probe_at: "2026-04-22T01:00:00+00:00",
            last_probe_ok: true,
            last_probe_model: "MiniMax-M2.7",
            last_probe_detail: null,
            last_detected_models: ["MiniMax-M2.7", "MiniMax-M2.5"],
          },
        ]}
      />,
    );

    expect(screen.getByText(/"stream": false/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "流式示例" }));

    expect(screen.getByText(/"stream": true/)).toBeTruthy();
    expect(screen.getByText(/\[DONE\]/)).toBeTruthy();
    expect(screen.getByText(/已验证/)).toBeTruthy();
    expect(screen.queryByText(/minimax-cn:MiniMax-M2.5 · 已探测/)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "查看其他模型" }));

    expect(screen.getByText(/minimax-cn:MiniMax-M2.5 · 已探测/)).toBeTruthy();
  });
});
