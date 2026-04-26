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
  AdminUsageRecord,
} from "../../api";
import {
  adjustAdminAccountCredits,
  getAdminAccountSyncSummary,
  createAdminAccount,
  createAdminApiKey,
  createAdminProvider,
  createAdminProviderModel,
  deleteAdminAccount,
  deleteAdminApiKey,
  deleteAdminProvider,
  deleteAdminProviderModel,
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
  getAdminUsageRecords,
  patchAdminProviderModelPricing,
  patchAdminProviderModel,
  rediscoverAdminProviderModels,
  refreshAdminProviderPricing,
  sendAdminTestChat,
  streamAdminTestChat,
  updateAdminApiKey,
  updateAdminAccount,
  updateAdminProvider,
} from "../../api";
import type { Locale } from "../../i18n";

type AdminShellProps = {
  adminSecret: string;
  locale: Locale;
  onLogout: () => void;
};

type AdminView = "overview" | "providers" | "models" | "accounts" | "api-keys" | "usage" | "permissions" | "settings";
type AdminModal =
  | { kind: "provider-create" }
  | { kind: "provider-edit"; provider: AdminProviderRecord }
  | { kind: "provider-delete"; provider: AdminProviderRecord }
  | { kind: "model-create" }
  | { kind: "model-edit"; model: AdminProviderModelRecord }
  | { kind: "model-delete"; model: AdminProviderModelRecord }
  | { kind: "model-pricing"; model: AdminProviderModelRecord }
  | { kind: "model-test"; model: AdminProviderModelRecord }
  | { kind: "account-create" }
  | { kind: "account-edit"; account: AdminAccountRecord }
  | { kind: "account-delete"; account: AdminAccountRecord }
  | { kind: "credit-adjust"; account: AdminAccountRecord }
  | { kind: "api-key-create" }
  | { kind: "api-key-edit"; apiKey: AdminApiKeyRecord }
  | { kind: "api-key-delete"; apiKey: AdminApiKeyRecord };

