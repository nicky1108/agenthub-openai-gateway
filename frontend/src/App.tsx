import { type FormEvent, useEffect, useRef, useState } from "react";

import {
  adjustAccountCredits,
  createAccount,
  createApiKey,
  createProviderModel,
  createProvider,
  getAccountCreditLedger,
  getAuthProviders,
  getDashboardSummary,
  getDashboardTimeseries,
  getCurrentAccount,
  getAccounts,
  getApiKeys,
  getHealth,
  getProviderModels,
  getProviders,
  getSettingsOverview,
  getUsageOverview,
  loginWithPassword,
  patchProviderModel,
  patchProviderModelPricing,
  refreshProviderPricing,
  revokeApiKey,
  rediscoverProviderModels,
  sendAdminTestChat,
  streamAdminTestChat,
  logoutSession,
  registerWithPassword,
} from "./api";
import type { Account, ApiKey, AuthAccount, CreditLedgerEntry, Provider, ProviderHealth, ProviderModel, UsageOverview } from "./api";
import type {
  AuthProviderStatus,
  DashboardTimeseries,
  ModelPricing,
  SettingsOverview,
} from "./api";
import { LOCALE_STORAGE_KEY, messages, type Locale } from "./i18n";

type DashboardSummary = Awaited<ReturnType<typeof getDashboardSummary>>;
type RouteId = "dashboard" | "providers" | "models" | "accounts" | "api-keys" | "usage" | "settings";
type DashboardWindow = "24h" | "7d";
type ModalId =
  | null
  | "add-account"
  | "adjust-credits"
  | "add-api-key"
  | "add-provider"
  | "add-manual-model";

const ROUTE_IDS: RouteId[] = ["dashboard", "providers", "models", "accounts", "api-keys", "usage", "settings"];

