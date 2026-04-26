import { useEffect, useState, type FormEvent } from "react";

import type {
  AdminAccountSyncSummary,
  AdminAccountRecord,
  AdminModelPricingRecord,
  AdminCreditLedgerEntry,
  AdminApiKeyRecord,
  AdminDashboardSummary,
  AdminDashboardTimeseries,
  AdminProviderHealthRecord,
  AdminProviderModelRecord,
  AdminProviderRecord,
  AdminSettingsOverview,
  AdminUsageOverview,
} from "../../api";
import {
  adjustAdminAccountCredits,
  getAdminAccountSyncSummary,
  createAdminAccount,
  createAdminApiKey,
  createAdminProvider,
  createAdminProviderModel,
  getAdminAccounts,
  getAdminAccountCreditLedger,
  getAdminApiKeys,
  getAdminDashboardSummary,
  getAdminDashboardTimeseries,
  getAdminHealth,
  getAdminProviderModels,
  getAdminProviders,
  getAdminSettingsOverview,
  getAdminUsageOverview,
  patchAdminProviderModelPricing,
  patchAdminProviderModel,
  rediscoverAdminProviderModels,
  refreshAdminProviderPricing,
  revokeAdminApiKey,
  sendAdminTestChat,
  streamAdminTestChat,
  updateAdminAccount,
} from "../../api";
import type { Locale } from "../../i18n";

type AdminShellProps = {
  adminSecret: string;
  locale: Locale;
  onLogout: () => void;
};

type AdminView = "overview" | "providers" | "models" | "accounts" | "api-keys" | "usage" | "permissions" | "settings";

function buildTrafficPath(series: AdminDashboardTimeseries | null): { stroke: string; fill: string } {
  const buckets = series?.buckets ?? [];
  if (buckets.length === 0) {
    return { stroke: "M0 160 L600 160", fill: "M0 160 L600 160 L600 180 L0 180 Z" };
  }
  const maxValue = Math.max(...buckets.map((bucket) => bucket.total_requests), 1);
  const points = buckets.map((bucket, index) => {
    const x = buckets.length === 1 ? 0 : (index / (buckets.length - 1)) * 600;
    const y = 160 - (bucket.total_requests / maxValue) * 120;
    return `${x.toFixed(1)} ${y.toFixed(1)}`;
  });
  const stroke = `M${points[0]} ${points.slice(1).map((point) => `L${point}`).join(" ")}`;
  return { stroke, fill: `${stroke} L600 180 L0 180 Z` };
}

