import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { messages } from "../../i18n";
import { summarizeProviderDetail } from "./providerDiagnostics";
import { ProvidersPage } from "./ProvidersPage";
import { providerPresets } from "./providerPresets";

describe("ProvidersPage", () => {
  const writeText = vi.fn().mockResolvedValue(undefined);

  beforeEach(() => {
    writeText.mockClear();
    Object.assign(navigator, {
      clipboard: {
        writeText,
      },
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("copies per-model ids, non-stream curls, and stream curls for a saved provider", async () => {
    render(
      <ProvidersPage
        copy={messages.zh}
        customModels={["minimax-cn:MiniMax-M2.7", "minimax-cn:MiniMax-M2.5"]}
        name="minimax-cn"
        platformProviders={[]}
        probeResult={null}
        probeRunning={false}
        presetId="minimax"
        presets={providerPresets}
        protocol="openai"
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
            last_detected_models: [],
          },
        ]}
        previewModelId="minimax-cn:default"
        reprobeProviderId={null}
        secret=""
        url="https://api.minimaxi.com/v1"
        onAdd={async () => {}}
        onDelete={async () => {}}
        onNameChange={() => {}}
        onProtocolChange={() => {}}
        onPresetChange={() => {}}
        onProbe={async () => {}}
        onReprobe={async () => {}}
        onSecretChange={() => {}}
        onUpdate={async () => {}}
        onUrlChange={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "复制 ID minimax-cn:MiniMax-M2.7" }));
    expect(writeText).toHaveBeenCalledWith("minimax-cn:MiniMax-M2.7");
    expect(screen.getByText(/已验证/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "查看其他模型 (1)" }));
    fireEvent.click(screen.getByRole("button", { name: "复制 cURL minimax-cn:MiniMax-M2.5" }));
    expect(writeText).toHaveBeenLastCalledWith(expect.stringContaining('"model": "minimax-cn:MiniMax-M2.5"'));

    fireEvent.click(screen.getByRole("button", { name: "复制流式 cURL minimax-cn:MiniMax-M2.5" }));
    expect(writeText).toHaveBeenLastCalledWith(expect.stringContaining('"stream": true'));
  });

  it("forwards provider delete clicks to the shell", () => {
    const onDelete = vi.fn(async () => {});

    render(
      <ProvidersPage
        copy={messages.zh}
        customModels={["minimax-cn:MiniMax-M2.7"]}
        name="minimax-cn"
        platformProviders={[]}
        probeResult={null}
        probeRunning={false}
        presetId="minimax"
        presets={providerPresets}
        protocol="openai"
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
            last_probe_at: null,
            last_probe_ok: null,
            last_probe_model: null,
            last_probe_detail: null,
            last_detected_models: [],
          },
        ]}
        previewModelId="minimax-cn:default"
        reprobeProviderId={null}
        secret=""
        url="https://api.minimaxi.com/v1"
        onAdd={async () => {}}
        onDelete={onDelete}
        onNameChange={() => {}}
        onProtocolChange={() => {}}
        onPresetChange={() => {}}
        onProbe={async () => {}}
        onReprobe={async () => {}}
        onSecretChange={() => {}}
        onUpdate={async () => {}}
        onUrlChange={() => {}}
      />,
    );

    const deleteButtons = screen.getAllByRole("button", { name: "删除" });
    fireEvent.click(deleteButtons[deleteButtons.length - 1]);

    expect(onDelete).toHaveBeenCalledWith(3);
  });

  it("surfaces actionable diagnostics for probe and saved-provider failures", () => {
    expect(summarizeProviderDetail("probe failed with status 404")?.summary).toContain("/v1");
    expect(summarizeProviderDetail("probe failed with status 401")?.summary).toContain("API key");

    render(
      <ProvidersPage
        copy={messages.zh}
        customModels={["minimax-cn:MiniMax-M2.7"]}
        name="minimax-cn"
        platformProviders={[]}
        probeResult={{
          models_endpoint_supported: false,
          detected_models: [],
          completion_probe_ok: false,
          completion_probe_model: null,
          detail: "probe failed with status 404",
        }}
        probeRunning={false}
        presetId="minimax"
        presets={providerPresets}
        protocol="openai"
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
            last_probe_ok: false,
            last_probe_model: null,
            last_probe_detail: "local gateway unavailable",
            last_detected_models: [],
          },
        ]}
        previewModelId="minimax-cn:default"
        reprobeProviderId={null}
        secret=""
        url="https://api.minimaxi.com/v1"
        onAdd={async () => {}}
        onDelete={async () => {}}
        onNameChange={() => {}}
        onProtocolChange={() => {}}
        onPresetChange={() => {}}
        onProbe={async () => {}}
        onReprobe={async () => {}}
        onSecretChange={() => {}}
        onUpdate={async () => {}}
        onUrlChange={() => {}}
      />,
    );

    expect(screen.getByText(/优先检查 Base URL/)).toBeTruthy();
    expect(screen.getByText(/平台模型服务暂时不可用/)).toBeTruthy();
  });

  it("shows verified provider models first and folds unverified models", () => {
    render(
      <ProvidersPage
        copy={messages.zh}
        customModels={["router:claude-good", "router:claude-detected"]}
        name="router"
        platformProviders={[]}
        probeResult={null}
        probeRunning={false}
        presetId="anthropic"
        presets={providerPresets}
        protocol="anthropic"
        providers={[
          {
            id: 8,
            account_id: "1",
            slug: "router",
            name: "router",
            protocol: "anthropic",
            base_url: "https://api.yourouter.ai/anthropic",
            description: null,
            status: "active",
            last_probe_at: "2026-04-22T01:00:00+00:00",
            last_probe_ok: true,
            last_probe_model: "claude-good",
            last_probe_detail: null,
            last_detected_models: ["claude-good", "claude-detected"],
          },
        ]}
        previewModelId="router:default"
        reprobeProviderId={null}
        secret=""
        url="https://api.yourouter.ai/anthropic"
        onAdd={async () => {}}
        onDelete={async () => {}}
        onNameChange={() => {}}
        onProtocolChange={() => {}}
        onPresetChange={() => {}}
        onProbe={async () => {}}
        onReprobe={async () => {}}
        onSecretChange={() => {}}
        onUpdate={async () => {}}
        onUrlChange={() => {}}
      />,
    );

    expect(screen.getByRole("button", { name: "复制 ID router:claude-good" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "复制 ID router:claude-detected" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "查看其他模型 (1)" }));

    expect(screen.getByRole("button", { name: "复制 ID router:claude-detected" })).toBeTruthy();
  });

  it("edits a saved provider without sending a blank replacement secret", async () => {
    const onUpdate = vi.fn(async () => {});

    render(
      <ProvidersPage
        copy={messages.zh}
        customModels={["router:claude-good"]}
        name="router"
        platformProviders={[]}
        probeResult={null}
        probeRunning={false}
        presetId="anthropic"
        presets={providerPresets}
        protocol="anthropic"
        providers={[
          {
            id: 8,
            account_id: "1",
            slug: "router",
            name: "router",
            protocol: "anthropic",
            base_url: "https://api.yourouter.ai/anthropic",
            description: "old",
            status: "active",
            last_probe_at: null,
            last_probe_ok: null,
            last_probe_model: null,
            last_probe_detail: null,
            last_detected_models: [],
          },
        ]}
        previewModelId="router:default"
        reprobeProviderId={null}
        secret=""
        url="https://api.yourouter.ai/anthropic"
        onAdd={async () => {}}
        onDelete={async () => {}}
        onNameChange={() => {}}
        onProtocolChange={() => {}}
        onPresetChange={() => {}}
        onProbe={async () => {}}
        onReprobe={async () => {}}
        onSecretChange={() => {}}
        onUpdate={onUpdate}
        onUrlChange={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "编辑 router" }));
    fireEvent.change(screen.getByLabelText("编辑 Provider 名称"), { target: { value: "Claude Router" } });
    fireEvent.change(screen.getByLabelText("编辑 Provider Base URL"), {
      target: { value: "https://api.anthropic.com/v1" },
    });
    fireEvent.change(screen.getByLabelText("编辑 Provider 描述"), { target: { value: "rotated" } });
    fireEvent.click(screen.getByRole("button", { name: "保存 Provider" }));

    expect(onUpdate).toHaveBeenCalledWith(8, {
      name: "Claude Router",
      protocol: "anthropic",
      base_url: "https://api.anthropic.com/v1",
      description: "rotated",
    });
  });
});