function getRouteFromHash(hash: string): RouteId {
  const value = hash.replace(/^#/, "");
  if (ROUTE_IDS.some((item) => item === value)) {
    return value as RouteId;
  }
  return "dashboard";
}

function aggregateUsage(
  usageSummary: UsageOverview | null,
  field: "by_provider" | "by_model",
): Array<[string, number]> {
  if (!usageSummary) {
    return [];
  }
  return Object.entries(usageSummary[field]).sort((left, right) => right[1] - left[1]);
}

function formatLastUsed(lastUsedAt: string | null, locale: Locale, noActivityLabel: string): string {
  if (!lastUsedAt) {
    return noActivityLabel;
  }

  return new Date(lastUsedAt).toLocaleString(locale === "zh" ? "zh-CN" : "en-US");
}

function formatProviderState(health: ProviderHealth | undefined, localeCopy: (typeof messages)["en"]): string {
  if (!health) {
    return localeCopy.providers.awaitingProbe;
  }
  if (health.capabilities.http || health.capabilities.cli) {
    return localeCopy.providers.healthy;
  }
  return localeCopy.providers.offline;
}

function buildTrafficPath(series: DashboardTimeseries | null): { stroke: string; fill: string; maxValue: number } {
  const buckets = series?.buckets ?? [];
  if (buckets.length === 0) {
    return { stroke: "M0 160 L600 160", fill: "M0 160 L600 160 L600 180 L0 180 Z", maxValue: 0 };
  }

  const maxValue = Math.max(...buckets.map((bucket) => bucket.total_requests), 1);
  const points = buckets.map((bucket, index) => {
    const x = buckets.length === 1 ? 0 : (index / (buckets.length - 1)) * 600;
    const y = 160 - (bucket.total_requests / maxValue) * 120;
    return `${x.toFixed(1)} ${y.toFixed(1)}`;
  });
  const stroke = `M${points[0]} ${points.slice(1).map((point) => `L${point}`).join(" ")}`;
  const fill = `${stroke} L600 180 L0 180 Z`;
  return { stroke, fill, maxValue };
}

function describeSeries(series: DashboardTimeseries | null, localeCopy: (typeof messages)["en"]): string {
  if (!series || series.buckets.length === 0) {
    return localeCopy.dashboard.noRuntimeActivity;
  }
  const busiest = [...series.buckets].sort((left, right) => right.total_requests - left.total_requests)[0];
  if (!busiest || busiest.total_requests === 0) {
    return localeCopy.dashboard.noRuntimeActivity;
  }
  return localeCopy.dashboard.peakTraffic(busiest.total_requests, busiest.label);
}

function formatUsdPerMillion(value: number | null): string {
  if (value === null) {
    return "—";
  }
  return `$${value.toFixed(2)}`;
}

function formatPricingSync(value: string, locale: Locale): string {
  return new Date(value).toLocaleString(locale === "zh" ? "zh-CN" : "en-US");
}

function formatRoutePolicyLabel(policy: string, localeCopy: (typeof messages)["en"]): string {
  switch (policy) {
    case "http-first":
      return localeCopy.providers.routePolicyHttpFirst;
    case "cli-first":
      return localeCopy.providers.routePolicyCliFirst;
    case "fixed-http":
      return localeCopy.providers.routePolicyFixedHttp;
    case "fixed-cli":
      return localeCopy.providers.routePolicyFixedCli;
    default:
      return policy;
  }
}

function formatModelSourceLabel(
  source: string,
  pricingSourceKind: string | undefined,
  locale: Locale,
): string {
  if (pricingSourceKind === "manual_override") {
    return locale === "zh" ? "手工价格覆盖" : "Manual pricing override";
  }
  if (pricingSourceKind === "official_snapshot") {
    return locale === "zh" ? "官方价格快照" : "Official pricing snapshot";
  }
  if (source === "manual_override") {
    return locale === "zh" ? "手工模型覆盖" : "Manual model override";
  }
  if (source === "bootstrap") {
    return locale === "zh" ? "内置发现" : "Bootstrap discovery";
  }
  if (source === "provider-default") {
    return locale === "zh" ? "Provider 默认模型" : "Provider default";
  }
  return source;
}

function formatLedgerEntryLabel(entryType: string, locale: Locale): string {
  if (entryType === "manual_adjustment") {
    return locale === "zh" ? "手工调整" : "Manual adjustment";
  }
  if (entryType === "model_inference") {
    return locale === "zh" ? "模型推理消费" : "Model inference";
  }
  return entryType;
}

export default function App() {
  const [locale, setLocale] = useState<Locale>(() => {
    const stored = globalThis.localStorage?.getItem(LOCALE_STORAGE_KEY);
    return stored === "zh" ? "zh" : "en";
  });
  const [authUser, setAuthUser] = useState<AuthAccount | null>(null);
  const [authState, setAuthState] = useState<"loading" | "authenticated" | "unauthenticated">("loading");
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authName, setAuthName] = useState("");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authError, setAuthError] = useState<string | null>(null);
  const [currentRoute, setCurrentRoute] = useState<RouteId>(() => getRouteFromHash(window.location.hash));

  const [accounts, setAccounts] = useState<Account[]>([]);
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [usageOverview, setUsageOverview] = useState<UsageOverview | null>(null);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [providerModels, setProviderModels] = useState<Record<string, ProviderModel[]>>({});
  const [health, setHealth] = useState<ProviderHealth[]>([]);
  const [dashboardSummary, setDashboardSummary] = useState<DashboardSummary | null>(null);
  const [dashboardWindow, setDashboardWindow] = useState<DashboardWindow>("24h");
  const [dashboardSeries, setDashboardSeries] = useState<DashboardTimeseries | null>(null);
  const [settingsOverview, setSettingsOverview] = useState<SettingsOverview | null>(null);
  const [authProviders, setAuthProviders] = useState<AuthProviderStatus>({
    email_password_enabled: true,
    github_enabled: false,
    google_enabled: false,
  });
  const [dashboardError, setDashboardError] = useState<string | null>(null);
  const [usageError, setUsageError] = useState<string | null>(null);
  const [settingsError, setSettingsError] = useState<string | null>(null);
  const [creditLedger, setCreditLedger] = useState<Record<number, CreditLedgerEntry[]>>({});

  const [accountName, setAccountName] = useState("");
  const [creditAdjustment, setCreditAdjustment] = useState("");
  const [creditAdjustmentNotes, setCreditAdjustmentNotes] = useState("");
  const [selectedAccountId, setSelectedAccountId] = useState("");
  const [apiKeyName, setApiKeyName] = useState("");
  const [createdApiKey, setCreatedApiKey] = useState<string | null>(null);
  const [keyPerMinute, setKeyPerMinute] = useState("");
  const [keyPerHour, setKeyPerHour] = useState("");
  const [keyPerDay, setKeyPerDay] = useState("");
  const [name, setName] = useState("");
  const [exposedModel, setExposedModel] = useState("default");
  const [routePolicy, setRoutePolicy] = useState("http-first");
  const [httpEnabled, setHttpEnabled] = useState(true);
  const [cliEnabled, setCliEnabled] = useState(false);
  const [httpBaseUrl, setHttpBaseUrl] = useState("");
  const [cliCommand, setCliCommand] = useState("");
  const [chatCapable, setChatCapable] = useState(true);
  const [streamCapable, setStreamCapable] = useState(true);
  const [selectedProviderName, setSelectedProviderName] = useState("");
  const [manualNativeModel, setManualNativeModel] = useState("");
  const [manualExposedModelId, setManualExposedModelId] = useState("");
  const [pricingNativeModel, setPricingNativeModel] = useState("");
  const [modelQuery, setModelQuery] = useState("");
  const [modelFilter, setModelFilter] = useState<"all" | "enabled" | "disabled">("all");
  const [exposedModelDraft, setExposedModelDraft] = useState("");
  const [pricingInput, setPricingInput] = useState("");
  const [pricingCachedInput, setPricingCachedInput] = useState("");
  const [pricingOutput, setPricingOutput] = useState("");
  const [pricingInputHigh, setPricingInputHigh] = useState("");
  const [pricingCachedInputHigh, setPricingCachedInputHigh] = useState("");
  const [pricingOutputHigh, setPricingOutputHigh] = useState("");
  const [pricingThreshold, setPricingThreshold] = useState("");
  const [pricingNotes, setPricingNotes] = useState("");
  const [testMessage, setTestMessage] = useState("");
  const [testChatMessages, setTestChatMessages] = useState<Array<{ id: string; role: "user" | "assistant"; content: string }>>([]);
  const [testChatStatus, setTestChatStatus] = useState<"idle" | "loading" | "error">("idle");
  const [testChatError, setTestChatError] = useState<string | null>(null);
  const [modelPanelStatus, setModelPanelStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [modelPanelMessage, setModelPanelMessage] = useState<string | null>(null);
  const [activeModal, setActiveModal] = useState<ModalId>(null);
  const testChatAbortRef = useRef<AbortController | null>(null);
  const copy = messages[locale];
  const NAV_ITEMS: Array<{ id: RouteId; label: string }> = [
    { id: "dashboard", label: copy.nav.dashboard },
    { id: "providers", label: copy.nav.providers },
    { id: "models", label: copy.nav.models },
    { id: "accounts", label: copy.nav.accounts },
    { id: "api-keys", label: copy.nav.apiKeys },
    { id: "usage", label: copy.nav.usage },
    { id: "settings", label: copy.nav.settings },
  ];

  useEffect(() => {
    globalThis.localStorage?.setItem(LOCALE_STORAGE_KEY, locale);
  }, [locale]);

  async function loadAuthenticatedData() {
    const [accountRows, keyRows, providerRows, healthRows, dashboard, usage, series, settingsData] = await Promise.all([
      getAccounts(),
      getApiKeys(),
      getProviders(),
      getHealth(),
      getDashboardSummary(),
      getUsageOverview(),
      getDashboardTimeseries(dashboardWindow),
      getSettingsOverview(),
    ]);

    setAccounts(accountRows);
    setApiKeys(keyRows);
    setUsageOverview(usage);
    setProviders(providerRows);
    setHealth(healthRows);
    setDashboardSummary(dashboard);
    setDashboardSeries(series);
    setDashboardError(null);
    setUsageError(null);
    setSettingsOverview(settingsData);
    setSettingsError(null);
    if (accountRows.length > 0) {
      setSelectedAccountId(String(accountRows[0].id));
      const firstAccountLedger = await getAccountCreditLedger(accountRows[0].id);
      setCreditLedger((current) => ({ ...current, [accountRows[0].id]: firstAccountLedger }));
    }
    if (providerRows.length > 0) {
      const defaultProvider = providerRows[0].name;
      setSelectedProviderName(defaultProvider);
      const models = await getProviderModels(defaultProvider);
      setProviderModels((current) => ({ ...current, [defaultProvider]: models }));
      if (models.length > 0) {
        setPricingNativeModel(models[0].native_model);
      }
    }
  }

  useEffect(() => {
    const syncRoute = () => {
      setCurrentRoute(getRouteFromHash(window.location.hash));
    };

    if (!window.location.hash) {
      window.location.hash = "#dashboard";
      syncRoute();
    }

    window.addEventListener("hashchange", syncRoute);
    return () => window.removeEventListener("hashchange", syncRoute);
  }, []);

  useEffect(() => {
    void getAuthProviders()
      .then((providers) => setAuthProviders(providers))
      .catch(() =>
        setAuthProviders({
          email_password_enabled: true,
          github_enabled: false,
          google_enabled: false,
        }),
      );
  }, []);

  useEffect(() => {
    void getCurrentAccount()
      .then(async (account) => {
        setAuthUser(account);
        setAuthState("authenticated");
        setAuthError(null);
        await loadAuthenticatedData();
      })
      .catch(() => {
        setAuthUser(null);
        setAuthState("unauthenticated");
      });
  }, []);

  useEffect(() => {
    if (providers.length === 0) {
      if (selectedProviderName !== "") {
        setSelectedProviderName("");
      }
      return;
    }

    const currentStillExists = providers.some((provider) => provider.name === selectedProviderName);
    if (!currentStillExists) {
      setSelectedProviderName(providers[0].name);
    }
  }, [providers, selectedProviderName]);

  useEffect(() => {
    if (!selectedProviderName) return;
    const selectedModel = (providerModels[selectedProviderName] ?? []).find((row) => row.native_model === pricingNativeModel);
    if (!selectedModel) return;
    setExposedModelDraft(selectedModel.exposed_model_id);
    setPricingInput(selectedModel.pricing?.input_price?.toString() ?? "");
    setPricingCachedInput(selectedModel.pricing?.cached_input_price?.toString() ?? "");
    setPricingOutput(selectedModel.pricing?.output_price?.toString() ?? "");
    setPricingInputHigh(selectedModel.pricing?.input_price_high?.toString() ?? "");
    setPricingCachedInputHigh(selectedModel.pricing?.cached_input_price_high?.toString() ?? "");
    setPricingOutputHigh(selectedModel.pricing?.output_price_high?.toString() ?? "");
    setPricingThreshold(selectedModel.pricing?.high_price_threshold_tokens?.toString() ?? "");
    setPricingNotes(selectedModel.pricing?.notes ?? "");
  }, [pricingNativeModel, providerModels, selectedProviderName]);

  useEffect(() => {
    setTestChatMessages([]);
    setTestMessage("");
    setTestChatStatus("idle");
    setTestChatError(null);
    setModelPanelStatus("idle");
    setModelPanelMessage(null);
    testChatAbortRef.current?.abort();
    testChatAbortRef.current = null;
  }, [selectedProviderName, pricingNativeModel]);

  useEffect(() => {
    if (!selectedAccountId) {
      return;
    }
    const accountId = Number(selectedAccountId);
    if (creditLedger[accountId]) {
      return;
    }
    void getAccountCreditLedger(accountId).then((ledger) => {
      setCreditLedger((current) => ({ ...current, [accountId]: ledger }));
    });
  }, [selectedAccountId, creditLedger]);

  useEffect(() => {
    if (authState !== "authenticated") {
      return;
    }
    void getDashboardTimeseries(dashboardWindow)
      .then((series) => {
        setDashboardSeries(series);
        setDashboardError(null);
      })
      .catch((error: unknown) => {
        setDashboardError(error instanceof Error ? error.message : "dashboard unavailable");
      });
  }, [authState, dashboardWindow]);

  async function handleAccountSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const created = await createAccount({ name: accountName });
    setAccounts((current) => current.concat(created));
    setSelectedAccountId(String(created.id));
    setAccountName("");
    setCreditLedger((current) => ({ ...current, [created.id]: [] }));
  }

  async function handleCreditAdjustmentSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const adjusted = await adjustAccountCredits(Number(selectedAccountId), {
      credits_delta: Number(creditAdjustment),
      notes: creditAdjustmentNotes || null,
    });
    setAccounts((current) => current.map((row) => (row.id === adjusted.id ? adjusted : row)));
    const ledger = await getAccountCreditLedger(adjusted.id);
    setCreditLedger((current) => ({ ...current, [adjusted.id]: ledger }));
    setCreditAdjustment("");
    setCreditAdjustmentNotes("");
  }

  async function handleApiKeySubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const created = await createApiKey({
      account_id: Number(selectedAccountId),
      name: apiKeyName,
      per_minute: keyPerMinute ? Number(keyPerMinute) : null,
      per_hour: keyPerHour ? Number(keyPerHour) : null,
      per_day: keyPerDay ? Number(keyPerDay) : null,
    });
    setApiKeys((current) => current.concat(created));
    setUsageOverview((current) => ({
      key_activity: [
        ...(current?.key_activity ?? []),
        {
          api_key_id: created.id,
          account_id: created.account_id,
          name: created.name,
          key_prefix: created.key_prefix,
          status: created.status,
          last_used_at: created.last_used_at,
          total_requests: 0,
          limited_requests: 0,
        },
      ],
      by_provider: current?.by_provider ?? {},
      by_model: current?.by_model ?? {},
    }));
    setCreatedApiKey(created.api_key);
    setApiKeyName("");
    setKeyPerMinute("");
    setKeyPerHour("");
    setKeyPerDay("");
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const created = await createProvider({
      name,
      exposed_model: exposedModel,
      route_policy: routePolicy,
      http_enabled: httpEnabled,
      cli_enabled: cliEnabled,
      chat_capable: chatCapable,
      stream_capable: streamCapable,
      http_base_url: httpEnabled ? httpBaseUrl : null,
      http_headers_json: "{}",
      cli_command: cliEnabled ? cliCommand : null,
      cli_args_json: "[]",
      cli_env_json: "{}",
    });
    setProviders((current) => current.concat(created));
    setSelectedProviderName(created.name);
    setName("");
    setExposedModel("default");
    setRoutePolicy("http-first");
    setHttpEnabled(true);
    setCliEnabled(false);
    setHttpBaseUrl("");
    setCliCommand("");
    setChatCapable(true);
    setStreamCapable(true);
    const models = await getProviderModels(created.name);
    setProviderModels((current) => ({ ...current, [created.name]: models }));
  }

  async function loadSelectedProviderModels(providerName: string) {
    const rows = await getProviderModels(providerName);
    setProviderModels((current) => ({ ...current, [providerName]: rows }));
    if (rows.length > 0) {
      setPricingNativeModel(rows[0].native_model);
    }
  }

  async function handleSelectProvider(providerName: string) {
    setSelectedProviderName(providerName);
    if (!providerModels[providerName]) {
      await loadSelectedProviderModels(providerName);
    }
  }

  async function handleRediscoverModels(providerNameOverride?: string) {
    const providerName = providerNameOverride ?? selectedProviderName;
    if (!providerName) return;
    const rows = await rediscoverProviderModels(providerName);
    setProviderModels((current) => ({ ...current, [providerName]: rows }));
    if (rows.length > 0) {
      setPricingNativeModel(rows[0].native_model);
    }
  }

  async function handleRefreshPricing() {
    if (!selectedProviderName) return;
    const rows = await refreshProviderPricing(selectedProviderName);
    setProviderModels((current) => ({ ...current, [selectedProviderName]: rows }));
  }

  async function handleSaveExposedModelId(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProviderName || !pricingNativeModel) return;
    setModelPanelStatus("saving");
    setModelPanelMessage(null);
    try {
      const updated = await patchProviderModel(selectedProviderName, pricingNativeModel, {
        exposed_model_id: exposedModelDraft,
      });
      setProviderModels((current) => ({
        ...current,
        [selectedProviderName]: (current[selectedProviderName] ?? []).map((row) =>
          row.native_model === pricingNativeModel ? updated : row,
        ),
      }));
      setModelPanelStatus("saved");
      setModelPanelMessage(copy.models.saved);
    } catch (error: unknown) {
      setModelPanelStatus("error");
      setModelPanelMessage(error instanceof Error ? error.message : copy.models.testFailed);
    }
  }

  async function handlePricingOverrideSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProviderName || !pricingNativeModel) return;
    setModelPanelStatus("saving");
    setModelPanelMessage(null);
    try {
      const pricing = await patchProviderModelPricing(selectedProviderName, pricingNativeModel, {
        input_price: pricingInput ? Number(pricingInput) : null,
        cached_input_price: pricingCachedInput ? Number(pricingCachedInput) : null,
        output_price: pricingOutput ? Number(pricingOutput) : null,
        input_price_high: pricingInputHigh ? Number(pricingInputHigh) : null,
        cached_input_price_high: pricingCachedInputHigh ? Number(pricingCachedInputHigh) : null,
        output_price_high: pricingOutputHigh ? Number(pricingOutputHigh) : null,
        high_price_threshold_tokens: pricingThreshold ? Number(pricingThreshold) : null,
        notes: pricingNotes || null,
      });
      setProviderModels((current) => ({
        ...current,
        [selectedProviderName]: (current[selectedProviderName] ?? []).map((row) =>
          row.native_model === pricingNativeModel ? { ...row, pricing } : row,
        ),
      }));
      setModelPanelStatus("saved");
      setModelPanelMessage(copy.models.saved);
    } catch (error: unknown) {
      setModelPanelStatus("error");
      setModelPanelMessage(error instanceof Error ? error.message : copy.models.testFailed);
    }
  }

  async function handleModelTestSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProviderName || !pricingNativeModel || !testMessage.trim()) return;
    const userContent = testMessage.trim();
    setTestChatStatus("loading");
    setTestChatError(null);
    setTestChatMessages((current) => [...current, { id: `user-${Date.now()}`, role: "user", content: userContent }]);
    setTestMessage("");
    try {
      const response = await sendAdminTestChat({
        model: `${selectedProviderName}:${pricingNativeModel}`,
        messages: [{ role: "user", content: userContent }],
      });
      const assistantContent = response.choices[0]?.message?.content?.trim() || copy.models.emptyResponse;
      setTestChatMessages((current) => [...current, { id: `assistant-${Date.now()}`, role: "assistant", content: assistantContent }]);
      setTestChatStatus("idle");
    } catch (error: unknown) {
      setTestChatStatus("error");
      setTestChatError(error instanceof Error ? error.message : copy.models.testFailed);
    }
  }

  async function handleModelTestStream() {
    if (!selectedProviderName || !pricingNativeModel || !testMessage.trim() || testChatStatus === "loading") return;
    const userContent = testMessage.trim();
    const assistantMessageId = `assistant-${Date.now()}`;
    testChatAbortRef.current?.abort();
    const controller = new AbortController();
    testChatAbortRef.current = controller;
    setTestChatStatus("loading");
    setTestChatError(null);
    setTestChatMessages((current) => [
      ...current,
      { id: `user-${Date.now()}`, role: "user", content: userContent },
      { id: assistantMessageId, role: "assistant", content: "" },
    ]);
    setTestMessage("");

    try {
      await streamAdminTestChat(
        {
          model: `${selectedProviderName}:${pricingNativeModel}`,
          messages: [{ role: "user", content: userContent }],
        },
        {
          signal: controller.signal,
          onChunk: (chunk) => {
            const delta = chunk.choices?.[0]?.delta?.content ?? "";
            if (!delta) return;
            setTestChatMessages((current) =>
              current.map((message) =>
                message.id === assistantMessageId
                  ? { ...message, content: `${message.content}${delta}` }
                  : message,
              ),
            );
          },
        },
      );
      setTestChatMessages((current) =>
        current.map((message) =>
          message.id === assistantMessageId && !message.content
            ? { ...message, content: copy.models.emptyResponse }
            : message,
        ),
      );
      setTestChatStatus("idle");
      testChatAbortRef.current = null;
    } catch (error: unknown) {
      if (error instanceof DOMException && error.name === "AbortError") {
        setTestChatStatus("idle");
        setTestChatError(copy.models.testCancelled);
        testChatAbortRef.current = null;
        return;
      }
      setTestChatStatus("error");
      setTestChatError(error instanceof Error ? error.message : copy.models.testFailed);
      testChatAbortRef.current = null;
    }
  }

  function handleCancelModelStream() {
    testChatAbortRef.current?.abort();
    testChatAbortRef.current = null;
  }

  async function handleOpenProviderModels(providerName: string) {
    setSelectedProviderName(providerName);
    await loadSelectedProviderModels(providerName);
    window.location.hash = "#models";
    setCurrentRoute("models");
  }

  async function handleToggleProviderModel(nativeModel: string, enabled: boolean) {
    if (!selectedProviderName) return;
    setModelPanelStatus("saving");
    setModelPanelMessage(null);
    try {
      const updated = await patchProviderModel(selectedProviderName, nativeModel, { enabled: !enabled });
      setProviderModels((current) => ({
        ...current,
        [selectedProviderName]: (current[selectedProviderName] ?? []).map((row) =>
          row.native_model === nativeModel ? updated : row,
        ),
      }));
      setModelPanelStatus("saved");
      setModelPanelMessage(copy.models.saved);
    } catch (error: unknown) {
      setModelPanelStatus("error");
      setModelPanelMessage(error instanceof Error ? error.message : copy.models.testFailed);
    }
  }

  async function handleManualModelSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProviderName) return;
    const created = await createProviderModel(selectedProviderName, {
      native_model: manualNativeModel,
      exposed_model_id: manualExposedModelId,
      enabled: true,
    });
    setProviderModels((current) => ({
      ...current,
      [selectedProviderName]: [...(current[selectedProviderName] ?? []), created],
    }));
    setManualNativeModel("");
    setManualExposedModelId("");
  }

  async function handleRevokeKey(keyId: number) {
    const revoked = await revokeApiKey(keyId);
    setApiKeys((current) => current.map((row) => (row.id === keyId ? revoked : row)));
  }

  async function handleAuthSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      const account =
        authMode === "login"
          ? await loginWithPassword({ email: authEmail, password: authPassword })
          : await registerWithPassword({ name: authName, email: authEmail, password: authPassword });
      setAuthUser(account);
      setAuthState("authenticated");
      setAuthError(null);
      if (authMode === "register") {
        const loginAccount = await loginWithPassword({ email: authEmail, password: authPassword });
        setAuthUser(loginAccount);
      }
      await loadAuthenticatedData();
      setAuthPassword("");
      setCurrentRoute(getRouteFromHash(window.location.hash));
    } catch (error: unknown) {
      setAuthError(error instanceof Error ? error.message : "authentication failed");
    }
  }

  async function handleLogout() {
    await logoutSession();
    setAuthUser(null);
    setAuthState("unauthenticated");
    setAccounts([]);
    setApiKeys([]);
    setUsageOverview(null);
    setProviders([]);
    setHealth([]);
    setDashboardSummary(null);
    setDashboardSeries(null);
    setSettingsOverview(null);
  }

  const recentKeyActivity = [...(usageOverview?.key_activity ?? [])].sort((left, right) => {
    const leftTime = left.last_used_at ? new Date(left.last_used_at).getTime() : 0;
    const rightTime = right.last_used_at ? new Date(right.last_used_at).getTime() : 0;
    return rightTime - leftTime || right.total_requests - left.total_requests;
  });
  const providerActivity = aggregateUsage(usageOverview, "by_provider").slice(0, 5);
  const modelActivity = aggregateUsage(usageOverview, "by_model").slice(0, 5);
  const selectedProviderModels = selectedProviderName ? (providerModels[selectedProviderName] ?? []) : [];
  const visibleProviderModels = selectedProviderModels.filter((model) => {
    const matchesQuery =
      modelQuery.trim().length === 0 ||
      model.native_model.toLowerCase().includes(modelQuery.toLowerCase()) ||
      model.exposed_model_id.toLowerCase().includes(modelQuery.toLowerCase());
    const matchesFilter =
      modelFilter === "all" ||
      (modelFilter === "enabled" && model.enabled) ||
      (modelFilter === "disabled" && !model.enabled);
    return matchesQuery && matchesFilter;
  });
  const selectedModel = selectedProviderModels.find((row) => row.native_model === pricingNativeModel) ?? null;
  const providerHealthByName = new Map(health.map((entry) => [entry.name, entry]));
  const selectedProviderRecord = providers.find((provider) => provider.name === selectedProviderName) ?? null;
  const selectedProviderHealth = selectedProviderRecord ? providerHealthByName.get(selectedProviderRecord.name) : undefined;
  const totalProviders = providers.length;
  const httpProviders = providers.filter((provider) => provider.http_enabled).length;
  const cliProviders = providers.filter((provider) => provider.cli_enabled).length;
  const streamingProviders = providers.filter((provider) => provider.stream_capable).length;
  const chart = buildTrafficPath(dashboardSeries);
  const totalSeriesRequests = (dashboardSeries?.buckets ?? []).reduce((sum, bucket) => sum + bucket.total_requests, 0);
  const totalSeriesErrors = (dashboardSeries?.buckets ?? []).reduce((sum, bucket) => sum + bucket.error_requests, 0);
  const totalSeriesLimited = (dashboardSeries?.buckets ?? []).reduce((sum, bucket) => sum + bucket.limited_requests, 0);
  const activeAccounts = accounts.filter((account) => account.status === "active").length;
  const accountsWithNotes = accounts.filter((account) => Boolean(account.notes)).length;
  const totalCredits = accounts.reduce((sum, account) => sum + account.credit_balance, 0);
  const activeApiKeys = apiKeys.filter((apiKey) => apiKey.status === "active").length;
  const revokedApiKeys = apiKeys.filter((apiKey) => apiKey.status === "revoked").length;
  const quotaConfiguredKeys = apiKeys.filter(
    (apiKey) => apiKey.per_minute !== null || apiKey.per_hour !== null || apiKey.per_day !== null,
  ).length;
  const selectedAccountLedger = selectedAccountId ? (creditLedger[Number(selectedAccountId)] ?? []) : [];

  function renderAccountSelector() {
    return (
      <div className="provider-selector">
        <span className="provider-selector-label">{copy.apiKeys.account}</span>
        <div className="provider-selector-grid" role="tablist" aria-label={copy.apiKeys.account}>
          {accounts.map((account) => (
            <button
              key={account.id}
              type="button"
              role="tab"
              aria-selected={selectedAccountId === String(account.id)}
              className={
                selectedAccountId === String(account.id)
                  ? "provider-selector-pill provider-selector-pill--active"
                  : "provider-selector-pill"
              }
              onClick={() => setSelectedAccountId(String(account.id))}
            >
              {account.name}
            </button>
          ))}
        </div>
      </div>
    );
  }

  function renderRoutePolicySelector() {
    return (
      <div className="provider-selector">
        <span className="provider-selector-label">{copy.providers.routePolicy}</span>
        <div className="provider-selector-grid" role="tablist" aria-label={copy.providers.routePolicy}>
              {["http-first", "cli-first", "fixed-http", "fixed-cli"].map((policy) => (
                <button
              key={policy}
              type="button"
              role="tab"
              aria-selected={routePolicy === policy}
              className={routePolicy === policy ? "provider-selector-pill provider-selector-pill--active" : "provider-selector-pill"}
              onClick={() => setRoutePolicy(policy)}
            >
              {formatRoutePolicyLabel(policy, copy)}
            </button>
          ))}
        </div>
      </div>
    );
  }

  function renderModal() {
    if (!activeModal) {
      return null;
    }

    let title = "";
    let body: JSX.Element | null = null;

    if (activeModal === "add-account") {
      title = copy.accounts.addAccount;
      body = (
        <form onSubmit={handleAccountSubmit} className="modal-form">
          <label>
            {copy.accounts.accountName}
            <input value={accountName} onChange={(event) => setAccountName(event.target.value)} />
          </label>
          <div className="modal-actions">
            <button type="button" onClick={() => setActiveModal(null)}>{copy.common.cancel}</button>
            <button type="submit">{copy.accounts.addAccount}</button>
          </div>
        </form>
      );
    } else if (activeModal === "adjust-credits") {
      title = copy.accounts.applyCreditAdjustment;
      body = (
        <form onSubmit={handleCreditAdjustmentSubmit} className="modal-form">
          {renderAccountSelector()}
          <label>
            {copy.accounts.creditDelta}
            <input value={creditAdjustment} onChange={(event) => setCreditAdjustment(event.target.value)} />
          </label>
          <label>
            {copy.accounts.adjustmentNotes}
            <input value={creditAdjustmentNotes} onChange={(event) => setCreditAdjustmentNotes(event.target.value)} />
          </label>
          <div className="modal-actions">
            <button type="button" onClick={() => setActiveModal(null)}>{copy.common.cancel}</button>
            <button type="submit">{copy.accounts.applyCreditAdjustment}</button>
          </div>
        </form>
      );
    } else if (activeModal === "add-api-key") {
      title = copy.apiKeys.createKey;
      body = (
        <form onSubmit={handleApiKeySubmit} className="modal-form">
          {renderAccountSelector()}
          <label>
            {copy.apiKeys.keyName}
            <input value={apiKeyName} onChange={(event) => setApiKeyName(event.target.value)} />
          </label>
          <label>
            {copy.apiKeys.perMinute}
            <input value={keyPerMinute} onChange={(event) => setKeyPerMinute(event.target.value)} />
          </label>
          <label>
            {copy.apiKeys.perHour}
            <input value={keyPerHour} onChange={(event) => setKeyPerHour(event.target.value)} />
          </label>
          <label>
            {copy.apiKeys.perDay}
            <input value={keyPerDay} onChange={(event) => setKeyPerDay(event.target.value)} />
          </label>
          <div className="modal-actions">
            <button type="button" onClick={() => setActiveModal(null)}>{copy.common.cancel}</button>
            <button type="submit">{copy.apiKeys.createKey}</button>
          </div>
        </form>
      );
    } else if (activeModal === "add-provider") {
      title = copy.providers.addProvider;
      body = (
        <form onSubmit={handleSubmit} className="modal-form">
          <label>
            {copy.providers.providerName}
            <input value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <label>
            {copy.providers.exposedModel}
            <input value={exposedModel} onChange={(event) => setExposedModel(event.target.value)} />
          </label>
          {renderRoutePolicySelector()}
          <label className="checkbox-field">
            <span>{copy.providers.httpEnabled}</span>
            <input type="checkbox" checked={httpEnabled} onChange={(event) => setHttpEnabled(event.target.checked)} />
          </label>
          <label className="checkbox-field">
            <span>{copy.providers.cliEnabled}</span>
            <input type="checkbox" checked={cliEnabled} onChange={(event) => setCliEnabled(event.target.checked)} />
          </label>
          <label>
            {copy.providers.httpBaseUrl}
            <input required={httpEnabled} value={httpBaseUrl} onChange={(event) => setHttpBaseUrl(event.target.value)} />
          </label>
          <label>
            {copy.providers.cliCommand}
            <input required={cliEnabled} value={cliCommand} onChange={(event) => setCliCommand(event.target.value)} />
          </label>
          <label className="checkbox-field">
            <span>{copy.providers.chatCapable}</span>
            <input type="checkbox" checked={chatCapable} onChange={(event) => setChatCapable(event.target.checked)} />
          </label>
          <label className="checkbox-field">
            <span>{copy.providers.streamCapable}</span>
            <input type="checkbox" checked={streamCapable} onChange={(event) => setStreamCapable(event.target.checked)} />
          </label>
          <div className="modal-actions">
            <button type="button" onClick={() => setActiveModal(null)}>{copy.common.cancel}</button>
            <button type="submit">{copy.providers.addProvider}</button>
          </div>
        </form>
      );
    } else if (activeModal === "add-manual-model") {
      title = copy.models.addManualModel;
      body = (
        <form onSubmit={handleManualModelSubmit} className="modal-form">
          <label>
            {copy.models.nativeModel}
            <input value={manualNativeModel} onChange={(event) => setManualNativeModel(event.target.value)} />
          </label>
          <label>
            {copy.models.exposedModelId}
            <input value={manualExposedModelId} onChange={(event) => setManualExposedModelId(event.target.value)} />
          </label>
          <div className="modal-actions">
            <button type="button" onClick={() => setActiveModal(null)}>{copy.common.cancel}</button>
            <button type="submit">{copy.models.addManualModel}</button>
          </div>
        </form>
      );
    }

    return (
      <div className="modal-backdrop" onClick={() => setActiveModal(null)}>
        <div className="modal-card" onClick={(event) => event.stopPropagation()}>
          <div className="modal-header">
            <h3>{title}</h3>
            <button type="button" onClick={() => setActiveModal(null)}>{copy.common.close}</button>
          </div>
          {body}
        </div>
      </div>
    );
  }

  function renderCurrentPage() {
    switch (currentRoute) {
      case "dashboard":
        return (
          <section id="dashboard" className="dashboard">
            <div className="section-header">
              <div>
                <span className="section-eyebrow">{copy.dashboard.overview}</span>
                <h2>{copy.dashboard.platformOverview}</h2>
              </div>
              <div className="status-pill">{dashboardWindow} {copy.common.defaultLabel}</div>
            </div>
            {dashboardError ? <p role="alert">{copy.nav.dashboard}: {dashboardError}</p> : null}
            <div className="kpi-grid">
              <div className="kpi-card">
                <strong>{copy.dashboard.requests}</strong>
                <span className="kpi-subtitle">{copy.dashboard.requestsSubtitle}</span>
                <div>{dashboardSummary?.total_requests ?? "—"}</div>
              </div>
              <div className="kpi-card">
                <strong>{copy.dashboard.activeKeys}</strong>
                <span className="kpi-subtitle">{copy.dashboard.activeKeysSubtitle}</span>
                <div>{dashboardSummary?.active_api_keys ?? "—"}</div>
              </div>
              <div className="kpi-card">
                <strong>{copy.dashboard.errorRate}</strong>
                <span className="kpi-subtitle">{copy.dashboard.errorRateSubtitle}</span>
                <div>{dashboardSummary ? `${(dashboardSummary.error_rate * 100).toFixed(1)}%` : "—"}</div>
              </div>
              <div className="kpi-card">
                <strong>{copy.dashboard.rateLimitHits}</strong>
                <span className="kpi-subtitle">{copy.dashboard.rateLimitHitsSubtitle}</span>
                <div>{dashboardSummary?.rate_limit_hits ?? "—"}</div>
              </div>
            </div>
            <div className="hero-chart">
              <div className="chart-header">
                <div>
                  <strong>{copy.dashboard.traffic}</strong>
                  <p>{describeSeries(dashboardSeries, copy)}</p>
                </div>
                <div className="chart-toggle">
                  <button
                    type="button"
                    className={dashboardWindow === "24h" ? "chart-toggle-active" : undefined}
                    onClick={() => setDashboardWindow("24h")}
                  >
                    24h
                  </button>
                  <button
                    type="button"
                    className={dashboardWindow === "7d" ? "chart-toggle-active" : undefined}
                    onClick={() => setDashboardWindow("7d")}
                  >
                    7d
                  </button>
                </div>
              </div>
              <svg viewBox="0 0 600 180" className="chart-svg" aria-hidden="true">
                <defs>
                  <linearGradient id="traffic-fill" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor="rgba(102,210,255,0.35)" />
                    <stop offset="100%" stopColor="rgba(102,210,255,0)" />
                  </linearGradient>
                </defs>
                <path
                  d={chart.stroke}
                  fill="none"
                  stroke="rgba(102,210,255,0.96)"
                  strokeWidth="4"
                  strokeLinecap="round"
                />
                <path
                  d={chart.fill}
                  fill="url(#traffic-fill)"
                />
              </svg>
              <div className="chart-footer">
                <span>{copy.dashboard.requestsInWindow(totalSeriesRequests)}</span>
                <span>{copy.dashboard.errorCount(totalSeriesErrors)}</span>
                <span>{copy.dashboard.limitedCount(totalSeriesLimited)}</span>
              </div>
            </div>
          </section>
        );
      case "accounts":
        return (
          <section id="accounts">
            <div className="section-header">
              <div>
                <span className="section-eyebrow">{copy.accounts.eyebrow}</span>
                <h2>{copy.accounts.title}</h2>
              </div>
              <div className="inline-actions">
                <button type="button" onClick={() => setActiveModal("add-account")}>{copy.accounts.addAccount}</button>
                <button type="button" onClick={() => setActiveModal("adjust-credits")}>{copy.accounts.applyCreditAdjustment}</button>
              </div>
            </div>
            <div className="provider-summary-grid">
              <article className="provider-summary-card">
                <span className="provider-summary-label">{copy.accounts.totalAccounts}</span>
                <strong>{accounts.length}</strong>
                <p>{copy.accounts.empty}</p>
              </article>
              <article className="provider-summary-card">
                <span className="provider-summary-label">{copy.accounts.activeAccounts}</span>
                <strong>{activeAccounts}</strong>
                <p>{copy.accounts.activeOnly}</p>
              </article>
              <article className="provider-summary-card">
                <span className="provider-summary-label">{copy.accounts.pendingNotes}</span>
                <strong>{accountsWithNotes}</strong>
                <p>{copy.accounts.noteCount(accountsWithNotes)}</p>
              </article>
              <article className="provider-summary-card">
                <span className="provider-summary-label">{copy.accounts.credits}</span>
                <strong>{totalCredits}</strong>
                <p>{selectedAccountId ? copy.accounts.selectedBalance(accounts.find((row) => String(row.id) === selectedAccountId)?.credit_balance ?? 0) : copy.common.noData}</p>
              </article>
            </div>
            <ul>
              {accounts.length === 0 ? <li>{copy.accounts.empty}</li> : accounts.map((account) => (
                <li key={account.id}>
                  <strong>{account.name}</strong>
                  <div className="usage-meta">{account.status === "active" ? copy.common.enabled : account.status} · {account.credit_balance} {copy.accounts.credits}</div>
                  {account.notes ? <div className="usage-meta">{account.notes}</div> : null}
                </li>
              ))}
            </ul>
            <ul>
              {selectedAccountLedger.length === 0 ? (
                <li>{copy.accounts.ledgerEmpty}</li>
              ) : (
                selectedAccountLedger.map((entry) => (
                  <li key={entry.id}>
                    <strong>{formatLedgerEntryLabel(entry.entry_type, locale)}</strong>
                    <div className="usage-meta">
                      {entry.credits_delta} {copy.accounts.credits} · {copy.accounts.balanceAfter(entry.balance_after)}
                    </div>
                    {entry.model_id ? <div className="usage-meta">{entry.model_id}</div> : null}
                    {entry.notes ? <div className="usage-meta">{entry.notes}</div> : null}
                  </li>
                ))
              )}
            </ul>
          </section>
        );
      case "api-keys":
        return (
          <section id="api-keys">
            <div className="section-header">
              <div>
                <span className="section-eyebrow">{copy.apiKeys.eyebrow}</span>
                <h2>{copy.apiKeys.title}</h2>
              </div>
              <button type="button" onClick={() => setActiveModal("add-api-key")}>{copy.apiKeys.createKey}</button>
            </div>
            <div className="provider-summary-grid">
              <article className="provider-summary-card">
                <span className="provider-summary-label">{copy.apiKeys.activeKeys}</span>
                <strong>{activeApiKeys}</strong>
                <p>{copy.apiKeys.quotaCoverageValue(activeApiKeys, apiKeys.length)}</p>
              </article>
              <article className="provider-summary-card">
                <span className="provider-summary-label">{copy.apiKeys.revokedKeys}</span>
                <strong>{revokedApiKeys}</strong>
                <p>{revokedApiKeys === 0 ? copy.common.noData : copy.apiKeys.quotaCoverageValue(revokedApiKeys, apiKeys.length)}</p>
              </article>
              <article className="provider-summary-card">
                <span className="provider-summary-label">{copy.apiKeys.quotaCoverage}</span>
                <strong>{quotaConfiguredKeys}</strong>
                <p>{copy.apiKeys.quotaCoverageValue(quotaConfiguredKeys, apiKeys.length)}</p>
              </article>
            </div>
            {createdApiKey ? <p>{copy.apiKeys.lastCreatedKey}: {createdApiKey}</p> : null}
            <ul>
              {apiKeys.length === 0 ? <li>{copy.apiKeys.noKeys}</li> : apiKeys.map((apiKey) => (
                <li key={apiKey.id}>
                  <strong>{apiKey.name}</strong>
                  <div className="usage-meta">{apiKey.key_prefix} · {apiKey.status}</div>
                  <div className="usage-meta">
                    {apiKey.per_minute ?? "—"}/{copy.apiKeys.requestsPerMin} · {apiKey.per_hour ?? "—"}/{copy.apiKeys.requestsPerHour} · {apiKey.per_day ?? "—"}/{copy.apiKeys.requestsPerDay}
                  </div>
                  <button type="button" onClick={() => handleRevokeKey(apiKey.id)}>
                    {copy.common.revoke}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        );
      case "providers":
        return (
          <section id="providers" className="providers-page">
            <div className="section-header">
              <div>
                <span className="section-eyebrow">{copy.providers.eyebrow}</span>
                <h2>{copy.providers.title}</h2>
                <p>{copy.providers.description}</p>
              </div>
              <button type="button" onClick={() => setActiveModal("add-provider")}>{copy.providers.addProvider}</button>
            </div>
            <div className="provider-summary-grid">
              <article className="provider-summary-card">
                <span className="provider-summary-label">{copy.providers.runtimeCoverage}</span>
                <strong>{totalProviders}</strong>
                <p>{copy.providers.runtimeCoverageDescription}</p>
              </article>
              <article className="provider-summary-card">
                <span className="provider-summary-label">{copy.providers.httpTransport}</span>
                <strong>{httpProviders}</strong>
                <p>{copy.providers.httpTransportDescription}</p>
              </article>
              <article className="provider-summary-card">
                <span className="provider-summary-label">{copy.providers.cliRuntimes}</span>
                <strong>{cliProviders}</strong>
                <p>{copy.providers.cliRuntimesDescription}</p>
              </article>
              <article className="provider-summary-card">
                <span className="provider-summary-label">{copy.providers.streamingReady}</span>
                <strong>{streamingProviders}</strong>
                <p>{copy.providers.streamingReadyDescription}</p>
              </article>
            </div>
            <div className="provider-layout">
              <div className="provider-panel provider-registry-panel">
                <div className="provider-panel-header">
                  <div>
                    <span className="section-eyebrow">{copy.providers.registry}</span>
                    <h3>{copy.providers.activeProviders}</h3>
                    <p>Route-ready providers with transport and capability context.</p>
                  </div>
                </div>
                <div className="provider-card-grid">
                  {providers.map((provider) => {
                    const providerHealth = providerHealthByName.get(provider.name);
                    const providerModelsCount = providerModels[provider.name]?.length ?? null;

                    return (
                      <article
                        key={provider.id}
                        className={selectedProviderName === provider.name ? "provider-card provider-card--active" : "provider-card"}
                        role="button"
                        tabIndex={0}
                        onClick={() => void handleSelectProvider(provider.name)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            void handleSelectProvider(provider.name);
                          }
                        }}
                      >
                        <div className="provider-card-topline">
                          <span
                            className={
                              formatProviderState(providerHealth, copy) === copy.providers.healthy
                                ? "provider-status provider-status--healthy"
                                : "provider-status"
                            }
                          >
                            {formatProviderState(providerHealth, copy)}
                          </span>
                          <span className="provider-route-pill">{formatRoutePolicyLabel(provider.route_policy, copy)}</span>
                        </div>
                        <h3>{provider.name}</h3>
                        <p>{copy.providers.primaryModel(provider.exposed_model)}</p>
                        <div className="provider-chip-row">
                          {provider.http_enabled ? <span className="provider-chip">{copy.providers.openAiHttp}</span> : null}
                          {provider.cli_enabled ? <span className="provider-chip">{copy.providers.cliRuntime}</span> : null}
                          {provider.chat_capable ? <span className="provider-chip">{copy.providers.chatCapableChip}</span> : null}
                          {provider.stream_capable ? <span className="provider-chip">{copy.providers.streaming}</span> : null}
                        </div>
                        <div className="provider-detail-list">
                          <div>
                            <span>{copy.providers.httpBase}</span>
                            <strong>{provider.http_base_url ?? copy.common.notConfigured}</strong>
                          </div>
                          <div>
                            <span>{copy.providers.cliCommandLabel}</span>
                            <strong>{provider.cli_command ?? copy.common.notConfigured}</strong>
                          </div>
                          <div>
                            <span>{copy.providers.modelCatalog}</span>
                            <strong>
                              {providerModelsCount === null
                                ? copy.providers.catalogPending
                                : providerModelsCount > 0
                                  ? copy.common.loadedCount(providerModelsCount)
                                  : copy.providers.openCatalog}
                            </strong>
                          </div>
                        </div>
                        <div className="inline-actions">
                          <button
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation();
                              void handleOpenProviderModels(provider.name);
                            }}
                          >
                            {copy.common.viewModels}
                          </button>
                          <button
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation();
                              void handleRediscoverModels(provider.name);
                            }}
                          >
                            {copy.common.rediscover}
                          </button>
                        </div>
                      </article>
                    );
                  })}
                </div>
              </div>
              <aside className="provider-panel provider-summary-panel">
                <div className="provider-panel-header">
                  <div>
                    <span className="section-eyebrow">{copy.providers.selectedProvider}</span>
                    <h3>{selectedProviderRecord?.name ?? copy.providers.selectedSummary}</h3>
                    <p>{selectedProviderRecord ? copy.providers.selectedDescription : copy.providers.selectionHint}</p>
                  </div>
                </div>
                {selectedProviderRecord ? (
                  <div className="provider-summary-rail">
                    <div className="provider-operations-card provider-operations-card--highlight">
                      <span className="provider-summary-label">{copy.providers.primaryModel(selectedProviderRecord.exposed_model)}</span>
                      <strong>{selectedProviderRecord.name}</strong>
                      <p>{copy.providers.manageModelsHint}</p>
                    </div>
                    <div className="provider-fact-grid">
                      <div className="provider-fact">
                        <span>{copy.providers.statusLabel}</span>
                        <strong>{formatProviderState(selectedProviderHealth, copy)}</strong>
                      </div>
                      <div className="provider-fact">
                        <span>{copy.providers.routePolicy}</span>
                        <strong>{formatRoutePolicyLabel(selectedProviderRecord.route_policy, copy)}</strong>
                      </div>
                      <div className="provider-fact">
                        <span>{copy.providers.catalogStateLabel}</span>
                        <strong>
                          {providerModels[selectedProviderRecord.name]
                            ? copy.common.loadedCount(providerModels[selectedProviderRecord.name]?.length ?? 0)
                            : copy.providers.catalogPending}
                        </strong>
                      </div>
                      <div className="provider-fact">
                        <span>{copy.providers.transportLabel}</span>
                        <strong>
                          {selectedProviderRecord.http_enabled && selectedProviderRecord.cli_enabled
                            ? `${copy.providers.openAiHttp} + ${copy.providers.cliRuntime}`
                            : selectedProviderRecord.http_enabled
                              ? copy.providers.openAiHttp
                              : selectedProviderRecord.cli_enabled
                                ? copy.providers.cliRuntime
                                : copy.common.noData}
                        </strong>
                      </div>
                    </div>
                    <div className="provider-operations-card">
                      <span className="provider-summary-label">{copy.providers.httpBase}</span>
                      <strong>{selectedProviderRecord.http_base_url ?? copy.common.notConfigured}</strong>
                      <p>{copy.providers.cliCommandLabel}: {selectedProviderRecord.cli_command ?? copy.common.notConfigured}</p>
                    </div>
                    <div className="provider-operations-card">
                      <span className="provider-summary-label">{copy.providers.capabilitiesLabel}</span>
                      <div className="provider-chip-row">
                        {selectedProviderRecord.http_enabled ? <span className="provider-chip">{copy.providers.openAiHttp}</span> : null}
                        {selectedProviderRecord.cli_enabled ? <span className="provider-chip">{copy.providers.cliRuntime}</span> : null}
                        {selectedProviderRecord.chat_capable ? <span className="provider-chip">{copy.providers.chatCapableChip}</span> : null}
                        {selectedProviderRecord.stream_capable ? <span className="provider-chip">{copy.providers.streaming}</span> : null}
                      </div>
                    </div>
                  </div>
                ) : null}
              </aside>
            </div>
          </section>
        );
      case "models":
        return (
          <section id="models" className="models-page">
            <div className="section-header">
              <div>
                <span className="section-eyebrow">{copy.models.eyebrow}</span>
                <h2>{copy.models.title}</h2>
                <p>Catalog, pricing, overrides, and live validation for the selected provider.</p>
              </div>
              <div className="inline-actions">
                <button type="button" onClick={() => void handleRediscoverModels()} disabled={!selectedProviderName}>
                  {copy.common.rediscover}
                </button>
                <button type="button" onClick={() => void handleRefreshPricing()} disabled={!selectedProviderName}>
                  {copy.models.refreshOfficialPricing}
                </button>
                <button type="button" onClick={() => setActiveModal("add-manual-model")} disabled={!selectedProviderName}>
                  {copy.models.addManualModel}
                </button>
              </div>
            </div>
            {providers.length === 0 ? (
              <p>{copy.models.noProviders}</p>
            ) : null}
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void loadSelectedProviderModels(selectedProviderName);
              }}
            >
              <div className="provider-selector">
                <span className="provider-selector-label">{copy.models.provider}</span>
                <div className="provider-selector-grid" role="tablist" aria-label="Provider">
                  {providers.map((provider) => (
                    <button
                      key={provider.id}
                      type="button"
                      role="tab"
                      aria-selected={selectedProviderName === provider.name}
                      className={
                        selectedProviderName === provider.name
                          ? "provider-selector-pill provider-selector-pill--active"
                          : "provider-selector-pill"
                      }
                      onClick={() => {
                        setSelectedProviderName(provider.name);
                        void loadSelectedProviderModels(provider.name);
                      }}
                    >
                      {provider.name}
                    </button>
                  ))}
                </div>
              </div>
            </form>
            <div className="models-layout">
              <div className="provider-panel models-catalog-panel">
                <div className="provider-panel-header">
                  <div>
                    <span className="section-eyebrow">{copy.models.eyebrow}</span>
                    <h3>{selectedProviderName || copy.models.provider}</h3>
                    <p>Compact rows for model availability, pricing, and current exposure.</p>
                  </div>
                </div>
                <div className="models-catalog-toolbar">
                  <div className="models-catalog-summary">
                    <div className="provider-fact">
                      <span>{copy.models.totalModels}</span>
                      <strong>{selectedProviderModels.length}</strong>
                    </div>
                    <div className="provider-fact">
                      <span>{copy.models.activeModels}</span>
                      <strong>{selectedProviderModels.filter((model) => model.enabled).length}</strong>
                    </div>
                    <div className="provider-fact">
                      <span>{copy.models.manualModels}</span>
                      <strong>{selectedProviderModels.filter((model) => model.manually_overridden).length}</strong>
                    </div>
                  </div>
                  <div className="models-catalog-controls">
                    <label>
                      {copy.models.searchModels}
                      <input value={modelQuery} onChange={(event) => setModelQuery(event.target.value)} />
                    </label>
                    <div className="provider-selector">
                      <span className="provider-selector-label">{copy.models.currentStatus}</span>
                      <div className="provider-selector-grid" role="tablist" aria-label={copy.models.currentStatus}>
                        {[
                          { id: "all", label: copy.models.filterAll },
                          { id: "enabled", label: copy.models.filterEnabled },
                          { id: "disabled", label: copy.models.filterDisabled },
                        ].map((option) => (
                          <button
                            key={option.id}
                            type="button"
                            role="tab"
                            aria-selected={modelFilter === option.id}
                            className={modelFilter === option.id ? "provider-selector-pill provider-selector-pill--active" : "provider-selector-pill"}
                            onClick={() => setModelFilter(option.id as "all" | "enabled" | "disabled")}
                          >
                            {option.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
                <ul>
                  {visibleProviderModels.length === 0 ? (
                    <li className="models-empty-state">{copy.models.noMatches}</li>
                  ) : visibleProviderModels.map((model) => (
                    <li
                      key={model.id}
                      className={model.native_model === pricingNativeModel ? "models-row models-row--active" : "models-row"}
                      role="button"
                      tabIndex={0}
                      onClick={() => setPricingNativeModel(model.native_model)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          setPricingNativeModel(model.native_model);
                        }
                      }}
                    >
                      <div className="models-row-topline">
                        <strong>{model.native_model}</strong>
                        {model.native_model === pricingNativeModel ? <span className="provider-chip">{copy.models.selectedLabel}</span> : null}
                      </div>
                      <div className="models-row-grid">
                        <div className="models-row-cell">
                          <span>{copy.models.exposedModelId}</span>
                          <strong>{model.exposed_model_id}</strong>
                        </div>
                        <div className="models-row-cell">
                          <span>{copy.models.source}</span>
                          <strong>{formatModelSourceLabel(model.source, model.pricing?.source_kind, locale)}</strong>
                        </div>
                        <div className="models-row-cell">
                          <span>{copy.models.officialPrice}</span>
                          <strong>
                            {model.pricing && model.pricing.input_price !== null && model.pricing.output_price !== null
                              ? copy.models.pricingSummary(
                                  formatUsdPerMillion(model.pricing.input_price),
                                  formatUsdPerMillion(model.pricing.output_price),
                                )
                              : copy.models.noOfficialPrice}
                          </strong>
                        </div>
                        <div className="models-row-cell">
                          <span>{copy.models.currentStatus}</span>
                          <strong>{model.enabled ? copy.common.enabled : copy.common.disabled}</strong>
                        </div>
                      </div>
                      <div className="models-row-meta">
                        <span>{model.pricing?.source_label ?? copy.common.noData}</span>
                        <span>{model.pricing?.synced_at ? copy.models.syncedAt(formatPricingSync(model.pricing.synced_at, locale)) : copy.common.noData}</span>
                      </div>
                      <div className="inline-actions">
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            setPricingNativeModel(model.native_model);
                          }}
                        >
                          {copy.common.viewModels}
                        </button>
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            void handleToggleProviderModel(model.native_model, model.enabled);
                          }}
                        >
                          {model.enabled ? copy.models.disable : copy.models.enable}
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
              <aside className="provider-panel models-tools-panel">
                <div className="provider-panel-header">
                  <div>
                    <span className="section-eyebrow">{copy.models.overview}</span>
                    <h3>{selectedModel?.native_model ?? copy.models.currentModel}</h3>
                    <p>{selectedModel ? copy.models.exposedAs(selectedModel.exposed_model_id) : copy.models.selectModelHint}</p>
                  </div>
                </div>
                <div className="provider-operations-stack">
                  <div className="provider-operations-card">
                    <span className="provider-summary-label">{copy.models.currentStatus}</span>
                    <strong>{selectedModel ? (selectedModel.enabled ? copy.common.enabled : copy.common.disabled) : copy.common.noData}</strong>
                    <p>{selectedModel ? formatModelSourceLabel(selectedModel.source, selectedModel.pricing?.source_kind, locale) : copy.common.noData}</p>
                  </div>
                  <div className="provider-operations-card">
                    <span className="provider-summary-label">{copy.models.pricingSource}</span>
                    <strong>
                      {selectedModel?.pricing && selectedModel.pricing.input_price !== null && selectedModel.pricing.output_price !== null
                        ? copy.models.pricingSummary(
                            formatUsdPerMillion(selectedModel.pricing.input_price),
                            formatUsdPerMillion(selectedModel.pricing.output_price),
                          )
                        : copy.models.noOfficialPrice}
                    </strong>
                    <p>{selectedModel?.pricing?.source_label ?? copy.common.noData}</p>
                  </div>
                  <div className="provider-operations-card">
                    <span className="provider-summary-label">{copy.models.syncedLabel}</span>
                    <strong>{selectedModel?.pricing?.synced_at ? formatPricingSync(selectedModel.pricing.synced_at, locale) : copy.common.noData}</strong>
                    <p>{selectedModel?.pricing?.notes ?? copy.common.noData}</p>
                  </div>
                </div>
                <section className="panel models-edit-panel">
                  <h3>{copy.models.exposureWorkspace}</h3>
                  <form onSubmit={handleSaveExposedModelId} className="models-workbench-form">
                    <label>
                      {copy.models.exposedModelId}
                      <input
                        value={exposedModelDraft}
                        onChange={(event) => setExposedModelDraft(event.target.value)}
                        disabled={!selectedModel}
                      />
                    </label>
                    <div className="inline-actions">
                      <button type="submit" disabled={!selectedModel || modelPanelStatus === "saving"}>
                        {modelPanelStatus === "saving" ? copy.models.saving : copy.models.rename}
                      </button>
                      <button
                        type="button"
                        disabled={!selectedModel || modelPanelStatus === "saving"}
                        onClick={() => {
                          if (selectedModel) {
                            void handleToggleProviderModel(selectedModel.native_model, selectedModel.enabled);
                          }
                        }}
                      >
                        {selectedModel?.enabled ? copy.models.disable : copy.models.enable}
                      </button>
                    </div>
                  </form>
                  {modelPanelMessage ? (
                    <p className={modelPanelStatus === "error" ? "models-panel-message models-panel-message--error" : "models-panel-message"}>
                      {modelPanelStatus === "saved" ? copy.models.saved : modelPanelStatus === "saving" ? copy.models.saving : modelPanelMessage}
                    </p>
                  ) : null}
                </section>
                <section className="panel models-pricing-panel">
                  <h3>{copy.models.pricingWorkspace}</h3>
                  <form onSubmit={handlePricingOverrideSubmit} className="models-pricing-form">
                    <div className="models-pricing-grid">
                      <label>
                        {copy.models.inputPrice}
                        <input value={pricingInput} onChange={(event) => setPricingInput(event.target.value)} disabled={!selectedModel} />
                      </label>
                      <label>
                        {copy.models.outputPrice}
                        <input value={pricingOutput} onChange={(event) => setPricingOutput(event.target.value)} disabled={!selectedModel} />
                      </label>
                      <label>
                        {copy.models.cachedInputPrice}
                        <input value={pricingCachedInput} onChange={(event) => setPricingCachedInput(event.target.value)} disabled={!selectedModel} />
                      </label>
                      <label>
                        {copy.models.highTierThreshold}
                        <input value={pricingThreshold} onChange={(event) => setPricingThreshold(event.target.value)} disabled={!selectedModel} />
                      </label>
                      <label>
                        {copy.models.highTierInput}
                        <input value={pricingInputHigh} onChange={(event) => setPricingInputHigh(event.target.value)} disabled={!selectedModel} />
                      </label>
                      <label>
                        {copy.models.highTierOutput}
                        <input value={pricingOutputHigh} onChange={(event) => setPricingOutputHigh(event.target.value)} disabled={!selectedModel} />
                      </label>
                      <label>
                        {copy.models.highTierCachedInput}
                        <input value={pricingCachedInputHigh} onChange={(event) => setPricingCachedInputHigh(event.target.value)} disabled={!selectedModel} />
                      </label>
                    </div>
                    <label>
                      {copy.models.pricingNotes}
                      <input value={pricingNotes} onChange={(event) => setPricingNotes(event.target.value)} disabled={!selectedModel} />
                    </label>
                    <div className="inline-actions">
                      <button type="submit" disabled={!selectedModel || modelPanelStatus === "saving"}>
                        {modelPanelStatus === "saving" ? copy.models.saving : copy.models.savePricingOverride}
                      </button>
                    </div>
                  </form>
                </section>
                <section className="panel models-test-panel">
                  <h3>{copy.models.validationWorkspace}</h3>
                  <div className="provider-selector">
                    <span className="provider-selector-label">{copy.models.pricingTargetModel}</span>
                    <div className="provider-selector-grid" role="tablist" aria-label={copy.models.pricingTargetModel}>
                      {selectedProviderModels.map((model) => (
                        <button
                          key={`test-${model.id}`}
                          type="button"
                          role="tab"
                          aria-selected={pricingNativeModel === model.native_model}
                          className={
                            pricingNativeModel === model.native_model
                              ? "provider-selector-pill provider-selector-pill--active"
                              : "provider-selector-pill"
                          }
                          onClick={() => setPricingNativeModel(model.native_model)}
                        >
                          {model.native_model}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="models-test-status" aria-live="polite">
                    <span className={testChatStatus === "loading" ? "status-pill status-pill--pending" : "status-pill"}>
                      {testChatStatus === "loading"
                        ? copy.models.testRunning
                        : selectedModel
                          ? `${copy.models.testReady}: ${selectedModel.native_model}`
                          : copy.common.noData}
                    </span>
                    {testChatError ? (
                      <p className="models-test-error" role="alert">
                        {copy.models.testFailed}: {testChatError}
                      </p>
                    ) : null}
                  </div>
                  <form onSubmit={handleModelTestSubmit}>
                    <label>
                      {copy.models.testChat}
                      <input
                        placeholder={copy.models.testPromptPlaceholder}
                        value={testMessage}
                        onChange={(event) => setTestMessage(event.target.value)}
                        disabled={!selectedModel}
                      />
                    </label>
                    <div className="inline-actions">
                      <button type="submit" disabled={!selectedModel || !testMessage.trim() || testChatStatus === "loading"}>
                        {testChatStatus === "loading" ? copy.models.testRunning : copy.models.sendTestMessage}
                      </button>
                      <button
                        type="button"
                        disabled={!selectedModel || !testMessage.trim() || testChatStatus === "loading"}
                        onClick={() => {
                          void handleModelTestStream();
                        }}
                      >
                        {copy.models.streamResponse}
                      </button>
                      <button type="button" disabled={testChatStatus !== "loading"} onClick={handleCancelModelStream}>
                        {copy.models.cancelStream}
                      </button>
                    </div>
                  </form>
                  <ul className="models-test-transcript">
                    {testChatMessages.length === 0 ? (
                      <li>{copy.models.noTestMessages}</li>
                    ) : (
                      testChatMessages.map((message, index) => (
                        <li
                          key={`${message.role}-${index}`}
                          className={
                            message.role === "user"
                              ? "models-test-message models-test-message--user"
                              : "models-test-message models-test-message--assistant"
                          }
                        >
                          <strong>{message.role === "user" ? copy.models.testerUser : copy.models.testerModel}</strong>
                          <div className="models-test-message-body">{message.content || copy.models.emptyResponse}</div>
                        </li>
                      ))
                    )}
                  </ul>
                </section>
              </aside>
            </div>
          </section>
        );
      case "usage":
        return (
          <section id="usage">
            <div className="section-header">
              <div>
                <span className="section-eyebrow">{copy.usage.eyebrow}</span>
                <h2>{copy.usage.title}</h2>
              </div>
            </div>
            {usageError ? <p role="alert">{copy.usage.title}: {usageError}</p> : null}
            <div className="provider-summary-grid">
              <article className="provider-summary-card">
                <span className="provider-summary-label">{copy.usage.totalTrackedKeys}</span>
                <strong>{recentKeyActivity.length}</strong>
                <p>{copy.usage.trackedKeyCount(recentKeyActivity.length)}</p>
              </article>
              <article className="provider-summary-card">
                <span className="provider-summary-label">{copy.usage.attributedProviders}</span>
                <strong>{providerActivity.length}</strong>
                <p>{providerActivity.length === 0 ? copy.usage.noAttributedUsage : providerActivity.map(([name]) => name).join(", ")}</p>
              </article>
              <article className="provider-summary-card">
                <span className="provider-summary-label">{copy.usage.attributedModels}</span>
                <strong>{modelActivity.length}</strong>
                <p>{modelActivity.length === 0 ? copy.usage.noModelActivity : modelActivity.map(([name]) => name).join(", ")}</p>
              </article>
            </div>
            <div className="split">
              <div className="panel">
                <h3>{copy.usage.recentKeyActivity}</h3>
                {recentKeyActivity.length === 0 ? (
                  <p>{copy.usage.noKeys}</p>
                ) : (
                  <ul>
                    {recentKeyActivity.map((apiKey) => (
                      <li key={apiKey.api_key_id}>
                        <strong>{apiKey.name}</strong>
                        <div className="usage-meta">{apiKey.key_prefix} · {apiKey.status}</div>
                        <div className="usage-stats">
                          {copy.usage.requestsLimited(apiKey.total_requests, apiKey.limited_requests)}
                        </div>
                        <div className="usage-meta">{copy.usage.lastUsed(formatLastUsed(apiKey.last_used_at, locale, copy.common.noActivityYet))}</div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="panel">
                <h3>{copy.usage.topProvidersModels}</h3>
                <p>
                  {copy.usage.providers}:{" "}
                  {providerActivity.length === 0
                    ? copy.usage.noAttributedUsage
                    : providerActivity.map(([name, count]) => `${name} (${count})`).join(", ")}
                </p>
                <p>
                  {copy.usage.models}:{" "}
                  {modelActivity.length === 0
                    ? copy.usage.noModelActivity
                    : modelActivity.map(([name, count]) => `${name} (${count})`).join(", ")}
                </p>
              </div>
            </div>
          </section>
        );
      case "settings":
        return (
          <section id="settings">
            <div className="section-header">
              <div>
                <span className="section-eyebrow">{copy.settings.eyebrow}</span>
                <h2>{copy.settings.title}</h2>
              </div>
            </div>
            {settingsError ? <p role="alert">{copy.settings.title}: {settingsError}</p> : null}
            <div className="settings-grid">
              <article className="settings-card">
                <span className="provider-summary-label">{copy.settings.gatewayEndpoint}</span>
                <strong>
                  {settingsOverview?.gateway_host ?? "—"}:{settingsOverview?.gateway_port ?? "—"}
                </strong>
                <p>{copy.settings.frontendBaseUrl(settingsOverview?.frontend_base_url ?? "—")}</p>
                <p>{copy.settings.database(settingsOverview?.database_scheme ?? "—")}</p>
              </article>
              <article className="settings-card">
                <span className="provider-summary-label">{copy.settings.authentication}</span>
                <strong>{copy.settings.primarySignIn}</strong>
                <p>{copy.settings.githubOauth(Boolean(settingsOverview?.github_oauth_enabled), copy.common.enabled, copy.common.disabled)}</p>
                <p>{copy.settings.googleOauth(Boolean(settingsOverview?.google_oauth_enabled), copy.common.enabled, copy.common.disabled)}</p>
              </article>
              <article className="settings-card">
                <span className="provider-summary-label">{copy.settings.controlPlane}</span>
                <strong>{copy.settings.adminBoundary}</strong>
                <p>{copy.settings.adminSecretConfigured(Boolean(settingsOverview?.admin_secret_configured), copy.common.yes, copy.common.no)}</p>
                <p>{copy.settings.authSeparation}</p>
              </article>
              <article className="settings-card">
                <span className="provider-summary-label">{copy.settings.interfaceLanguage}</span>
                <strong>{messages[locale].localeLabel}</strong>
                <p>{copy.shell.language}: {locale === "en" ? "English / 中文" : "中文 / English"}</p>
              </article>
            </div>
          </section>
        );
      default:
        return null;
    }
  }

  if (authState === "loading") {
    return (
      <main className="auth-shell">
        <section id="auth-loading" className="auth-card auth-card--loading">
          <div className="auth-brand-lockup">
            <div className="auth-brand-mark">AG</div>
            <div>
              <h1>{copy.shell.productName}</h1>
              <p className="auth-kicker">{copy.shell.gatewayOperations}</p>
            </div>
          </div>
          <div className="language-toggle">
            <button type="button" className={locale === "en" ? "language-toggle-active" : undefined} onClick={() => setLocale("en")}>
              English
            </button>
            <button type="button" className={locale === "zh" ? "language-toggle-active" : undefined} onClick={() => setLocale("zh")}>
              中文
            </button>
          </div>
          <p>{copy.auth.checkingSession}</p>
        </section>
      </main>
    );
  }

  if (authState === "unauthenticated") {
    return (
      <main className="auth-shell">
        <section id="auth" className="auth-card">
          <div className="auth-split">
            <div className="auth-copy">
              <div className="auth-brand-lockup">
                <div className="auth-brand-mark">AG</div>
                <div>
                  <h1>{copy.shell.productName}</h1>
                  <p className="auth-kicker">{copy.shell.gatewayOperations}</p>
                </div>
              </div>
              <h2>{authMode === "login" ? copy.auth.signInTitle : copy.auth.registerTitle}</h2>
              <p>{copy.auth.description}</p>
              <ul className="auth-feature-list">
                <li>{copy.auth.featureTraffic}</li>
                <li>{copy.auth.featureProviders}</li>
                <li>{copy.auth.featureKeys}</li>
              </ul>
            </div>
            <div className="auth-form-panel">
              <div className="language-toggle">
                <button type="button" className={locale === "en" ? "language-toggle-active" : undefined} onClick={() => setLocale("en")}>
                  English
                </button>
                <button type="button" className={locale === "zh" ? "language-toggle-active" : undefined} onClick={() => setLocale("zh")}>
                  中文
                </button>
              </div>
              <div className="auth-form-header">
                <span className="auth-eyebrow">{authMode === "login" ? copy.auth.primaryAccess : copy.auth.createWorkspaceAccess}</span>
                <h3>{authMode === "login" ? copy.auth.emailSignIn : copy.auth.emailRegister}</h3>
              </div>
              {authError ? <p role="alert">{copy.auth.authFailed}: {authError}</p> : null}
              <form className="auth-form" onSubmit={handleAuthSubmit}>
                {authMode === "register" ? (
                  <label className="auth-field">
                    <span className="auth-label">{copy.auth.name}</span>
                    <input value={authName} onChange={(event) => setAuthName(event.target.value)} />
                  </label>
                ) : null}
                <label className="auth-field">
                  <span className="auth-label">{copy.auth.email}</span>
                  <input value={authEmail} onChange={(event) => setAuthEmail(event.target.value)} />
                </label>
                <label className="auth-field">
                  <span className="auth-label">{copy.auth.password}</span>
                  <input
                    type="password"
                    value={authPassword}
                    onChange={(event) => setAuthPassword(event.target.value)}
                  />
                </label>
                <button className="auth-submit" type="submit">
                  {authMode === "login" ? copy.auth.signIn : copy.auth.createAccount}
                </button>
              </form>
              <div className="auth-toggle-group">
                <button
                  className={authMode === "login" ? "auth-secondary auth-secondary--active" : "auth-secondary"}
                  type="button"
                  onClick={() => setAuthMode("login")}
                >
                  {copy.auth.useEmailLogin}
                </button>
                <button
                  className={authMode === "register" ? "auth-secondary auth-secondary--active" : "auth-secondary"}
                  type="button"
                  onClick={() => setAuthMode("register")}
                >
                  {copy.auth.createAccount}
                </button>
              </div>
              <div className="auth-social-group">
                <button
                  className="auth-social-button"
                  type="button"
                  disabled={!authProviders.github_enabled}
                  onClick={() => {
                    window.location.href = "/auth/oauth/github";
                  }}
                >
                  {copy.auth.continueWithGithub}
                </button>
                <button
                  className="auth-social-button"
                  type="button"
                  disabled={!authProviders.google_enabled}
                  onClick={() => {
                    window.location.href = "/auth/oauth/google";
                  }}
                >
                  {copy.auth.continueWithGoogle}
                </button>
              </div>
              <p className="auth-provider-note">
                {copy.auth.providerNote(authProviders.github_enabled, authProviders.google_enabled)}
              </p>
            </div>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="sidebar-mark">AG</div>
          <div>
            <h1>{copy.shell.productName}</h1>
            <p>{copy.shell.productTagline}</p>
          </div>
        </div>
        <div className="sidebar-section-label">{copy.shell.navigation}</div>
        <nav>
          {NAV_ITEMS.map((item) => (
            <a key={item.id} href={`#${item.id}`} aria-current={currentRoute === item.id ? "page" : undefined}>
              {item.label}
            </a>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span className="sidebar-footer-label">{copy.shell.runtime}</span>
          <strong>{copy.shell.gateway}</strong>
        </div>
      </aside>
      <section className="content">
        <header className="topbar">
          <div className="topbar-title-group">
            <span className="topbar-eyebrow">{copy.shell.developerPlatform}</span>
            <strong>{copy.shell.gatewayOperations}</strong>
          </div>
          <div className="topbar-user">
            <div className="language-toggle language-toggle--compact">
              <button type="button" className={locale === "en" ? "language-toggle-active" : undefined} onClick={() => setLocale("en")}>
                English
              </button>
              <button type="button" className={locale === "zh" ? "language-toggle-active" : undefined} onClick={() => setLocale("zh")}>
                中文
              </button>
            </div>
            <span className="topbar-user-email">{authUser?.email ?? copy.common.signedIn}</span>
            <button className="topbar-logout" type="button" onClick={handleLogout}>
              {copy.shell.signOut}
            </button>
          </div>
        </header>
        <div className="page-body">{renderCurrentPage()}</div>
      </section>
      {renderModal()}
    </main>
  );
}
