import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as api from "../../api";
import { messages } from "../../i18n";
import { DocsPage } from "./DocsPage";

vi.mock("../../api", async () => {
  const actual = await vi.importActual<typeof import("../../api")>("../../api");
  return {
    ...actual,
    getPortalCatalog: vi.fn(async () => ({
      platform_providers: [],
      platform_models: [],
      custom_models: [],
    })),
  };
});

describe("DocsPage", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders unified, managed, custom, and streaming sections", () => {
    render(
      <DocsPage
        authUser={null}
        copy={messages.zh}
        locale="zh"
        onNavigate={() => {}}
        onToggleLocale={() => {}}
      />,
    );

    expect(screen.getByRole("heading", { name: "统一模型示例" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "平台模型" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "自定义 Provider" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "流式调用" })).toBeTruthy();
  });

  it("uses live catalog model ids when an authenticated user is present", async () => {
    vi.mocked(api.getPortalCatalog).mockResolvedValue({
      platform_providers: [],
      platform_models: [{ id: "codex:gpt-5.4-mini", provider: "codex", source: "platform", enabled: true }],
      custom_models: [{ id: "minimax-cn:MiniMax-M2.5", provider: "minimax-cn", source: "custom", enabled: true }],
    });

    render(
      <DocsPage
        authUser={{ account_id: "acct_123", workspace_id: "ws_123", name: "Nicky", email: "nicky@example.com" }}
        copy={messages.zh}
        locale="zh"
        onNavigate={() => {}}
        onToggleLocale={() => {}}
      />,
    );

    expect((await screen.findAllByText(/codex:gpt-5\.4-mini/)).length).toBeGreaterThan(0);
    expect((await screen.findAllByText(/minimax-cn:MiniMax-M2\.5/)).length).toBeGreaterThan(0);
  });

  it("does not expose Hermes task models in public user docs", async () => {
    vi.mocked(api.getPortalCatalog).mockResolvedValue({
      platform_providers: [],
      platform_models: [
        { id: "codex:gpt-5.4-mini", provider: "codex", source: "platform", enabled: true },
        { id: "hermes:hermes-agent", provider: "hermes", source: "platform", enabled: true },
      ],
      custom_models: [],
    });

    render(
      <DocsPage
        authUser={{ account_id: "acct_admin", workspace_id: "ws_admin", name: "Admin", email: "admin@example.com", is_admin: true }}
        copy={messages.zh}
        locale="zh"
        onNavigate={() => {}}
        onToggleLocale={() => {}}
      />,
    );

    expect((await screen.findAllByText(/codex:gpt-5\.4-mini/)).length).toBeGreaterThan(0);
    expect(screen.queryByText(/hermes:hermes-agent/)).toBeNull();
    expect(screen.queryByText(/\/v1\/hermes\/tasks/)).toBeNull();
  });

  it("updates examples when the selected live models change", async () => {
    vi.mocked(api.getPortalCatalog).mockResolvedValue({
      platform_providers: [],
      platform_models: [
        { id: "codex:gpt-5.4-mini", provider: "codex", source: "platform", enabled: true },
        { id: "gemini:gemini-2.5-pro", provider: "gemini", source: "platform", enabled: true },
      ],
      custom_models: [
        { id: "minimax-cn:MiniMax-M2.5", provider: "minimax-cn", source: "custom", enabled: true },
        { id: "minimax-cn:MiniMax-M2.7", provider: "minimax-cn", source: "custom", enabled: true },
      ],
    });

    render(
      <DocsPage
        authUser={{ account_id: "acct_123", workspace_id: "ws_123", name: "Nicky", email: "nicky@example.com" }}
        copy={messages.zh}
        locale="zh"
        onNavigate={() => {}}
        onToggleLocale={() => {}}
      />,
    );

    fireEvent.change(await screen.findByLabelText("示例模型"), {
      target: { value: "minimax-cn:MiniMax-M2.7" },
    });
    fireEvent.click(screen.getByRole("button", { name: "流式" }));

    expect((await screen.findAllByText(/minimax-cn:MiniMax-M2\.7/)).length).toBeGreaterThan(0);
    expect(screen.getByText(/"stream": true/)).toBeTruthy();
    expect(screen.getAllByText(/data: \[DONE\]/).length).toBeGreaterThan(0);
  });

  it("copies the currently selected docs example", async () => {
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
    vi.mocked(api.getPortalCatalog).mockResolvedValue({
      platform_providers: [],
      platform_models: [{ id: "codex:gpt-5.4-mini", provider: "codex", source: "platform", enabled: true }],
      custom_models: [{ id: "minimax-cn:MiniMax-M2.5", provider: "minimax-cn", source: "custom", enabled: true }],
    });

    render(
      <DocsPage
        authUser={{ account_id: "acct_123", workspace_id: "ws_123", name: "Nicky", email: "nicky@example.com" }}
        copy={messages.zh}
        locale="zh"
        onNavigate={() => {}}
        onToggleLocale={() => {}}
      />,
    );

    await screen.findAllByText(/codex:gpt-5\.4-mini/);
    fireEvent.change(screen.getByLabelText("示例模型"), { target: { value: "codex:gpt-5.4-mini" } });
    fireEvent.click(screen.getByRole("button", { name: "复制示例" }));

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(expect.stringContaining('"model": "codex:gpt-5.4-mini"'));
  });

  it("documents custom provider protocols and common errors", () => {
    render(
      <DocsPage
        authUser={null}
        copy={messages.zh}
        locale="zh"
        onNavigate={() => {}}
        onToggleLocale={() => {}}
      />,
    );

    expect(screen.getByRole("heading", { name: "OpenAI-compatible Provider" })).toBeTruthy();
    expect(screen.getByText(/Base URL 必须指向包含 \/v1 的 OpenAI 兼容根路径/)).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Anthropic Messages Provider" })).toBeTruthy();
    expect(screen.getByText(/AgentHub 会把 OpenAI chat\.completions 请求转换为 Anthropic Messages/)).toBeTruthy();
    expect(screen.getByRole("heading", { name: "常见错误" })).toBeTruthy();
    expect(screen.getByText(/429/)).toBeTruthy();
  });

  it("documents a platform-model tools call for web_fetch", () => {
    render(
      <DocsPage
        authUser={null}
        copy={messages.zh}
        locale="zh"
        onNavigate={() => {}}
        onToggleLocale={() => {}}
      />,
    );

    expect(screen.getByRole("heading", { name: "Tools 调用：web_fetch" })).toBeTruthy();
    expect(screen.getAllByText(/"model": "codex:gpt-5\.4"/).length).toBeGreaterThan(0);
    expect(screen.getByText(/"name": "web_fetch"/)).toBeTruthy();
    expect(screen.getByText(/"tool_choice"/)).toBeTruthy();
    expect(screen.getByText(/"url":/)).toBeTruthy();
  });
});