function parseOptionalInt(value: string): number | null {
  if (!value.trim()) {
    return null;
  }
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

function formatUsageTokens(row: AdminUsageRecord): string {
  if (row.input_tokens == null && row.output_tokens == null && row.cached_input_tokens == null) {
    return "-";
  }
  return `${row.input_tokens ?? 0} / ${row.cached_input_tokens ?? 0} / ${row.output_tokens ?? 0}`;
}

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
  const [modal, setModal] = useState<AdminModal | null>(null);
  const [modalError, setModalError] = useState<string | null>(null);
  const [modalBusy, setModalBusy] = useState(false);
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
  const [usageRecords, setUsageRecords] = useState<AdminUsageRecord[]>([]);
  const [selectedProviderName, setSelectedProviderName] = useState("");
  const [providerModels, setProviderModels] = useState<Record<string, AdminProviderModelRecord[]>>({});
  const [selectedModelNativeModel, setSelectedModelNativeModel] = useState("");

  const [accountName, setAccountName] = useState("");
  const [accountEmail, setAccountEmail] = useState("");
  const [accountIsAdmin, setAccountIsAdmin] = useState(false);
  const [accountStatus, setAccountStatus] = useState("active");
  const [accountNotes, setAccountNotes] = useState("");
  const [creditAdjustment, setCreditAdjustment] = useState("");
  const [creditAdjustmentReason, setCreditAdjustmentReason] = useState("");
  const [selectedAccountId, setSelectedAccountId] = useState("");
  const [apiKeyName, setApiKeyName] = useState("");
  const [apiKeyMinute, setApiKeyMinute] = useState("");
  const [apiKeyHour, setApiKeyHour] = useState("");
  const [apiKeyDay, setApiKeyDay] = useState("");
  const [apiKeyStatus, setApiKeyStatus] = useState("active");
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
  const [manualModelEnabled, setManualModelEnabled] = useState(true);
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
          records: "Usage 明细",
          keyActivity: "Key 活动",
          providers: "按 Provider",
          models: "按模型",
          time: "时间",
          account: "账户",
          apiKey: "API Key",
          provider: "Provider",
          model: "模型",
          outcome: "结果",
          tokens: "Tokens",
          credits: "信用点",
          usd: "USD",
          source: "来源",
          count: "次数",
          empty: "还没有 Usage 流水。",
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
          records: "Usage records",
          keyActivity: "Key activity",
          providers: "By provider",
          models: "By model",
          time: "Time",
          account: "Account",
          apiKey: "API Key",
          provider: "Provider",
          model: "Model",
          outcome: "Outcome",
          tokens: "Tokens",
          credits: "Credits",
          usd: "USD",
          source: "Source",
          count: "Count",
          empty: "No usage records yet.",
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
  const actionCopy = isZh
    ? {
        create: "新建",
        edit: "编辑",
        delete: "删除",
        cancel: "取消",
        save: "保存",
        confirmDelete: "确认删除",
        close: "关闭",
        test: "测试",
        pricing: "价格",
        adjustCredits: "调整信用点",
        rawKey: "明文 Key 只展示一次",
      }
    : {
        create: "Create",
        edit: "Edit",
        delete: "Delete",
        cancel: "Cancel",
        save: "Save",
        confirmDelete: "Confirm delete",
        close: "Close",
        test: "Test",
        pricing: "Pricing",
        adjustCredits: "Adjust credits",
        rawKey: "Raw key is shown once",
      };

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      const [
        summaryRow,
        timeseriesRow,
        syncSummaryRow,
        settingsRow,
        providerRows,
        healthRows,
        accountRows,
        apiKeyRows,
        usageRow,
        usageRecordRows,
      ] = await Promise.all([
        getAdminDashboardSummary(adminSecret),
        getAdminDashboardTimeseries(adminSecret, dashboardWindow),
        getAdminAccountSyncSummary(adminSecret),
        getAdminSettingsOverview(adminSecret),
        getAdminProviders(adminSecret),
        getAdminHealth(adminSecret),
        getAdminAccounts(adminSecret),
        getAdminApiKeys(adminSecret),
        getAdminUsageOverview(adminSecret),
        getAdminUsageRecords(adminSecret),
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
      setUsageRecords(Array.isArray(usageRecordRows) ? usageRecordRows : []);
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

  function openModal(next: AdminModal) {
    setModalError(null);
    setModal(next);
  }

  function closeModal() {
    if (modalBusy) return;
    setModal(null);
    setModalError(null);
  }

  function openProviderCreateModal() {
    setProviderName("");
    setProviderExposedModel("default");
    setProviderRoutePolicy("http-first");
    setProviderHttpEnabled(true);
    setProviderCliEnabled(false);
    setProviderChatCapable(true);
    setProviderStreamCapable(true);
    setProviderHttpBaseUrl("");
    setProviderCliCommand("");
    openModal({ kind: "provider-create" });
  }

  function openProviderEditModal(provider: AdminProviderRecord) {
    setProviderName(provider.name);
    setProviderExposedModel(provider.exposed_model);
    setProviderRoutePolicy(provider.route_policy);
    setProviderHttpEnabled(provider.http_enabled);
    setProviderCliEnabled(provider.cli_enabled);
    setProviderChatCapable(provider.chat_capable);
    setProviderStreamCapable(provider.stream_capable);
    setProviderHttpBaseUrl(provider.http_base_url ?? "");
    setProviderCliCommand(provider.cli_command ?? "");
    openModal({ kind: "provider-edit", provider });
  }

  function openModelCreateModal() {
    setManualNativeModel("");
    setManualExposedModelId("");
    setManualModelEnabled(true);
    openModal({ kind: "model-create" });
  }

  function openModelEditModal(model: AdminProviderModelRecord) {
    setManualNativeModel(model.native_model);
    setManualExposedModelId(model.exposed_model_id);
    setManualModelEnabled(model.enabled);
    setSelectedModelNativeModel(model.native_model);
    openModal({ kind: "model-edit", model });
  }

  function openModelPricingModal(model: AdminProviderModelRecord) {
    setSelectedModelNativeModel(model.native_model);
    setPricingInput(model.pricing?.input_price?.toString() ?? "");
    setPricingCachedInput(model.pricing?.cached_input_price?.toString() ?? "");
    setPricingOutput(model.pricing?.output_price?.toString() ?? "");
    setPricingNotes(model.pricing?.notes ?? "");
    openModal({ kind: "model-pricing", model });
  }

  function openModelTestModal(model: AdminProviderModelRecord) {
    setSelectedModelNativeModel(model.native_model);
    setTestMessage("");
    setTestChatError(null);
    setTestChatStatus("idle");
    setTestChatMessages([]);
    openModal({ kind: "model-test", model });
  }

  function openAccountCreateModal() {
    setAccountName("");
    setAccountEmail("");
    setAccountIsAdmin(false);
    setAccountStatus("active");
    setAccountNotes("");
    openModal({ kind: "account-create" });
  }

  function openAccountEditModal(account: AdminAccountRecord) {
    setAccountName(account.name);
    setAccountEmail(account.email ?? "");
    setAccountIsAdmin(account.is_admin);
    setAccountStatus(account.status);
    setAccountNotes(account.notes ?? "");
    setSelectedAccountId(String(account.id));
    openModal({ kind: "account-edit", account });
  }

  function openCreditAdjustmentModal(account: AdminAccountRecord) {
    setSelectedAccountId(String(account.id));
    setCreditAdjustment("");
    setCreditAdjustmentReason("");
    openModal({ kind: "credit-adjust", account });
  }

  function openApiKeyCreateModal() {
    setApiKeyName("");
    setApiKeyMinute("");
    setApiKeyHour("");
    setApiKeyDay("");
    setApiKeyStatus("active");
    openModal({ kind: "api-key-create" });
  }

  function openApiKeyEditModal(apiKey: AdminApiKeyRecord) {
    setSelectedAccountId(String(apiKey.account_id));
    setApiKeyName(apiKey.name);
    setApiKeyMinute(apiKey.per_minute == null ? "" : String(apiKey.per_minute));
    setApiKeyHour(apiKey.per_hour == null ? "" : String(apiKey.per_hour));
    setApiKeyDay(apiKey.per_day == null ? "" : String(apiKey.per_day));
    setApiKeyStatus(apiKey.status);
    openModal({ kind: "api-key-edit", apiKey });
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

  async function handleSaveAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setModalBusy(true);
    setModalError(null);
    try {
      if (modal?.kind === "account-edit") {
        const updated = await updateAdminAccount(adminSecret, modal.account.id, {
          name: accountName,
          email: accountEmail || null,
          status: accountStatus,
          is_admin: accountIsAdmin,
          notes: accountNotes || null,
        });
        setAccounts((current) => current.map((row) => (row.id === updated.id ? updated : row)));
        setNotice(isZh ? "账户已更新。" : "Account updated.");
      } else {
        const created = await createAdminAccount(adminSecret, {
          name: accountName,
          email: accountEmail || null,
          is_admin: accountIsAdmin,
          notes: accountNotes || null,
        });
        setAccounts((current) => current.concat(created));
        setSelectedAccountId(String(created.id));
        setNotice(isZh ? "账户已创建。" : "Account created.");
      }
      setModal(null);
    } catch (saveError) {
      setModalError(saveError instanceof Error ? saveError.message : "request failed");
    } finally {
      setModalBusy(false);
    }
  }

  async function handleUpdateAccount(accountId: number, payload: Parameters<typeof updateAdminAccount>[2]) {
    const updated = await updateAdminAccount(adminSecret, accountId, payload);
    setAccounts((current) => current.map((row) => (row.id === accountId ? updated : row)));
    setNotice(isZh ? "账户已更新。" : "Account updated.");
  }

  async function handleDeleteAccount(account: AdminAccountRecord) {
    setModalBusy(true);
    setModalError(null);
    try {
      const updated = await deleteAdminAccount(adminSecret, account.id);
      setAccounts((current) => current.map((row) => (row.id === updated.id ? updated : row)));
      setNotice(isZh ? "账户已删除。" : "Account deleted.");
      setModal(null);
    } catch (deleteError) {
      setModalError(deleteError instanceof Error ? deleteError.message : "request failed");
    } finally {
      setModalBusy(false);
    }
  }

  async function handleAdjustCredits(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedAccountId || !creditAdjustment.trim()) return;
    setModalBusy(true);
    setModalError(null);
    try {
      const accountId = Number(selectedAccountId);
      const adjusted = await adjustAdminAccountCredits(adminSecret, accountId, {
        credits_delta: Number(creditAdjustment),
        notes: creditAdjustmentReason || undefined,
      });
      setAccounts((current) => current.map((row) => (row.id === adjusted.id ? adjusted : row)));
      const ledger = await getAdminAccountCreditLedger(adminSecret, accountId);
      setCreditLedger((current) => ({ ...current, [accountId]: ledger }));
      setNotice(isZh ? "信用点已调整。" : "Credits adjusted.");
      setModal(null);
    } catch (adjustError) {
      setModalError(adjustError instanceof Error ? adjustError.message : "request failed");
    } finally {
      setModalBusy(false);
    }
  }

  async function handleSaveApiKey(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setModalBusy(true);
    setModalError(null);
    try {
      if (modal?.kind === "api-key-edit") {
        const updated = await updateAdminApiKey(adminSecret, modal.apiKey.id, {
          name: apiKeyName,
          status: apiKeyStatus,
          per_minute: parseOptionalInt(apiKeyMinute),
          per_hour: parseOptionalInt(apiKeyHour),
          per_day: parseOptionalInt(apiKeyDay),
        });
        setApiKeys((current) => current.map((row) => (row.id === updated.id ? updated : row)));
        setNotice(isZh ? "API Key 已更新。" : "API key updated.");
      } else {
        const created = await createAdminApiKey(adminSecret, {
          account_id: Number(selectedAccountId),
          name: apiKeyName,
          per_minute: parseOptionalInt(apiKeyMinute),
          per_hour: parseOptionalInt(apiKeyHour),
          per_day: parseOptionalInt(apiKeyDay),
        });
        setApiKeys((current) => current.concat(created));
        setCreatedApiKey(created.api_key);
        setNotice(isZh ? "API Key 已创建。" : "API key created.");
      }
      setModal(null);
    } catch (saveError) {
      setModalError(saveError instanceof Error ? saveError.message : "request failed");
    } finally {
      setModalBusy(false);
    }
  }

  async function handleDeleteApiKey(apiKey: AdminApiKeyRecord) {
    setModalBusy(true);
    setModalError(null);
    try {
      const updated = await deleteAdminApiKey(adminSecret, apiKey.id);
      setApiKeys((current) => current.map((row) => (row.id === updated.id ? updated : row)));
      setNotice(isZh ? "API Key 已撤销。" : "API key revoked.");
      setModal(null);
    } catch (deleteError) {
      setModalError(deleteError instanceof Error ? deleteError.message : "request failed");
    } finally {
      setModalBusy(false);
    }
  }

  function buildProviderPayload() {
    return {
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
    };
  }

  async function handleSaveProvider(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setModalBusy(true);
    setModalError(null);
    try {
      if (modal?.kind === "provider-edit") {
        const updated = await updateAdminProvider(adminSecret, modal.provider.name, buildProviderPayload());
        setProviders((current) => current.map((row) => (row.id === updated.id ? updated : row)));
        setSelectedProviderName(updated.name);
        setNotice(isZh ? "Provider 已更新。" : "Provider updated.");
      } else {
        const created = await createAdminProvider(adminSecret, buildProviderPayload());
        setProviders((current) => current.concat(created));
        setSelectedProviderName(created.name);
        setNotice(isZh ? "Provider 已创建。" : "Provider created.");
      }
      await loadData();
      setModal(null);
    } catch (saveError) {
      setModalError(saveError instanceof Error ? saveError.message : "request failed");
    } finally {
      setModalBusy(false);
    }
  }

  async function handleDeleteProvider(provider: AdminProviderRecord) {
    setModalBusy(true);
    setModalError(null);
    try {
      await deleteAdminProvider(adminSecret, provider.name);
      setProviders((current) => current.filter((row) => row.id !== provider.id));
      setHealth((current) => current.filter((row) => row.name !== provider.name));
      setProviderModels((current) => {
        const next = { ...current };
        delete next[provider.name];
        return next;
      });
      if (selectedProviderName === provider.name) {
        setSelectedProviderName("");
      }
      setNotice(isZh ? "Provider 已删除。" : "Provider deleted.");
      setModal(null);
    } catch (deleteError) {
      setModalError(deleteError instanceof Error ? deleteError.message : "request failed");
    } finally {
      setModalBusy(false);
    }
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

  async function handleSaveModel(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProviderName) return;
    setModalBusy(true);
    setModalError(null);
    try {
      if (modal?.kind === "model-edit") {
        const updated = await patchAdminProviderModel(adminSecret, selectedProviderName, modal.model.native_model, {
          exposed_model_id: manualExposedModelId,
          enabled: manualModelEnabled,
        });
        setProviderModels((current) => ({
          ...current,
          [selectedProviderName]: (current[selectedProviderName] ?? []).map((row) => row.native_model === updated.native_model ? updated : row),
        }));
        setNotice(isZh ? "模型已更新。" : "Model updated.");
      } else {
        const created = await createAdminProviderModel(adminSecret, selectedProviderName, {
          native_model: manualNativeModel,
          exposed_model_id: manualExposedModelId,
          enabled: manualModelEnabled,
        });
        setProviderModels((current) => ({
          ...current,
          [selectedProviderName]: [...(Array.isArray(current[selectedProviderName]) ? current[selectedProviderName] : []), created],
        }));
        setNotice(isZh ? "模型已添加。" : "Model added.");
      }
      setModal(null);
    } catch (saveError) {
      setModalError(saveError instanceof Error ? saveError.message : "request failed");
    } finally {
      setModalBusy(false);
    }
  }

  async function handleDeleteModel(model: AdminProviderModelRecord) {
    if (!selectedProviderName) return;
    setModalBusy(true);
    setModalError(null);
    try {
      await deleteAdminProviderModel(adminSecret, selectedProviderName, model.native_model);
      setProviderModels((current) => ({
        ...current,
        [selectedProviderName]: (current[selectedProviderName] ?? []).filter((row) => row.native_model !== model.native_model),
      }));
      setNotice(isZh ? "模型已删除。" : "Model deleted.");
      setModal(null);
    } catch (deleteError) {
      setModalError(deleteError instanceof Error ? deleteError.message : "request failed");
    } finally {
      setModalBusy(false);
    }
  }

  async function handleSavePricing(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProviderName || !selectedModelNativeModel) return;
    setModalBusy(true);
    setModalError(null);
    try {
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
      setModal(null);
    } catch (saveError) {
      setModalError(saveError instanceof Error ? saveError.message : "request failed");
    } finally {
      setModalBusy(false);
    }
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
  const healthByProvider = new Map(health.map((item) => [item.name, item]));
  const chart = buildTrafficPath(timeseries);
  const totalSeriesRequests = (timeseries?.buckets ?? []).reduce((sum, bucket) => sum + bucket.total_requests, 0);
  const totalSeriesErrors = (timeseries?.buckets ?? []).reduce((sum, bucket) => sum + bucket.error_requests, 0);
  const totalSeriesLimited = (timeseries?.buckets ?? []).reduce((sum, bucket) => sum + bucket.limited_requests, 0);

  function renderModal() {
    if (!modal) return null;
    const titleByKind: Record<AdminModal["kind"], string> = {
      "provider-create": copy.providers.createTitle,
      "provider-edit": `${actionCopy.edit} ${copy.providers.title}`,
      "provider-delete": `${actionCopy.delete} ${copy.providers.title}`,
      "model-create": copy.models.manualTitle,
      "model-edit": `${actionCopy.edit} ${copy.models.title}`,
      "model-delete": `${actionCopy.delete} ${copy.models.title}`,
      "model-pricing": copy.models.pricingWorkspace,
      "model-test": copy.models.testWorkspace,
      "account-create": copy.accounts.addAccount,
      "account-edit": `${actionCopy.edit} ${copy.accounts.title}`,
      "account-delete": `${actionCopy.delete} ${copy.accounts.title}`,
      "credit-adjust": copy.accounts.adjustCredits,
      "api-key-create": copy.apiKeys.createKey,
      "api-key-edit": `${actionCopy.edit} ${copy.apiKeys.title}`,
      "api-key-delete": `${copy.apiKeys.revoke} ${copy.apiKeys.title}`,
    };

    return (
      <div className="confirm-dialog-backdrop" role="presentation">
        <div aria-modal="true" className="admin-modal" role="dialog" aria-label={titleByKind[modal.kind]}>
          <div className="admin-modal__header">
            <strong>{titleByKind[modal.kind]}</strong>
            <button className="ghost-action" onClick={closeModal} type="button">{actionCopy.close}</button>
          </div>
          {modalError ? <div className="inline-error">{modalError}</div> : null}

          {(modal.kind === "provider-create" || modal.kind === "provider-edit") ? (
            <form className="provider-form admin-modal__body" onSubmit={handleSaveProvider}>
              <label><span>{copy.providers.providerName}</span><input disabled={modal.kind === "provider-edit"} value={providerName} onChange={(event) => setProviderName(event.target.value)} /></label>
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
              <div className="admin-modal__actions">
                <button className="ghost-action" onClick={closeModal} type="button">{actionCopy.cancel}</button>
                <button className="primary-action" disabled={modalBusy || !providerName.trim()} type="submit">{actionCopy.save}</button>
              </div>
            </form>
          ) : null}

          {modal.kind === "provider-delete" ? (
            <div className="admin-modal__body">
              <p>{isZh ? `删除 Provider ${modal.provider.name}，会同时移除它的模型目录。` : `Delete provider ${modal.provider.name}. Its model catalog will also be removed.`}</p>
              <div className="admin-modal__actions">
                <button className="ghost-action" onClick={closeModal} type="button">{actionCopy.cancel}</button>
                <button className="ghost-action ghost-action--danger" disabled={modalBusy} onClick={() => void handleDeleteProvider(modal.provider)} type="button">{actionCopy.confirmDelete}</button>
              </div>
            </div>
          ) : null}

          {(modal.kind === "model-create" || modal.kind === "model-edit") ? (
            <form className="inline-form admin-modal__body" onSubmit={handleSaveModel}>
              <label><span>{copy.models.nativeModel}</span><input disabled={modal.kind === "model-edit"} value={manualNativeModel} onChange={(event) => setManualNativeModel(event.target.value)} /></label>
              <label><span>{copy.models.exposedAs}</span><input value={manualExposedModelId} onChange={(event) => setManualExposedModelId(event.target.value)} /></label>
              <label><input checked={manualModelEnabled} onChange={(event) => setManualModelEnabled(event.target.checked)} type="checkbox" /> {copy.models.enable}</label>
              <div className="admin-modal__actions">
                <button className="ghost-action" onClick={closeModal} type="button">{actionCopy.cancel}</button>
                <button className="primary-action" disabled={modalBusy || !manualNativeModel.trim() || !manualExposedModelId.trim()} type="submit">{actionCopy.save}</button>
              </div>
            </form>
          ) : null}

          {modal.kind === "model-delete" ? (
            <div className="admin-modal__body">
              <p>{isZh ? `删除模型 ${modal.model.native_model}。` : `Delete model ${modal.model.native_model}.`}</p>
              <div className="admin-modal__actions">
                <button className="ghost-action" onClick={closeModal} type="button">{actionCopy.cancel}</button>
                <button className="ghost-action ghost-action--danger" disabled={modalBusy} onClick={() => void handleDeleteModel(modal.model)} type="button">{actionCopy.confirmDelete}</button>
              </div>
            </div>
          ) : null}

          {modal.kind === "model-pricing" ? (
            <form className="inline-form admin-modal__body" onSubmit={handleSavePricing}>
              <label><span>{copy.models.inputPrice}</span><input value={pricingInput} onChange={(event) => setPricingInput(event.target.value)} /></label>
              <label><span>{copy.models.cachedInputPrice}</span><input value={pricingCachedInput} onChange={(event) => setPricingCachedInput(event.target.value)} /></label>
              <label><span>{copy.models.outputPrice}</span><input value={pricingOutput} onChange={(event) => setPricingOutput(event.target.value)} /></label>
              <label><span>{copy.models.pricingNotes}</span><input value={pricingNotes} onChange={(event) => setPricingNotes(event.target.value)} /></label>
              <div className="admin-modal__actions">
                <button className="ghost-action" onClick={closeModal} type="button">{actionCopy.cancel}</button>
                <button className="primary-action" disabled={modalBusy} type="submit">{copy.models.savePricing}</button>
              </div>
            </form>
          ) : null}

          {modal.kind === "model-test" ? (
            <div className="admin-modal__body">
              <form className="inline-form" onSubmit={handleSendModelTest}>
                <label><span>{modal.model.native_model}</span><input value={testMessage} onChange={(event) => setTestMessage(event.target.value)} /></label>
                <div className="data-table__actions">
                  <button className="primary-action" disabled={!testMessage.trim() || testChatStatus === "loading"} type="submit">{copy.models.sendTest}</button>
                  <button className="ghost-action ghost-action--bright" disabled={!testMessage.trim() || testChatStatus === "loading"} onClick={() => void handleStreamModelTest()} type="button">{copy.models.streamTest}</button>
                  <button className="ghost-action" disabled={testChatStatus !== "loading"} onClick={handleCancelStream} type="button">{copy.models.cancelStream}</button>
                </div>
              </form>
              {testChatError ? <div className="inline-error">{testChatError}</div> : null}
              <div className="admin-modal__transcript">
                {testChatMessages.length === 0 ? <div className="empty-state empty-state--compact">{copy.models.noTranscript}</div> : testChatMessages.map((message, index) => (
                  <article className="provider-row" key={`${message.role}-${index}`}>
                    <div className="provider-row__body"><strong>{message.role}</strong><p>{message.content || "..."}</p></div>
                  </article>
                ))}
              </div>
            </div>
          ) : null}

          {(modal.kind === "account-create" || modal.kind === "account-edit") ? (
            <form className="inline-form admin-modal__body" onSubmit={handleSaveAccount}>
              <label><span>{copy.accounts.accountName}</span><input value={accountName} onChange={(event) => setAccountName(event.target.value)} /></label>
              <label><span>{copy.accounts.accountEmail}</span><input value={accountEmail} onChange={(event) => setAccountEmail(event.target.value)} /></label>
              {modal.kind === "account-edit" ? <label><span>{copy.accounts.columnStatus}</span><select value={accountStatus} onChange={(event) => setAccountStatus(event.target.value)}><option value="active">active</option><option value="suspended">suspended</option><option value="deleted">deleted</option></select></label> : null}
              <label><span>{copy.accounts.accountNotes}</span><input value={accountNotes} onChange={(event) => setAccountNotes(event.target.value)} /></label>
              <label><input checked={accountIsAdmin} onChange={(event) => setAccountIsAdmin(event.target.checked)} type="checkbox" /> {copy.accounts.adminRole}</label>
              <div className="admin-modal__actions">
                <button className="ghost-action" onClick={closeModal} type="button">{actionCopy.cancel}</button>
                <button className="primary-action" disabled={modalBusy || !accountName.trim()} type="submit">{actionCopy.save}</button>
              </div>
            </form>
          ) : null}

          {modal.kind === "account-delete" ? (
            <div className="admin-modal__body">
              <p>{isZh ? `删除账户 ${modal.account.name}。这会将状态设为 deleted，不会硬删除历史流水。` : `Delete account ${modal.account.name}. This sets status to deleted and keeps historical ledger rows.`}</p>
              <div className="admin-modal__actions">
                <button className="ghost-action" onClick={closeModal} type="button">{actionCopy.cancel}</button>
                <button className="ghost-action ghost-action--danger" disabled={modalBusy} onClick={() => void handleDeleteAccount(modal.account)} type="button">{actionCopy.confirmDelete}</button>
              </div>
            </div>
          ) : null}

          {modal.kind === "credit-adjust" ? (
            <form className="inline-form admin-modal__body" onSubmit={handleAdjustCredits}>
              <label><span>{copy.apiKeys.account}</span><input disabled value={modal.account.name} /></label>
              <label><span>{copy.accounts.adjustmentAmount}</span><input value={creditAdjustment} onChange={(event) => setCreditAdjustment(event.target.value)} /></label>
              <label><span>{copy.accounts.adjustmentReason}</span><input value={creditAdjustmentReason} onChange={(event) => setCreditAdjustmentReason(event.target.value)} /></label>
              <div className="admin-modal__actions">
                <button className="ghost-action" onClick={closeModal} type="button">{actionCopy.cancel}</button>
                <button className="primary-action" disabled={modalBusy || !creditAdjustment.trim()} type="submit">{copy.accounts.applyAdjustment}</button>
              </div>
            </form>
          ) : null}

          {(modal.kind === "api-key-create" || modal.kind === "api-key-edit") ? (
            <form className="inline-form admin-modal__body" onSubmit={handleSaveApiKey}>
              <label><span>{copy.apiKeys.account}</span><select disabled={modal.kind === "api-key-edit"} value={selectedAccountId} onChange={(event) => setSelectedAccountId(event.target.value)}>{accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}</select></label>
              <label><span>{copy.apiKeys.keyName}</span><input value={apiKeyName} onChange={(event) => setApiKeyName(event.target.value)} /></label>
              {modal.kind === "api-key-edit" ? <label><span>{copy.apiKeys.columnStatus}</span><select value={apiKeyStatus} onChange={(event) => setApiKeyStatus(event.target.value)}><option value="active">active</option><option value="revoked">revoked</option></select></label> : null}
              <label><span>{copy.apiKeys.perMinute}</span><input value={apiKeyMinute} onChange={(event) => setApiKeyMinute(event.target.value)} /></label>
              <label><span>{copy.apiKeys.perHour}</span><input value={apiKeyHour} onChange={(event) => setApiKeyHour(event.target.value)} /></label>
              <label><span>{copy.apiKeys.perDay}</span><input value={apiKeyDay} onChange={(event) => setApiKeyDay(event.target.value)} /></label>
              <div className="admin-modal__actions">
                <button className="ghost-action" onClick={closeModal} type="button">{actionCopy.cancel}</button>
                <button className="primary-action" disabled={modalBusy || !selectedAccountId || !apiKeyName.trim()} type="submit">{actionCopy.save}</button>
              </div>
            </form>
          ) : null}

          {modal.kind === "api-key-delete" ? (
            <div className="admin-modal__body">
              <p>{isZh ? `撤销 API Key ${modal.apiKey.name}。` : `Revoke API key ${modal.apiKey.name}.`}</p>
              <div className="admin-modal__actions">
                <button className="ghost-action" onClick={closeModal} type="button">{actionCopy.cancel}</button>
                <button className="ghost-action ghost-action--danger" disabled={modalBusy} onClick={() => void handleDeleteApiKey(modal.apiKey)} type="button">{copy.apiKeys.revoke}</button>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    );
  }

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
          <article className="detail-panel detail-panel--wide">
            <div className="detail-panel__title-row">
              <div><h3>{copy.providers.title}</h3><p>{copy.providers.createLead}</p></div>
              <button className="primary-action" onClick={openProviderCreateModal}>{actionCopy.create}</button>
            </div>
            <div className="table-shell">
              <table className="data-table">
                <thead><tr><th>{copy.providers.providerName}</th><th>{copy.providers.routePolicy}</th><th>{copy.providers.exposedModel}</th><th>Transport</th><th>{copy.models.state}</th><th>{copy.models.action}</th></tr></thead>
                <tbody>
                  {providers.map((provider) => {
                    const healthRow = healthByProvider.get(provider.name);
                    const isHealthy = healthRow ? healthRow.capabilities.http || healthRow.capabilities.cli : false;
                    return (
                      <tr key={provider.id}>
                        <td>{provider.name}</td>
                        <td>{provider.route_policy}</td>
                        <td>{provider.exposed_model}</td>
                        <td>{[provider.http_enabled ? "HTTP" : null, provider.cli_enabled ? "CLI" : null].filter(Boolean).join(" + ") || "-"}</td>
                        <td><span className={`status-pill ${isHealthy ? "status-pill--ok" : "status-pill--warning"}`}>{isHealthy ? copy.providers.healthy : copy.providers.pending}</span></td>
                        <td className="data-table__actions">
                          <button className="ghost-action ghost-action--bright" onClick={() => { setSelectedProviderName(provider.name); setView("models"); }}>{copy.providers.openModels}</button>
                          <button className="ghost-action ghost-action--bright" onClick={() => openProviderEditModal(provider)}>{actionCopy.edit}</button>
                          <button className="ghost-action ghost-action--danger" onClick={() => openModal({ kind: "provider-delete", provider })}>{actionCopy.delete}</button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
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
                <button className="primary-action" disabled={!selectedProviderName} onClick={openModelCreateModal}>{actionCopy.create}</button>
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
                          <button className="ghost-action ghost-action--bright" onClick={() => openModelEditModal(model)}>{actionCopy.edit}</button>
                          <button className="ghost-action ghost-action--bright" onClick={() => openModelPricingModal(model)}>{actionCopy.pricing}</button>
                          <button className="ghost-action ghost-action--bright" onClick={() => openModelTestModal(model)}>{actionCopy.test}</button>
                          <button className="ghost-action ghost-action--danger" onClick={() => openModal({ kind: "model-delete", model })}>{actionCopy.delete}</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </article>
        </section>
      ) : null}

      {!loading && !error && view === "accounts" ? (
        <section className="detail-grid">
          <article className="detail-panel detail-panel--wide">
            <div className="detail-panel__title-row">
              <div><h3>{copy.accounts.title}</h3><p>{copy.permissions.lead}</p></div>
              <button className="primary-action" onClick={openAccountCreateModal}>{actionCopy.create}</button>
            </div>
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
                        <button className="ghost-action ghost-action--bright" onClick={() => openAccountEditModal(account)}>{actionCopy.edit}</button>
                        <button className="ghost-action ghost-action--bright" onClick={() => openCreditAdjustmentModal(account)}>{actionCopy.adjustCredits}</button>
                        <button className="ghost-action ghost-action--danger" onClick={() => openModal({ kind: "account-delete", account })}>{actionCopy.delete}</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>
          <article className="detail-panel detail-panel--wide">
            <h3>{copy.accounts.ledger}</h3>
            <div className="table-shell">
              <table className="data-table">
                <thead><tr><th>Delta</th><th>Type</th><th>Provider</th><th>Model</th><th>{copy.accounts.balance}</th><th>Notes</th><th>Time</th></tr></thead>
                <tbody>
                  {(creditLedger[Number(selectedAccountId)] ?? []).length === 0 ? (
                    <tr><td colSpan={7}>{copy.accounts.ledgerEmpty}</td></tr>
                  ) : (creditLedger[Number(selectedAccountId)] ?? []).map((entry) => (
                    <tr key={entry.id}>
                      <td>{`${entry.credits_delta > 0 ? "+" : ""}${entry.credits_delta}`}</td>
                      <td>{entry.entry_type}</td>
                      <td>{entry.provider_name ?? "-"}</td>
                      <td>{entry.model_id ?? "-"}</td>
                      <td>{entry.balance_after}</td>
                      <td>{entry.notes ?? "-"}</td>
                      <td>{new Date(entry.created_at).toLocaleString(isZh ? "zh-CN" : "en-US")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>
        </section>
      ) : null}

      {!loading && !error && view === "api-keys" ? (
        <section className="detail-grid">
          <article className="detail-panel detail-panel--wide">
            <div className="detail-panel__title-row">
              <div><h3>{copy.apiKeys.title}</h3><p>{actionCopy.rawKey}</p></div>
              <button className="primary-action" onClick={openApiKeyCreateModal}>{actionCopy.create}</button>
            </div>
            {createdApiKey ? <div className="secret-banner"><div><strong>{copy.apiKeys.createdKey}</strong><code>{createdApiKey}</code></div></div> : null}
            <div className="table-shell">
              <table className="data-table">
                <thead><tr><th>{copy.apiKeys.columnName}</th><th>{copy.apiKeys.columnAccountId}</th><th>{copy.apiKeys.columnPrefix}</th><th>{copy.apiKeys.perMinute}</th><th>{copy.apiKeys.perHour}</th><th>{copy.apiKeys.perDay}</th><th>{copy.apiKeys.columnStatus}</th><th>{copy.models.action}</th></tr></thead>
                <tbody>
                  {apiKeys.map((apiKey) => (
                    <tr key={apiKey.id}>
                      <td>{apiKey.name}</td>
                      <td>{apiKey.account_id}</td>
                      <td>{apiKey.key_prefix}</td>
                      <td>{apiKey.per_minute ?? "-"}</td>
                      <td>{apiKey.per_hour ?? "-"}</td>
                      <td>{apiKey.per_day ?? "-"}</td>
                      <td>{apiKey.status}</td>
                      <td className="data-table__actions">
                        <button className="ghost-action ghost-action--bright" onClick={() => openApiKeyEditModal(apiKey)}>{actionCopy.edit}</button>
                        <button className="ghost-action ghost-action--danger" onClick={() => openModal({ kind: "api-key-delete", apiKey })}>{copy.apiKeys.revoke}</button>
                      </td>
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
          <article className="detail-panel detail-panel--wide">
            <h3>{copy.usage.records}</h3>
            <div className="table-shell">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{copy.usage.time}</th>
                    <th>{copy.usage.account}</th>
                    <th>{copy.usage.apiKey}</th>
                    <th>{copy.usage.provider}</th>
                    <th>{copy.usage.model}</th>
                    <th>{copy.usage.outcome}</th>
                    <th>{`${copy.usage.tokens} in/cache/out`}</th>
                    <th>{copy.usage.credits}</th>
                    <th>{copy.usage.usd}</th>
                    <th>{copy.usage.source}</th>
                  </tr>
                </thead>
                <tbody>
                  {usageRecords.length === 0 ? (
                    <tr><td colSpan={10}>{copy.usage.empty}</td></tr>
                  ) : usageRecords.map((row) => (
                    <tr key={row.id}>
                      <td>{new Date(row.created_at).toLocaleString(isZh ? "zh-CN" : "en-US")}</td>
                      <td>{row.account_name ? `${row.account_name} #${row.account_id}` : row.account_id}</td>
                      <td>{row.api_key_name ? `${row.api_key_name} ${row.key_prefix ?? ""}` : row.api_key_id}</td>
                      <td>{row.provider_name ?? "-"}</td>
                      <td>{row.model_id ?? "-"}</td>
                      <td>{row.outcome}</td>
                      <td>{formatUsageTokens(row)}</td>
                      <td>{row.credits_charged ?? "-"}</td>
                      <td>{row.usd_amount ?? "-"}</td>
                      <td>{row.pricing_source ?? row.token_source ?? "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>
          <article className="detail-panel detail-panel--wide">
            <h3>{copy.usage.keyActivity}</h3>
            <div className="table-shell">
              <table className="data-table">
                <thead><tr><th>{copy.usage.apiKey}</th><th>{copy.usage.account}</th><th>{copy.apiKeys.columnStatus}</th><th>{copy.usage.count}</th><th>{copy.overview.rateLimitHits}</th><th>{copy.usage.time}</th></tr></thead>
                <tbody>
                  {(usage?.key_activity ?? []).length === 0 ? (
                    <tr><td colSpan={6}>{copy.usage.empty}</td></tr>
                  ) : (usage?.key_activity ?? []).map((item) => (
                    <tr key={item.api_key_id}>
                      <td>{`${item.name} ${item.key_prefix}`}</td>
                      <td>{item.account_id}</td>
                      <td>{item.status}</td>
                      <td>{item.total_requests}</td>
                      <td>{item.limited_requests}</td>
                      <td>{copy.usage.lastUsed(item.last_used_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>
          <article className="detail-panel detail-panel--wide">
            <h3>{copy.usage.providers}</h3>
            <div className="table-shell">
              <table className="data-table">
                <thead><tr><th>{copy.usage.provider}</th><th>{copy.usage.count}</th></tr></thead>
                <tbody>
                  {Object.entries(usage?.by_provider ?? {}).length === 0 ? (
                    <tr><td colSpan={2}>{copy.usage.empty}</td></tr>
                  ) : Object.entries(usage?.by_provider ?? {})
                    .sort(([, left], [, right]) => right - left)
                    .map(([name, count]) => <tr key={name}><td>{name}</td><td>{count}</td></tr>)}
                </tbody>
              </table>
            </div>
          </article>
          <article className="detail-panel detail-panel--wide">
            <h3>{copy.usage.models}</h3>
            <div className="table-shell">
              <table className="data-table">
                <thead><tr><th>{copy.usage.model}</th><th>{copy.usage.count}</th></tr></thead>
                <tbody>
                  {Object.entries(usage?.by_model ?? {}).length === 0 ? (
                    <tr><td colSpan={2}>{copy.usage.empty}</td></tr>
                  ) : Object.entries(usage?.by_model ?? {})
                    .sort(([, left], [, right]) => right - left)
                    .map(([name, count]) => <tr key={name}><td>{name}</td><td>{count}</td></tr>)}
                </tbody>
              </table>
            </div>
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
                        <button className="ghost-action ghost-action--bright" onClick={() => openAccountEditModal(account)}>{actionCopy.edit}</button>
                        <button className="ghost-action ghost-action--danger" onClick={() => openModal({ kind: "account-delete", account })}>{actionCopy.delete}</button>
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
      {renderModal()}
    </main>
  );
}