export function AdminShell({ adminSecret, locale, onLogout }: AdminShellProps) {
  const isZh = locale === "zh";
  const [view, setView] = useState<AdminView>("overview");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [summary, setSummary] = useState<AdminDashboardSummary | null>(null);
  const [timeseries, setTimeseries] = useState<AdminDashboardTimeseries | null>(null);
  const [dashboardWindow, setDashboardWindow] = useState<"24h" | "7d">("24h");
  const [accountSyncSummary, setAccountSyncSummary] = useState<AdminAccountSyncSummary | null>(null);
  const [settings, setSettings] = useState<AdminSettingsOverview | null>(null);
  const [providers, setProviders] = useState<AdminProviderRecord[]>([]);
  const [health, setHealth] = useState<AdminProviderHealthRecord[]>([]);
  const [accounts, setAccounts] = useState<AdminAccountRecord[]>([]);
  const [creditLedger, setCreditLedger] = useState<Record<number, AdminCreditLedgerEntry[]>>({});
  const [apiKeys, setApiKeys] = useState<AdminApiKeyRecord[]>([]);
  const [usage, setUsage] = useState<AdminUsageOverview | null>(null);
  const [selectedProviderName, setSelectedProviderName] = useState("");
  const [providerModels, setProviderModels] = useState<Record<string, AdminProviderModelRecord[]>>({});
  const [selectedModelNativeModel, setSelectedModelNativeModel] = useState("");

  const [accountName, setAccountName] = useState("");
  const [accountEmail, setAccountEmail] = useState("");
  const [accountIsAdmin, setAccountIsAdmin] = useState(false);
  const [accountNotes, setAccountNotes] = useState("");
  const [creditAdjustment, setCreditAdjustment] = useState("");
  const [creditAdjustmentReason, setCreditAdjustmentReason] = useState("");
  const [selectedAccountId, setSelectedAccountId] = useState("");
  const [apiKeyName, setApiKeyName] = useState("");
  const [apiKeyMinute, setApiKeyMinute] = useState("");
  const [apiKeyHour, setApiKeyHour] = useState("");
  const [apiKeyDay, setApiKeyDay] = useState("");
  const [createdApiKey, setCreatedApiKey] = useState<string | null>(null);

  const [providerName, setProviderName] = useState("");
  const [providerRoutePolicy, setProviderRoutePolicy] = useState("http-first");
  const [providerExposedModel, setProviderExposedModel] = useState("default");
  const [providerHttpEnabled, setProviderHttpEnabled] = useState(true);
  const [providerCliEnabled, setProviderCliEnabled] = useState(false);
  const [providerChatCapable, setProviderChatCapable] = useState(true);
  const [providerStreamCapable, setProviderStreamCapable] = useState(true);
  const [providerHttpBaseUrl, setProviderHttpBaseUrl] = useState("");
  const [providerCliCommand, setProviderCliCommand] = useState("");

  const [manualNativeModel, setManualNativeModel] = useState("");
  const [manualExposedModelId, setManualExposedModelId] = useState("");
  const [pricingInput, setPricingInput] = useState("");
  const [pricingCachedInput, setPricingCachedInput] = useState("");
  const [pricingOutput, setPricingOutput] = useState("");
  const [pricingNotes, setPricingNotes] = useState("");
  const [testMessage, setTestMessage] = useState("");
  const [testChatStatus, setTestChatStatus] = useState<"idle" | "loading" | "error">("idle");
  const [testChatError, setTestChatError] = useState<string | null>(null);
  const [testChatMessages, setTestChatMessages] = useState<Array<{ role: "user" | "assistant"; content: string }>>([]);
  const [testStreamAbortController, setTestStreamAbortController] = useState<AbortController | null>(null);

  const copy = isZh
    ? {
        title: "Admin Console",
        nav: { overview: "概览", providers: "Providers", models: "Models", accounts: "Accounts", apiKeys: "API Keys", usage: "Usage", permissions: "Permissions", settings: "Settings" },
        logout: "退出管理台",
        loading: "加载中...",
        overview: {
          totalRequests: "总请求数",
          activeKeys: "活跃密钥",
          errorRate: "错误率",
          rateLimitHits: "限流命中",
          traffic: "流量趋势",
          accountSync: "账户同步",
          settings: "基础设置",
          gatewayHost: "网关地址",
          frontendBaseUrl: "前端地址",
          databaseScheme: "数据库",
          authMode: "登录方式",
          requestsInWindow: (count: number) => `${count} 次请求`,
          errorCount: (count: number) => `${count} 个错误`,
          limitedCount: (count: number) => `${count} 次限流`,
          totalAccounts: "账户总数",
          mirroredAccounts: "已镜像账户",
          pendingAccounts: "待补齐账户",
          failedAccounts: "失败账户",
        },
        providers: {
          title: "Provider Registry",
          createTitle: "注册 Provider",
          createLead: "配置传输策略、能力开关和上游地址。",
          providerName: "Provider 名称",
          exposedModel: "默认对外模型",
          routePolicy: "路由策略",
          httpEnabled: "启用 HTTP",
          cliEnabled: "启用 CLI",
          httpBaseUrl: "HTTP Base URL",
          cliCommand: "CLI 命令",
          chatCapable: "支持 Chat",
          streamCapable: "支持 Stream",
          addProvider: "添加 Provider",
          healthTitle: "Provider 状态",
          openModels: "查看模型",
          healthy: "健康",
          pending: "待检查",
        },
        models: {
          title: "Models Workbench",
          noProvider: "先在左侧 Provider 列表里选择一个 Provider。",
          refresh: "重新发现模型",
          refreshPricing: "刷新价格快照",
          nativeModel: "原始模型 ID",
          exposedAs: "对外模型 ID",
          source: "来源",
          state: "状态",
          action: "操作",
          disable: "禁用",
          enable: "启用",
          rename: "保存映射",
          manualTitle: "手动添加模型",
          addModel: "添加模型",
          select: "选中",
          pricingWorkspace: "价格工作台",
          pricingSummary: "价格摘要",
          inputPrice: "输入价格",
          cachedInputPrice: "缓存输入价格",
          outputPrice: "输出价格",
          pricingNotes: "备注",
          savePricing: "保存价格覆盖",
          testWorkspace: "模型测试",
          sendTest: "发送测试",
          streamTest: "流式测试",
          cancelStream: "停止流式",
          noTranscript: "还没有测试消息。",
        },
        accounts: {
          title: "Accounts",
          accountName: "账户名称",
          accountEmail: "邮箱",
          accountNotes: "备注",
          adminRole: "管理员权限",
          addAccount: "创建账户",
          columnName: "名称",
          columnEmail: "邮箱",
          columnAdmin: "管理员",
          columnStatus: "状态",
          columnMirror: "同步镜像",
          balance: "信用点余额",
          adjustCredits: "调整信用点",
          adjustmentAmount: "调整额度",
          adjustmentReason: "调整原因",
          applyAdjustment: "应用调整",
          ledger: "最近流水",
          ledgerEmpty: "还没有信用点流水。",
          grantAdmin: "设为管理员",
          revokeAdmin: "移除管理员",
          activate: "启用",
          suspend: "暂停",
          balanceAfter: (amount: string) => `调整后余额 ${amount}`,
        },
        apiKeys: {
          title: "API Keys",
          account: "账户",
          keyName: "密钥名称",
          perMinute: "每分钟限额",
          perHour: "每小时限额",
          perDay: "每天限额",
          createKey: "创建 API Key",
          columnName: "名称",
          columnAccountId: "账户 ID",
          columnPrefix: "前缀",
          columnStatus: "状态",
          revoke: "撤销",
          createdKey: "新建明文 Key",
        },
        usage: {
          title: "Usage",
          keyActivity: "Key 活动",
          providers: "按 Provider",
          models: "按模型",
          requestsLimited: (requests: number, limited: number) => `${requests} 请求 · ${limited} 限流`,
          lastUsed: (value: string | null) => value ?? "暂无使用",
        },
        permissions: {
          title: "权限管理",
          lead: "统一控制哪些账户可以进入 Admin，以及账户是否可继续使用 API。",
          admins: "管理员",
          members: "普通账户",
        },
        settings: {
          title: "Settings",
          adminSecretConfigured: "管理员访问已配置",
          authProviders: "认证配置",
        },
      }
    : {
        title: "Admin Console",
        nav: { overview: "Overview", providers: "Providers", models: "Models", accounts: "Accounts", apiKeys: "API Keys", usage: "Usage", permissions: "Permissions", settings: "Settings" },
        logout: "Sign out",
        loading: "Loading...",
        overview: {
          totalRequests: "Total requests",
          activeKeys: "Active keys",
          errorRate: "Error rate",
          rateLimitHits: "Rate limit hits",
          traffic: "Traffic",
          accountSync: "Account sync",
          settings: "Settings",
          gatewayHost: "Gateway host",
          frontendBaseUrl: "Frontend URL",
          databaseScheme: "Database",
          authMode: "Auth mode",
          requestsInWindow: (count: number) => `${count} requests`,
          errorCount: (count: number) => `${count} errors`,
          limitedCount: (count: number) => `${count} limited`,
          totalAccounts: "Total accounts",
          mirroredAccounts: "Mirrored accounts",
          pendingAccounts: "Accounts needing backfill",
          failedAccounts: "Failed accounts",
        },
        providers: {
          title: "Provider Registry",
          createTitle: "Register provider",
          createLead: "Configure transport policy, capabilities, and upstream endpoints.",
          providerName: "Provider name",
          exposedModel: "Default exposed model",
          routePolicy: "Route policy",
          httpEnabled: "HTTP enabled",
          cliEnabled: "CLI enabled",
          httpBaseUrl: "HTTP base URL",
          cliCommand: "CLI command",
          chatCapable: "Chat capable",
          streamCapable: "Stream capable",
          addProvider: "Add provider",
          healthTitle: "Provider status",
          openModels: "Open models",
          healthy: "Healthy",
          pending: "Needs review",
        },
        models: {
          title: "Models Workbench",
          noProvider: "Select a provider from the list first.",
          refresh: "Rediscover models",
          refreshPricing: "Refresh pricing",
          nativeModel: "Native model ID",
          exposedAs: "Exposed model ID",
          source: "Source",
          state: "State",
          action: "Action",
          disable: "Disable",
          enable: "Enable",
          rename: "Save mapping",
          manualTitle: "Add manual model",
          addModel: "Add model",
          select: "Select",
          pricingWorkspace: "Pricing workspace",
          pricingSummary: "Pricing summary",
          inputPrice: "Input price",
          cachedInputPrice: "Cached input price",
          outputPrice: "Output price",
          pricingNotes: "Notes",
          savePricing: "Save pricing override",
          testWorkspace: "Model test",
          sendTest: "Send test",
          streamTest: "Stream test",
          cancelStream: "Cancel stream",
          noTranscript: "No test messages yet.",
        },
        accounts: {
          title: "Accounts",
          accountName: "Account name",
          accountEmail: "Email",
          accountNotes: "Notes",
          adminRole: "Admin role",
          addAccount: "Create account",
          columnName: "Name",
          columnEmail: "Email",
          columnAdmin: "Admin",
          columnStatus: "Status",
          columnMirror: "Mirror",
          balance: "Credit balance",
          adjustCredits: "Adjust credits",
          adjustmentAmount: "Adjustment amount",
          adjustmentReason: "Adjustment reason",
          applyAdjustment: "Apply adjustment",
          ledger: "Recent ledger",
          ledgerEmpty: "No credit ledger entries yet.",
          grantAdmin: "Grant admin",
          revokeAdmin: "Revoke admin",
          activate: "Activate",
          suspend: "Suspend",
          balanceAfter: (amount: string) => `Balance after ${amount}`,
        },
        apiKeys: {
          title: "API Keys",
          account: "Account",
          keyName: "Key name",
          perMinute: "Per minute",
          perHour: "Per hour",
          perDay: "Per day",
          createKey: "Create API key",
          columnName: "Name",
          columnAccountId: "Account ID",
          columnPrefix: "Prefix",
          columnStatus: "Status",
          revoke: "Revoke",
          createdKey: "Last created raw key",
        },
        usage: {
          title: "Usage",
          keyActivity: "Key activity",
          providers: "By provider",
          models: "By model",
          requestsLimited: (requests: number, limited: number) => `${requests} requests · ${limited} limited`,
          lastUsed: (value: string | null) => value ?? "No activity yet",
        },
        permissions: {
          title: "Permissions",
          lead: "Control which accounts can enter Admin and whether each account can keep using API access.",
          admins: "Admins",
          members: "Members",
        },
        settings: {
          title: "Settings",
          adminSecretConfigured: "Admin access configured",
          authProviders: "Auth providers",
        },
      };

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      const [summaryRow, timeseriesRow, syncSummaryRow, settingsRow, providerRows, healthRows, accountRows, apiKeyRows, usageRow] = await Promise.all([
        getAdminDashboardSummary(adminSecret),
        getAdminDashboardTimeseries(adminSecret, dashboardWindow),
        getAdminAccountSyncSummary(adminSecret),
        getAdminSettingsOverview(adminSecret),
        getAdminProviders(adminSecret),
        getAdminHealth(adminSecret),
        getAdminAccounts(adminSecret),
        getAdminApiKeys(adminSecret),
        getAdminUsageOverview(adminSecret),
      ]);
      setSummary(summaryRow);
      setTimeseries(timeseriesRow);
      setAccountSyncSummary(syncSummaryRow);
      setSettings(settingsRow);
      setProviders(Array.isArray(providerRows) ? providerRows : []);
      setHealth(Array.isArray(healthRows) ? healthRows : []);
      setAccounts(Array.isArray(accountRows) ? accountRows : []);
      setApiKeys(Array.isArray(apiKeyRows) ? apiKeyRows : []);
      setUsage(usageRow);
      if (Array.isArray(accountRows) && accountRows.length > 0 && !selectedAccountId) {
        setSelectedAccountId(String(accountRows[0].id));
      }
      if (Array.isArray(providerRows) && providerRows.length > 0 && !selectedProviderName) {
        setSelectedProviderName(providerRows[0].name);
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "request failed");
    } finally {
      setLoading(false);
    }
  }

  async function loadSelectedProviderModels(providerName: string) {
    const rows = await getAdminProviderModels(adminSecret, providerName);
    setProviderModels((current) => ({ ...current, [providerName]: Array.isArray(rows) ? rows : [] }));
  }

  useEffect(() => {
    void loadData();
  }, [adminSecret, dashboardWindow]);

  useEffect(() => {
    if (!selectedProviderName) return;
    void loadSelectedProviderModels(selectedProviderName);
  }, [selectedProviderName]);

  useEffect(() => {
    const rows = selectedProviderName && Array.isArray(providerModels[selectedProviderName]) ? providerModels[selectedProviderName] : [];
    if (rows.length === 0) {
      setSelectedModelNativeModel("");
      return;
    }
    if (!rows.some((row) => row.native_model === selectedModelNativeModel)) {
      setSelectedModelNativeModel(rows[0].native_model);
    }
  }, [providerModels, selectedProviderName, selectedModelNativeModel]);

  useEffect(() => {
    const currentModel = selectedProviderName && Array.isArray(providerModels[selectedProviderName])
      ? providerModels[selectedProviderName].find((row) => row.native_model === selectedModelNativeModel)
      : null;
    setPricingInput(currentModel?.pricing?.input_price?.toString() ?? "");
    setPricingCachedInput(currentModel?.pricing?.cached_input_price?.toString() ?? "");
    setPricingOutput(currentModel?.pricing?.output_price?.toString() ?? "");
    setPricingNotes(currentModel?.pricing?.notes ?? "");
  }, [providerModels, selectedProviderName, selectedModelNativeModel]);

  useEffect(() => {
    if (!selectedAccountId) return;
    const numericAccountId = Number(selectedAccountId);
    if (!Number.isFinite(numericAccountId)) return;
    void getAdminAccountCreditLedger(adminSecret, numericAccountId).then((rows) => {
      setCreditLedger((current) => ({ ...current, [numericAccountId]: rows }));
    }).catch((ledgerError) => {
      setCreditLedger((current) => ({ ...current, [numericAccountId]: [] }));
      setNotice(ledgerError instanceof Error ? ledgerError.message : "ledger request failed");
    });
  }, [adminSecret, selectedAccountId]);

  async function handleCreateAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const created = await createAdminAccount(adminSecret, {
      name: accountName,
      email: accountEmail || null,
      is_admin: accountIsAdmin,
      notes: accountNotes || null,
    });
    setAccounts((current) => current.concat(created));
    setSelectedAccountId(String(created.id));
    setAccountName("");
    setAccountEmail("");
    setAccountIsAdmin(false);
    setAccountNotes("");
    setNotice(isZh ? "账户已创建。" : "Account created.");
  }

  async function handleUpdateAccount(accountId: number, payload: Parameters<typeof updateAdminAccount>[2]) {
    const updated = await updateAdminAccount(adminSecret, accountId, payload);
    setAccounts((current) => current.map((row) => (row.id === accountId ? updated : row)));
    setNotice(isZh ? "账户已更新。" : "Account updated.");
  }

  async function handleAdjustCredits(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedAccountId || !creditAdjustment.trim()) return;
    const accountId = Number(selectedAccountId);
    const adjusted = await adjustAdminAccountCredits(adminSecret, accountId, {
      credits_delta: Number(creditAdjustment),
      notes: creditAdjustmentReason || undefined,
    });
    setAccounts((current) => current.map((row) => (row.id === adjusted.id ? adjusted : row)));
    const ledger = await getAdminAccountCreditLedger(adminSecret, accountId);
    setCreditLedger((current) => ({ ...current, [accountId]: ledger }));
    setCreditAdjustment("");
    setCreditAdjustmentReason("");
    setNotice(isZh ? "信用点已调整。" : "Credits adjusted.");
  }

  async function handleCreateApiKey(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const created = await createAdminApiKey(adminSecret, {
      account_id: Number(selectedAccountId),
      name: apiKeyName,
      per_minute: apiKeyMinute ? Number(apiKeyMinute) : null,
      per_hour: apiKeyHour ? Number(apiKeyHour) : null,
      per_day: apiKeyDay ? Number(apiKeyDay) : null,
    });
    setApiKeys((current) => current.concat(created));
    setCreatedApiKey(created.api_key);
    setApiKeyName("");
    setApiKeyMinute("");
    setApiKeyHour("");
    setApiKeyDay("");
    setNotice(isZh ? "API Key 已创建。" : "API key created.");
  }

  async function handleRevokeApiKey(keyId: number) {
    const updated = await revokeAdminApiKey(adminSecret, keyId);
    setApiKeys((current) => current.map((row) => (row.id === keyId ? updated : row)));
    setNotice(isZh ? "API Key 已撤销。" : "API key revoked.");
  }

  async function handleCreateProvider(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const created = await createAdminProvider(adminSecret, {
      name: providerName,
      exposed_model: providerExposedModel,
      http_enabled: providerHttpEnabled,
      cli_enabled: providerCliEnabled,
      route_policy: providerRoutePolicy,
      chat_capable: providerChatCapable,
      stream_capable: providerStreamCapable,
      http_base_url: providerHttpEnabled ? providerHttpBaseUrl : null,
      http_api_key: null,
      http_headers_json: "{}",
      cli_command: providerCliEnabled ? providerCliCommand : null,
      cli_args_json: "[]",
      cli_env_json: "{}",
      cli_cwd: null,
    });
    setProviders((current) => current.concat(created));
    setSelectedProviderName(created.name);
    setProviderName("");
    setProviderExposedModel("default");
    setProviderRoutePolicy("http-first");
    setProviderHttpEnabled(true);
    setProviderCliEnabled(false);
    setProviderChatCapable(true);
    setProviderStreamCapable(true);
    setProviderHttpBaseUrl("");
    setProviderCliCommand("");
    setNotice(isZh ? "Provider 已创建。" : "Provider created.");
    await loadData();
  }

  async function handleRediscoverModels() {
    if (!selectedProviderName) return;
    const rows = await rediscoverAdminProviderModels(adminSecret, selectedProviderName);
    setProviderModels((current) => ({ ...current, [selectedProviderName]: Array.isArray(rows) ? rows : [] }));
    setNotice(isZh ? "模型目录已刷新。" : "Model catalog refreshed.");
  }

  async function handleRefreshPricing() {
    if (!selectedProviderName) return;
    const rows = await refreshAdminProviderPricing(adminSecret, selectedProviderName);
    setProviderModels((current) => ({ ...current, [selectedProviderName]: Array.isArray(rows) ? rows : [] }));
    setNotice(isZh ? "价格快照已刷新。" : "Pricing snapshot refreshed.");
  }

  async function handleToggleModel(nativeModel: string, enabled: boolean) {
    if (!selectedProviderName) return;
    const updated = await patchAdminProviderModel(adminSecret, selectedProviderName, nativeModel, { enabled: !enabled });
    setProviderModels((current) => ({
      ...current,
      [selectedProviderName]: (current[selectedProviderName] ?? []).map((row) => row.native_model === nativeModel ? updated : row),
    }));
  }

  async function handleRenameModel(nativeModel: string, exposedModelId: string) {
    if (!selectedProviderName) return;
    const updated = await patchAdminProviderModel(adminSecret, selectedProviderName, nativeModel, { exposed_model_id: exposedModelId });
    setProviderModels((current) => ({
      ...current,
      [selectedProviderName]: (current[selectedProviderName] ?? []).map((row) => row.native_model === nativeModel ? updated : row),
    }));
  }

  async function handleCreateManualModel(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProviderName) return;
    const created = await createAdminProviderModel(adminSecret, selectedProviderName, {
      native_model: manualNativeModel,
      exposed_model_id: manualExposedModelId,
      enabled: true,
    });
    setProviderModels((current) => ({
      ...current,
      [selectedProviderName]: [...(Array.isArray(current[selectedProviderName]) ? current[selectedProviderName] : []), created],
    }));
    setManualNativeModel("");
    setManualExposedModelId("");
  }

  async function handleSavePricing(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProviderName || !selectedModelNativeModel) return;
    const pricing = await patchAdminProviderModelPricing(adminSecret, selectedProviderName, selectedModelNativeModel, {
      input_price: pricingInput ? Number(pricingInput) : null,
      cached_input_price: pricingCachedInput ? Number(pricingCachedInput) : null,
      output_price: pricingOutput ? Number(pricingOutput) : null,
      notes: pricingNotes || null,
    });
    setProviderModels((current) => ({
      ...current,
      [selectedProviderName]: (current[selectedProviderName] ?? []).map((row) => row.native_model === selectedModelNativeModel ? { ...row, pricing } : row),
    }));
    setNotice(isZh ? "价格覆盖已保存。" : "Pricing override saved.");
  }

  async function handleSendModelTest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProviderName || !selectedModelNativeModel || !testMessage.trim()) return;
    setTestChatStatus("loading");
    setTestChatError(null);
    try {
      const response = await sendAdminTestChat(adminSecret, {
        model: `${selectedProviderName}:${selectedModelNativeModel}`,
        messages: [{ role: "user", content: testMessage }],
      });
      const assistantText = response.choices[0]?.message?.content ?? "";
      setTestChatMessages((current) => [...current, { role: "user", content: testMessage }, { role: "assistant", content: assistantText }]);
      setTestMessage("");
      setTestChatStatus("idle");
    } catch (testError) {
      setTestChatStatus("error");
      setTestChatError(testError instanceof Error ? testError.message : "request failed");
    }
  }

  async function handleStreamModelTest() {
    if (!selectedProviderName || !selectedModelNativeModel || !testMessage.trim() || testChatStatus === "loading") return;
    const prompt = testMessage;
    const controller = new AbortController();
    setTestStreamAbortController(controller);
    setTestChatStatus("loading");
    setTestChatError(null);
    setTestChatMessages((current) => [...current, { role: "user", content: prompt }, { role: "assistant", content: "" }]);
    setTestMessage("");
    try {
      await streamAdminTestChat(
        adminSecret,
        {
          model: `${selectedProviderName}:${selectedModelNativeModel}`,
          messages: [{ role: "user", content: prompt }],
        },
        {
          signal: controller.signal,
          onChunk: (chunk) => {
            const text = chunk.choices?.[0]?.delta?.content ?? "";
            if (!text) return;
            setTestChatMessages((current) => {
              const next = [...current];
              const last = next[next.length - 1];
              if (last && last.role === "assistant") {
                next[next.length - 1] = { ...last, content: `${last.content}${text}` };
              }
              return next;
            });
          },
        },
      );
      setTestChatStatus("idle");
    } catch (testError) {
      if ((testError as Error).name !== "AbortError") {
        setTestChatStatus("error");
        setTestChatError(testError instanceof Error ? testError.message : "request failed");
      } else {
        setTestChatStatus("idle");
      }
    } finally {
      setTestStreamAbortController(null);
    }
  }

  function handleCancelStream() {
    testStreamAbortController?.abort();
    setTestStreamAbortController(null);
  }

  const selectedProviderModels = selectedProviderName && Array.isArray(providerModels[selectedProviderName]) ? providerModels[selectedProviderName] : [];
  const selectedModel = selectedProviderModels.find((row) => row.native_model === selectedModelNativeModel) ?? null;
  const healthByProvider = new Map(health.map((item) => [item.name, item]));
  const chart = buildTrafficPath(timeseries);
  const totalSeriesRequests = (timeseries?.buckets ?? []).reduce((sum, bucket) => sum + bucket.total_requests, 0);
  const totalSeriesErrors = (timeseries?.buckets ?? []).reduce((sum, bucket) => sum + bucket.error_requests, 0);
  const totalSeriesLimited = (timeseries?.buckets ?? []).reduce((sum, bucket) => sum + bucket.limited_requests, 0);

  return (
    <main className="admin-shell">
      <section className="admin-shell__hero">
        <div>
          <div className="eyebrow">Admin</div>
          <h1>{copy.title}</h1>
        </div>
        <button className="ghost-action ghost-action--bright" onClick={onLogout}>
          {copy.logout}
        </button>
      </section>
      <nav className="admin-shell__nav" aria-label="Admin navigation">
        <button className={view === "overview" ? "active" : ""} onClick={() => setView("overview")}>{copy.nav.overview}</button>
        <button className={view === "providers" ? "active" : ""} onClick={() => setView("providers")}>{copy.nav.providers}</button>
        <button className={view === "models" ? "active" : ""} onClick={() => setView("models")}>{copy.nav.models}</button>
        <button className={view === "accounts" ? "active" : ""} onClick={() => setView("accounts")}>{copy.nav.accounts}</button>
        <button className={view === "api-keys" ? "active" : ""} onClick={() => setView("api-keys")}>{copy.nav.apiKeys}</button>
        <button className={view === "usage" ? "active" : ""} onClick={() => setView("usage")}>{copy.nav.usage}</button>
        <button className={view === "permissions" ? "active" : ""} onClick={() => setView("permissions")}>{copy.nav.permissions}</button>
        <button className={view === "settings" ? "active" : ""} onClick={() => setView("settings")}>{copy.nav.settings}</button>
      </nav>
      {loading ? <div className="empty-state empty-state--loading">{copy.loading}</div> : null}
      {notice ? <div className="inline-success">{notice}</div> : null}
      {error ? <div className="inline-error">{error}</div> : null}

      {!loading && !error && view === "overview" ? (
        <section className="admin-grid">
          <article className="metric-card"><span>{copy.overview.totalRequests}</span><strong>{summary?.total_requests ?? 0}</strong></article>
          <article className="metric-card"><span>{copy.overview.activeKeys}</span><strong>{summary?.active_api_keys ?? 0}</strong></article>
          <article className="metric-card"><span>{copy.overview.errorRate}</span><strong>{summary ? `${(summary.error_rate * 100).toFixed(2)}%` : "0%"}</strong></article>
          <article className="metric-card"><span>{copy.overview.rateLimitHits}</span><strong>{summary?.rate_limit_hits ?? 0}</strong></article>
          <article className="detail-panel detail-panel--wide">
            <div className="detail-panel__title-row">
              <h3>{copy.overview.traffic}</h3>
              <div className="model-chip-group">
                <button className={dashboardWindow === "24h" ? "ghost-action ghost-action--bright" : "ghost-action"} onClick={() => setDashboardWindow("24h")}>24h</button>
                <button className={dashboardWindow === "7d" ? "ghost-action ghost-action--bright" : "ghost-action"} onClick={() => setDashboardWindow("7d")}>7d</button>
              </div>
            </div>
            <svg viewBox="0 0 600 180" className="chart-svg" aria-hidden="true">
              <defs>
                <linearGradient id="admin-traffic-fill" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="rgba(14,165,233,0.28)" />
                  <stop offset="100%" stopColor="rgba(14,165,233,0)" />
                </linearGradient>
              </defs>
              <path d={chart.stroke} fill="none" stroke="rgba(14,165,233,0.9)" strokeWidth="4" strokeLinecap="round" />
              <path d={chart.fill} fill="url(#admin-traffic-fill)" />
            </svg>
            <div className="chart-footer">
              <span>{copy.overview.requestsInWindow(totalSeriesRequests)}</span>
              <span>{copy.overview.errorCount(totalSeriesErrors)}</span>
              <span>{copy.overview.limitedCount(totalSeriesLimited)}</span>
            </div>
          </article>
          <article className="detail-panel detail-panel--wide">
            <h3>{copy.overview.accountSync}</h3>
            <div className="detail-panel__meta">
              <span>{`${copy.overview.totalAccounts}: ${accountSyncSummary?.total_accounts ?? 0}`}</span>
              <span>{`${copy.overview.mirroredAccounts}: ${accountSyncSummary?.mirrored_accounts ?? 0}`}</span>
              <span>{`${copy.overview.pendingAccounts}: ${accountSyncSummary?.accounts_needing_backfill ?? 0}`}</span>
              <span>{`${copy.overview.failedAccounts}: ${accountSyncSummary?.accounts_with_failed_sync ?? 0}`}</span>
            </div>
          </article>
          <article className="detail-panel detail-panel--wide">
            <h3>{copy.overview.settings}</h3>
            <div className="detail-panel__meta">
              <span>{`${copy.overview.gatewayHost}: ${settings?.gateway_host ?? "-"}:${settings?.gateway_port ?? "-"}`}</span>
              <span>{`${copy.overview.frontendBaseUrl}: ${settings?.frontend_base_url ?? "-"}`}</span>
              <span>{`${copy.overview.databaseScheme}: ${settings?.database_scheme ?? "-"}`}</span>
              <span>{`${copy.overview.authMode}: email=${String(settings?.email_password_enabled ?? false)} github=${String(settings?.github_oauth_enabled ?? false)} google=${String(settings?.google_oauth_enabled ?? false)}`}</span>
            </div>
          </article>
        </section>
      ) : null}

      {!loading && !error && view === "providers" ? (
        <section className="detail-grid">
          <article className="form-panel">
            <div className="form-panel__header"><div><h3>{copy.providers.createTitle}</h3><p>{copy.providers.createLead}</p></div></div>
            <form className="provider-form" onSubmit={handleCreateProvider}>
              <label><span>{copy.providers.providerName}</span><input value={providerName} onChange={(event) => setProviderName(event.target.value)} /></label>
              <label><span>{copy.providers.exposedModel}</span><input value={providerExposedModel} onChange={(event) => setProviderExposedModel(event.target.value)} /></label>
              <label><span>{copy.providers.routePolicy}</span><select value={providerRoutePolicy} onChange={(event) => setProviderRoutePolicy(event.target.value)}><option value="http-first">http-first</option><option value="cli-first">cli-first</option><option value="fixed-http">fixed-http</option><option value="fixed-cli">fixed-cli</option></select></label>
              <label><span>{copy.providers.httpBaseUrl}</span><input value={providerHttpBaseUrl} onChange={(event) => setProviderHttpBaseUrl(event.target.value)} /></label>
              <label><span>{copy.providers.cliCommand}</span><input value={providerCliCommand} onChange={(event) => setProviderCliCommand(event.target.value)} /></label>
              <div className="model-chip-group">
                <label><input checked={providerHttpEnabled} onChange={(event) => setProviderHttpEnabled(event.target.checked)} type="checkbox" /> {copy.providers.httpEnabled}</label>
                <label><input checked={providerCliEnabled} onChange={(event) => setProviderCliEnabled(event.target.checked)} type="checkbox" /> {copy.providers.cliEnabled}</label>
                <label><input checked={providerChatCapable} onChange={(event) => setProviderChatCapable(event.target.checked)} type="checkbox" /> {copy.providers.chatCapable}</label>
                <label><input checked={providerStreamCapable} onChange={(event) => setProviderStreamCapable(event.target.checked)} type="checkbox" /> {copy.providers.streamCapable}</label>
              </div>
              <button className="primary-action" disabled={!providerName.trim()} type="submit">{copy.providers.addProvider}</button>
            </form>
          </article>
          <article className="detail-panel detail-panel--wide">
            <h3>{copy.providers.healthTitle}</h3>
            <div className="provider-list">
              {providers.map((provider) => {
                const healthRow = healthByProvider.get(provider.name);
                const isHealthy = healthRow ? healthRow.capabilities.http || healthRow.capabilities.cli : false;
                return (
                  <article className="provider-row" key={provider.id}>
                    <div className="provider-row__body">
                      <strong>{provider.name}</strong>
                      <p>{provider.route_policy}</p>
                      <small>{provider.http_base_url ?? provider.cli_command ?? "-"}</small>
                    </div>
                    <div className="provider-row__actions">
                      <span className={`status-pill ${isHealthy ? "status-pill--ok" : "status-pill--warning"}`}>{isHealthy ? copy.providers.healthy : copy.providers.pending}</span>
                      <button className="ghost-action ghost-action--bright" onClick={() => { setSelectedProviderName(provider.name); setView("models"); }}>{copy.providers.openModels}</button>
                    </div>
                  </article>
                );
              })}
            </div>
          </article>
        </section>
      ) : null}

      {!loading && !error && view === "models" ? (
        <section className="detail-grid">
          <article className="detail-panel detail-panel--wide">
            <div className="detail-panel__title-row">
              <div><h3>{copy.models.title}</h3><p>{selectedProviderName || copy.models.noProvider}</p></div>
              <div className="model-chip-group">
                <button className="ghost-action ghost-action--bright" disabled={!selectedProviderName} onClick={() => void handleRediscoverModels()}>{copy.models.refresh}</button>
                <button className="ghost-action ghost-action--bright" disabled={!selectedProviderName} onClick={() => void handleRefreshPricing()}>{copy.models.refreshPricing}</button>
              </div>
            </div>
            {selectedProviderName ? (
              <div className="table-shell">
                <table className="data-table">
                  <thead><tr><th>{copy.models.nativeModel}</th><th>{copy.models.exposedAs}</th><th>{copy.models.source}</th><th>{copy.models.state}</th><th>{copy.models.action}</th></tr></thead>
                  <tbody>
                    {selectedProviderModels.map((model) => (
                      <tr key={model.id}>
                        <td>{model.native_model}</td>
                        <td>{model.exposed_model_id}</td>
                        <td>{model.pricing?.input_price != null && model.pricing?.output_price != null ? `${model.source} · $${model.pricing.input_price}/$${model.pricing.output_price}` : model.source}</td>
                        <td>{model.enabled ? "enabled" : "disabled"}</td>
                        <td className="data-table__actions">
                          <button className="ghost-action ghost-action--bright" onClick={() => void handleToggleModel(model.native_model, model.enabled)}>{model.enabled ? copy.models.disable : copy.models.enable}</button>
                          <button className="ghost-action ghost-action--bright" onClick={() => { setSelectedModelNativeModel(model.native_model); const nextId = globalThis.prompt?.(copy.models.exposedAs, model.exposed_model_id); if (nextId && nextId !== model.exposed_model_id) void handleRenameModel(model.native_model, nextId); }}>{copy.models.rename}</button>
                          <button className="ghost-action ghost-action--bright" onClick={() => setSelectedModelNativeModel(model.native_model)}>{copy.models.select}</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </article>
          {selectedProviderName ? (
            <article className="form-panel">
              <div className="form-panel__header"><div><h3>{copy.models.manualTitle}</h3></div></div>
              <form className="inline-form" onSubmit={handleCreateManualModel}>
                <label><span>{copy.models.nativeModel}</span><input value={manualNativeModel} onChange={(event) => setManualNativeModel(event.target.value)} /></label>
                <label><span>{copy.models.exposedAs}</span><input value={manualExposedModelId} onChange={(event) => setManualExposedModelId(event.target.value)} /></label>
                <button className="primary-action" disabled={!manualNativeModel.trim() || !manualExposedModelId.trim()} type="submit">{copy.models.addModel}</button>
              </form>
            </article>
          ) : null}
          {selectedModel ? (
            <article className="detail-panel">
              <h3>{copy.models.pricingWorkspace}</h3>
              <p>{copy.models.pricingSummary}</p>
              <form className="inline-form" onSubmit={handleSavePricing}>
                <label><span>{copy.models.inputPrice}</span><input value={pricingInput} onChange={(event) => setPricingInput(event.target.value)} /></label>
                <label><span>{copy.models.cachedInputPrice}</span><input value={pricingCachedInput} onChange={(event) => setPricingCachedInput(event.target.value)} /></label>
                <label><span>{copy.models.outputPrice}</span><input value={pricingOutput} onChange={(event) => setPricingOutput(event.target.value)} /></label>
                <label><span>{copy.models.pricingNotes}</span><input value={pricingNotes} onChange={(event) => setPricingNotes(event.target.value)} /></label>
                <button className="primary-action" type="submit">{copy.models.savePricing}</button>
              </form>
            </article>
          ) : null}
          {selectedModel ? (
            <article className="detail-panel">
              <h3>{copy.models.testWorkspace}</h3>
              <form className="inline-form" onSubmit={handleSendModelTest}>
                <label><span>{selectedModel.native_model}</span><input value={testMessage} onChange={(event) => setTestMessage(event.target.value)} /></label>
                <div className="data-table__actions">
                  <button className="primary-action" disabled={!testMessage.trim() || testChatStatus === "loading"} type="submit">{copy.models.sendTest}</button>
                  <button className="ghost-action ghost-action--bright" disabled={!testMessage.trim() || testChatStatus === "loading"} onClick={() => void handleStreamModelTest()} type="button">{copy.models.streamTest}</button>
                  <button className="ghost-action" disabled={testChatStatus !== "loading"} onClick={handleCancelStream} type="button">{copy.models.cancelStream}</button>
                </div>
              </form>
              {testChatError ? <div className="inline-error">{testChatError}</div> : null}
              <div className="provider-list">
                {testChatMessages.length === 0 ? (
                  <div className="empty-state empty-state--compact">{copy.models.noTranscript}</div>
                ) : testChatMessages.map((message, index) => (
                  <article className="provider-row" key={`${message.role}-${index}`}>
                    <div className="provider-row__body"><strong>{message.role}</strong><p>{message.content || "..."}</p></div>
                  </article>
                ))}
              </div>
            </article>
          ) : null}
        </section>
      ) : null}

      {!loading && !error && view === "accounts" ? (
        <section className="detail-grid">
          <article className="form-panel">
            <div className="form-panel__header"><div><h3>{copy.accounts.title}</h3></div></div>
            <form className="inline-form" onSubmit={handleCreateAccount}>
              <label><span>{copy.accounts.accountName}</span><input value={accountName} onChange={(event) => setAccountName(event.target.value)} /></label>
              <label><span>{copy.accounts.accountEmail}</span><input value={accountEmail} onChange={(event) => setAccountEmail(event.target.value)} /></label>
              <label><span>{copy.accounts.accountNotes}</span><input value={accountNotes} onChange={(event) => setAccountNotes(event.target.value)} /></label>
              <label><input checked={accountIsAdmin} onChange={(event) => setAccountIsAdmin(event.target.checked)} type="checkbox" /> {copy.accounts.adminRole}</label>
              <button className="primary-action" disabled={!accountName.trim()} type="submit">{copy.accounts.addAccount}</button>
            </form>
          </article>
          <article className="form-panel">
            <div className="form-panel__header"><div><h3>{copy.accounts.adjustCredits}</h3></div></div>
            <form className="inline-form" onSubmit={handleAdjustCredits}>
              <label><span>{copy.apiKeys.account}</span><select value={selectedAccountId} onChange={(event) => setSelectedAccountId(event.target.value)}>{accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}</select></label>
              <label><span>{copy.accounts.adjustmentAmount}</span><input value={creditAdjustment} onChange={(event) => setCreditAdjustment(event.target.value)} /></label>
              <label><span>{copy.accounts.adjustmentReason}</span><input value={creditAdjustmentReason} onChange={(event) => setCreditAdjustmentReason(event.target.value)} /></label>
              <button className="primary-action" disabled={!selectedAccountId || !creditAdjustment.trim()} type="submit">{copy.accounts.applyAdjustment}</button>
            </form>
          </article>
          <article className="detail-panel detail-panel--wide">
            <div className="table-shell">
              <table className="data-table">
                <thead><tr><th>{copy.accounts.columnName}</th><th>{copy.accounts.columnEmail}</th><th>{copy.accounts.columnAdmin}</th><th>{copy.accounts.columnStatus}</th><th>{copy.accounts.balance}</th><th>{copy.accounts.columnMirror}</th><th>{copy.models.action}</th></tr></thead>
                <tbody>
                  {accounts.map((account) => (
                    <tr key={account.id}>
                      <td>{account.name}</td>
                      <td>{account.email ?? "-"}</td>
                      <td>{account.is_admin ? "yes" : "no"}</td>
                      <td>{account.status}</td>
                      <td>{account.credit_balance ?? 0}</td>
                      <td>{account.public_account_id ?? account.public_workspace_id ?? "-"}</td>
                      <td className="data-table__actions">
                        <button className="ghost-action ghost-action--bright" onClick={() => setSelectedAccountId(String(account.id))}>{copy.models.select}</button>
                        <button className="ghost-action ghost-action--bright" onClick={() => void handleUpdateAccount(account.id, { is_admin: !account.is_admin })}>{account.is_admin ? copy.accounts.revokeAdmin : copy.accounts.grantAdmin}</button>
                        <button className={account.status === "active" ? "ghost-action ghost-action--danger" : "ghost-action ghost-action--bright"} onClick={() => void handleUpdateAccount(account.id, { status: account.status === "active" ? "suspended" : "active" })}>{account.status === "active" ? copy.accounts.suspend : copy.accounts.activate}</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>
          <article className="detail-panel detail-panel--wide">
            <h3>{copy.accounts.ledger}</h3>
            <div className="provider-list">
              {(creditLedger[Number(selectedAccountId)] ?? []).length === 0 ? (
                <div className="empty-state empty-state--compact">{copy.accounts.ledgerEmpty}</div>
              ) : (
                (creditLedger[Number(selectedAccountId)] ?? []).map((entry) => (
                  <article className="provider-row" key={entry.id}>
                    <div className="provider-row__body">
                      <strong>{`${entry.credits_delta > 0 ? "+" : ""}${entry.credits_delta}`}</strong>
                      <p>{`${entry.entry_type} · ${entry.provider_name ?? "-"} · ${entry.model_id ?? "-"}`}</p>
                      {entry.notes ? <small>{entry.notes}</small> : null}
                      <small>{copy.accounts.balanceAfter(String(entry.balance_after))}</small>
                    </div>
                    <div className="provider-row__actions"><small>{new Date(entry.created_at).toLocaleString(isZh ? "zh-CN" : "en-US")}</small></div>
                  </article>
                ))
              )}
            </div>
          </article>
        </section>
      ) : null}

      {!loading && !error && view === "api-keys" ? (
        <section className="detail-grid">
          <article className="form-panel">
            <div className="form-panel__header"><div><h3>{copy.apiKeys.title}</h3></div></div>
            <form className="inline-form api-key-form" onSubmit={handleCreateApiKey}>
              <label><span>{copy.apiKeys.account}</span><select value={selectedAccountId} onChange={(event) => setSelectedAccountId(event.target.value)}>{accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}</select></label>
              <label><span>{copy.apiKeys.keyName}</span><input value={apiKeyName} onChange={(event) => setApiKeyName(event.target.value)} /></label>
              <label><span>{copy.apiKeys.perMinute}</span><input value={apiKeyMinute} onChange={(event) => setApiKeyMinute(event.target.value)} /></label>
              <label><span>{copy.apiKeys.perHour}</span><input value={apiKeyHour} onChange={(event) => setApiKeyHour(event.target.value)} /></label>
              <label><span>{copy.apiKeys.perDay}</span><input value={apiKeyDay} onChange={(event) => setApiKeyDay(event.target.value)} /></label>
              <button className="primary-action" disabled={!selectedAccountId || !apiKeyName.trim()} type="submit">{copy.apiKeys.createKey}</button>
            </form>
            {createdApiKey ? <div className="secret-banner"><div><strong>{copy.apiKeys.createdKey}</strong><code>{createdApiKey}</code></div></div> : null}
          </article>
          <article className="detail-panel detail-panel--wide">
            <div className="table-shell">
              <table className="data-table">
                <thead><tr><th>{copy.apiKeys.columnName}</th><th>{copy.apiKeys.columnAccountId}</th><th>{copy.apiKeys.columnPrefix}</th><th>{copy.apiKeys.columnStatus}</th><th>{copy.models.action}</th></tr></thead>
                <tbody>
                  {apiKeys.map((apiKey) => (
                    <tr key={apiKey.id}>
                      <td>{apiKey.name}</td>
                      <td>{apiKey.account_id}</td>
                      <td>{apiKey.key_prefix}</td>
                      <td>{apiKey.status}</td>
                      <td>{apiKey.status === "active" ? <button className="ghost-action ghost-action--danger" onClick={() => void handleRevokeApiKey(apiKey.id)}>{copy.apiKeys.revoke}</button> : null}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>
        </section>
      ) : null}

      {!loading && !error && view === "usage" ? (
        <section className="detail-grid">
          <article className="detail-panel">
            <h3>{copy.usage.keyActivity}</h3>
            <div className="provider-list">
              {(usage?.key_activity ?? []).map((item) => (
                <article className="provider-row" key={item.api_key_id}>
                  <div className="provider-row__body">
                    <strong>{item.name}</strong>
                    <p>{copy.usage.requestsLimited(item.total_requests, item.limited_requests)}</p>
                    <small>{copy.usage.lastUsed(item.last_used_at)}</small>
                  </div>
                </article>
              ))}
            </div>
          </article>
          <article className="detail-panel">
            <h3>{copy.usage.providers}</h3>
            <div className="detail-panel__meta">{Object.entries(usage?.by_provider ?? {}).map(([name, count]) => <span key={name}>{`${name}: ${count}`}</span>)}</div>
          </article>
          <article className="detail-panel">
            <h3>{copy.usage.models}</h3>
            <div className="detail-panel__meta">{Object.entries(usage?.by_model ?? {}).map(([name, count]) => <span key={name}>{`${name}: ${count}`}</span>)}</div>
          </article>
        </section>
      ) : null}

      {!loading && !error && view === "permissions" ? (
        <section className="detail-grid">
          <article className="detail-panel detail-panel--wide">
            <div className="detail-panel__title-row">
              <div><h3>{copy.permissions.title}</h3><p>{copy.permissions.lead}</p></div>
            </div>
            <div className="detail-panel__meta">
              <span>{`${copy.permissions.admins}: ${accounts.filter((account) => account.is_admin).length}`}</span>
              <span>{`${copy.permissions.members}: ${accounts.filter((account) => !account.is_admin).length}`}</span>
              <span>{`${copy.overview.totalAccounts}: ${accounts.length}`}</span>
            </div>
          </article>
          <article className="detail-panel detail-panel--wide">
            <div className="table-shell">
              <table className="data-table">
                <thead><tr><th>{copy.accounts.columnName}</th><th>{copy.accounts.columnEmail}</th><th>{copy.accounts.columnAdmin}</th><th>{copy.accounts.columnStatus}</th><th>{copy.models.action}</th></tr></thead>
                <tbody>
                  {accounts.map((account) => (
                    <tr key={account.id}>
                      <td>{account.name}</td>
                      <td>{account.email ?? "-"}</td>
                      <td><span className={`status-pill ${account.is_admin ? "status-pill--ok" : "status-pill--warning"}`}>{account.is_admin ? copy.permissions.admins : copy.permissions.members}</span></td>
                      <td>{account.status}</td>
                      <td className="data-table__actions">
                        <button className="ghost-action ghost-action--bright" onClick={() => void handleUpdateAccount(account.id, { is_admin: !account.is_admin })}>{account.is_admin ? copy.accounts.revokeAdmin : copy.accounts.grantAdmin}</button>
                        <button className={account.status === "active" ? "ghost-action ghost-action--danger" : "ghost-action ghost-action--bright"} onClick={() => void handleUpdateAccount(account.id, { status: account.status === "active" ? "suspended" : "active" })}>{account.status === "active" ? copy.accounts.suspend : copy.accounts.activate}</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>
        </section>
      ) : null}

      {!loading && !error && view === "settings" ? (
        <section className="detail-grid">
          <article className="detail-panel detail-panel--wide">
            <h3>{copy.settings.title}</h3>
            <div className="detail-panel__meta">
              <span>{`${copy.overview.gatewayHost}: ${settings?.gateway_host ?? "-"}:${settings?.gateway_port ?? "-"}`}</span>
              <span>{`${copy.overview.frontendBaseUrl}: ${settings?.frontend_base_url ?? "-"}`}</span>
              <span>{`${copy.overview.databaseScheme}: ${settings?.database_scheme ?? "-"}`}</span>
              <span>{`${copy.settings.adminSecretConfigured}: ${String(settings?.admin_secret_configured ?? false)}`}</span>
              <span>{`${copy.settings.authProviders}: email=${String(settings?.email_password_enabled ?? false)} github=${String(settings?.github_oauth_enabled ?? false)} google=${String(settings?.google_oauth_enabled ?? false)}`}</span>
            </div>
          </article>
        </section>
      ) : null}
    </main>
  );
}
