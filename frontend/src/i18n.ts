export type Locale = "en" | "zh";

type Copy = {
  localeLabel: string;
  shell: {
    productName: string;
    productTagline: string;
    navigation: string;
    runtime: string;
    gateway: string;
    developerPlatform: string;
    gatewayOperations: string;
    signOut: string;
    language: string;
  };
  nav: {
    dashboard: string;
    providers: string;
    models: string;
    accounts: string;
    apiKeys: string;
    usage: string;
    settings: string;
  };
  common: {
    noData: string;
    enabled: string;
    disabled: string;
    yes: string;
    no: string;
    cancel: string;
    close: string;
    signedIn: string;
    defaultLabel: string;
    create: string;
    add: string;
    revoke: string;
    rediscover: string;
    viewModels: string;
    noActivityYet: string;
    notConfigured: string;
    loadedCount: (count: number) => string;
  };
  auth: {
    checkingSession: string;
    signInTitle: string;
    registerTitle: string;
    description: string;
    featureTraffic: string;
    featureProviders: string;
    featureKeys: string;
    primaryAccess: string;
    createWorkspaceAccess: string;
    emailSignIn: string;
    emailRegister: string;
    authFailed: string;
    name: string;
    email: string;
    password: string;
    signIn: string;
    createAccount: string;
    useEmailLogin: string;
    continueWithGithub: string;
    continueWithGoogle: string;
    providerNote: (githubReady: boolean, googleReady: boolean) => string;
    ready: string;
    needsConfiguration: string;
  };
  dashboard: {
    overview: string;
    platformOverview: string;
    requests: string;
    requestsSubtitle: string;
    activeKeys: string;
    activeKeysSubtitle: string;
    errorRate: string;
    errorRateSubtitle: string;
    rateLimitHits: string;
    rateLimitHitsSubtitle: string;
    traffic: string;
    noRuntimeActivity: string;
    peakTraffic: (count: number, label: string) => string;
    requestsInWindow: (count: number) => string;
    errorCount: (count: number) => string;
    limitedCount: (count: number) => string;
  };
  accounts: {
    eyebrow: string;
    title: string;
    accountName: string;
    addAccount: string;
    totalAccounts: string;
    activeAccounts: string;
    pendingNotes: string;
    credits: string;
    selectedBalance: (value: number) => string;
    activeOnly: string;
    noteCount: (count: number) => string;
    empty: string;
    creditDelta: string;
    adjustmentNotes: string;
    applyCreditAdjustment: string;
    ledgerEmpty: string;
    balanceAfter: (value: number) => string;
  };
  apiKeys: {
    eyebrow: string;
    title: string;
    account: string;
    keyName: string;
    perMinute: string;
    perHour: string;
    perDay: string;
    createKey: string;
    lastCreatedKey: string;
    activeKeys: string;
    revokedKeys: string;
    quotaCoverage: string;
    quotaCoverageValue: (count: number, total: number) => string;
    noKeys: string;
    requestsPerMin: string;
    requestsPerHour: string;
    requestsPerDay: string;
  };
  providers: {
    eyebrow: string;
    title: string;
    description: string;
    runtimeCoverage: string;
    runtimeCoverageDescription: string;
    httpTransport: string;
    httpTransportDescription: string;
    cliRuntimes: string;
    cliRuntimesDescription: string;
    streamingReady: string;
    streamingReadyDescription: string;
    registry: string;
    activeProviders: string;
    compose: string;
    registerProvider: string;
    registerDescription: string;
    providerName: string;
    exposedModel: string;
    routePolicy: string;
    httpEnabled: string;
    cliEnabled: string;
    httpBaseUrl: string;
    cliCommand: string;
    chatCapable: string;
    streamCapable: string;
    addProvider: string;
    primaryModel: (model: string) => string;
    healthy: string;
    offline: string;
    awaitingProbe: string;
    routePolicyHttpFirst: string;
    routePolicyCliFirst: string;
    routePolicyFixedHttp: string;
    routePolicyFixedCli: string;
    httpBase: string;
    cliCommandLabel: string;
    modelCatalog: string;
    openCatalog: string;
    openAiHttp: string;
    cliRuntime: string;
    chatCapableChip: string;
    streaming: string;
    selectedProvider: string;
    selectedSummary: string;
    selectedDescription: string;
    selectionHint: string;
    statusLabel: string;
    transportLabel: string;
    capabilitiesLabel: string;
    catalogStateLabel: string;
    catalogPending: string;
    manageModelsHint: string;
  };
    models: {
      eyebrow: string;
      title: string;
      provider: string;
      noProviders: string;
      source: string;
      exposedAs: (modelId: string) => string;
      disable: string;
      enable: string;
      rename: string;
      nativeModel: string;
      exposedModelId: string;
      addManualModel: string;
      officialPrice: string;
      noOfficialPrice: string;
      pricingSummary: (input: string, output: string) => string;
      cachedPrice: (value: string) => string;
      pricingTier: (threshold: number, input: string, output: string) => string;
      sourceLink: string;
      syncedAt: (value: string) => string;
      refreshOfficialPricing: string;
      pricingTargetModel: string;
      inputPrice: string;
      cachedInputPrice: string;
      outputPrice: string;
      highTierInput: string;
      highTierCachedInput: string;
      highTierOutput: string;
      highTierThreshold: string;
      pricingNotes: string;
      savePricingOverride: string;
      overview: string;
      currentModel: string;
      currentStatus: string;
      pricingSource: string;
      syncedLabel: string;
      totalModels: string;
      activeModels: string;
      manualModels: string;
      searchModels: string;
      filterAll: string;
      filterEnabled: string;
      filterDisabled: string;
      noMatches: string;
      selectedLabel: string;
      exposureWorkspace: string;
      pricingWorkspace: string;
      validationWorkspace: string;
      selectModelHint: string;
      saving: string;
      saved: string;
      testChat: string;
      testPromptPlaceholder: string;
      testReady: string;
      testRunning: string;
      testFailed: string;
      emptyResponse: string;
      streamResponse: string;
      cancelStream: string;
      testCancelled: string;
      sendTestMessage: string;
      noTestMessages: string;
      testerUser: string;
      testerModel: string;
    };
  usage: {
    eyebrow: string;
    title: string;
    recentKeyActivity: string;
    topProvidersModels: string;
    noKeys: string;
    noAttributedUsage: string;
    noModelActivity: string;
    providers: string;
    models: string;
    requestsLimited: (requests: number, limited: number) => string;
    lastUsed: (value: string) => string;
    totalTrackedKeys: string;
    trackedKeyCount: (count: number) => string;
    attributedProviders: string;
    attributedModels: string;
  };
  settings: {
    eyebrow: string;
    title: string;
    gatewayEndpoint: string;
    frontendBaseUrl: (url: string) => string;
    database: (scheme: string) => string;
    authentication: string;
    primarySignIn: string;
    githubOauth: (enabled: boolean, enabledText: string, disabledText: string) => string;
    googleOauth: (enabled: boolean, enabledText: string, disabledText: string) => string;
    controlPlane: string;
    adminBoundary: string;
    adminSecretConfigured: (configured: boolean, yes: string, no: string) => string;
    authSeparation: string;
    interfaceLanguage: string;
  };
};

export const LOCALE_STORAGE_KEY = "agh_locale";

export const messages: Record<Locale, Copy> = {
  en: {
    localeLabel: "English",
    shell: {
      productName: "AgentHub",
      productTagline: "Developer Platform",
      navigation: "Navigation",
      runtime: "Runtime",
      gateway: "OpenAI-compatible gateway",
      developerPlatform: "Developer Platform",
      gatewayOperations: "Gateway operations",
      signOut: "Sign out",
      language: "Language",
    },
    nav: {
      dashboard: "Dashboard",
      providers: "Providers",
      models: "Models",
      accounts: "Accounts",
      apiKeys: "API Keys",
      usage: "Usage",
      settings: "Settings",
    },
    common: {
      noData: "No data yet.",
      enabled: "Enabled",
      disabled: "Disabled",
      yes: "Yes",
      no: "No",
      cancel: "Cancel",
      close: "Close",
      signedIn: "Signed in",
      defaultLabel: "default",
      create: "Create",
      add: "Add",
      revoke: "Revoke",
      rediscover: "Rediscover",
      viewModels: "View models",
      noActivityYet: "No activity yet",
      notConfigured: "Not configured",
      loadedCount: (count) => `${count} loaded`,
    },
    auth: {
      checkingSession: "Checking session…",
      signInTitle: "Sign in to your platform",
      registerTitle: "Create your operator account",
      description: "Manage providers, keys, model catalogs, quotas, and traffic from one dark developer console.",
      featureTraffic: "Track request volume, key activity, and rate-limit hits",
      featureProviders: "Control HTTP and CLI providers from the same shell",
      featureKeys: "Keep OpenAI-compatible access behind managed API keys",
      primaryAccess: "Primary access",
      createWorkspaceAccess: "Create workspace access",
      emailSignIn: "Email sign in",
      emailRegister: "Register with email",
      authFailed: "Authentication failed",
      name: "Name",
      email: "Email",
      password: "Password",
      signIn: "Sign In",
      createAccount: "Create Account",
      useEmailLogin: "Use Email Login",
      continueWithGithub: "Continue with GitHub",
      continueWithGoogle: "Continue with Google",
      providerNote: (githubReady, googleReady) =>
        `GitHub ${githubReady ? "is ready" : "needs configuration"} · Google ${
          googleReady ? "is ready" : "needs configuration"
        }`,
      ready: "is ready",
      needsConfiguration: "needs configuration",
    },
    dashboard: {
      overview: "Overview",
      platformOverview: "Platform Overview",
      requests: "Requests",
      requestsSubtitle: "Gateway traffic volume",
      activeKeys: "Active Keys",
      activeKeysSubtitle: "Live access credentials",
      errorRate: "Error Rate",
      errorRateSubtitle: "Failed request ratio",
      rateLimitHits: "Rate Limit Hits",
      rateLimitHitsSubtitle: "Quota pressure",
      traffic: "Traffic",
      noRuntimeActivity: "No runtime activity recorded yet.",
      peakTraffic: (count, label) => `Peak traffic hit ${count} requests during ${label}.`,
      requestsInWindow: (count) => `${count} requests in window`,
      errorCount: (count) => `${count} errors`,
      limitedCount: (count) => `${count} limited`,
    },
    accounts: {
      eyebrow: "Identity",
      title: "Account Management",
      accountName: "Account Name",
      addAccount: "Add Account",
      totalAccounts: "Total Accounts",
      activeAccounts: "Active Accounts",
      pendingNotes: "Accounts With Notes",
      credits: "Credits",
      selectedBalance: (value) => `Current account balance ${value}`,
      activeOnly: "Active only",
      noteCount: (count) => `${count} with notes`,
      empty: "No accounts yet.",
      creditDelta: "Credits delta",
      adjustmentNotes: "Notes",
      applyCreditAdjustment: "Apply Credit Adjustment",
      ledgerEmpty: "No credit ledger entries yet.",
      balanceAfter: (value) => `balance ${value}`,
    },
    apiKeys: {
      eyebrow: "Access",
      title: "Key Management",
      account: "Account",
      keyName: "API Key Name",
      perMinute: "Per Minute",
      perHour: "Per Hour",
      perDay: "Per Day",
      createKey: "Create API Key",
      lastCreatedKey: "Last Created Key",
      activeKeys: "Active Keys",
      revokedKeys: "Revoked Keys",
      quotaCoverage: "Quota Coverage",
      quotaCoverageValue: (count, total) => `${count} / ${total} keys have explicit limits`,
      noKeys: "No API keys yet.",
      requestsPerMin: "min",
      requestsPerHour: "hr",
      requestsPerDay: "day",
    },
    providers: {
      eyebrow: "Runtime",
      title: "Provider Registry",
      description: "Control transport policy, health posture, and model entry points for every upstream runtime.",
      runtimeCoverage: "Runtime coverage",
      runtimeCoverageDescription: "Total configured providers in the gateway registry.",
      httpTransport: "OpenAI-compatible HTTP",
      httpTransportDescription: "Providers currently able to route through HTTP transport.",
      cliRuntimes: "CLI runtimes",
      cliRuntimesDescription: "Providers available through local command execution.",
      streamingReady: "Streaming ready",
      streamingReadyDescription: "Providers marked as stream-capable from the control plane.",
      registry: "Registry",
      activeProviders: "Active providers",
      compose: "Compose",
      registerProvider: "Register provider",
      registerDescription: "Add a new upstream and decide which transport the gateway should prefer.",
      providerName: "Provider Name",
      exposedModel: "Exposed Model",
      routePolicy: "Route Policy",
      httpEnabled: "HTTP Enabled",
      cliEnabled: "CLI Enabled",
      httpBaseUrl: "HTTP Base URL",
      cliCommand: "CLI Command",
      chatCapable: "Chat Capable",
      streamCapable: "Stream Capable",
      addProvider: "Add Provider",
      primaryModel: (model) => `Primary exposed model: ${model}`,
      healthy: "Healthy",
      offline: "Offline",
      awaitingProbe: "Awaiting probe",
      routePolicyHttpFirst: "HTTP first",
      routePolicyCliFirst: "CLI first",
      routePolicyFixedHttp: "Fixed HTTP",
      routePolicyFixedCli: "Fixed CLI",
      httpBase: "HTTP base",
      cliCommandLabel: "CLI command",
      modelCatalog: "Model catalog",
      openCatalog: "Open catalog",
      openAiHttp: "OpenAI-compatible HTTP",
      cliRuntime: "CLI runtime",
      chatCapableChip: "Chat capable",
      streaming: "Streaming",
      selectedProvider: "Selected runtime",
      selectedSummary: "Runtime summary",
      selectedDescription: "A focused snapshot for the provider you are currently inspecting.",
      selectionHint: "Select a provider card to inspect transport, health, and catalog state.",
      statusLabel: "Health status",
      transportLabel: "Transport",
      capabilitiesLabel: "Capabilities",
      catalogStateLabel: "Catalog state",
      catalogPending: "Catalog not loaded yet",
      manageModelsHint: "Use the Models page for pricing, exposure, and live validation.",
    },
    models: {
      eyebrow: "Catalog",
      title: "Models",
      provider: "Provider",
      noProviders: "No providers registered yet. Add one in Providers before managing model catalogs.",
      source: "Source",
      exposedAs: (modelId) => `Exposed as ${modelId}`,
      disable: "Disable",
      enable: "Enable",
      rename: "Rename",
      nativeModel: "Native Model",
      exposedModelId: "Exposed Model ID",
      addManualModel: "Add Manual Model",
      officialPrice: "Official API Price",
      noOfficialPrice: "No official API price snapshot is available for this model yet.",
      pricingSummary: (input, output) => `${input} in · ${output} out`,
      cachedPrice: (value) => `${value} cached input`,
      pricingTier: (threshold, input, output) => `Above ${threshold.toLocaleString()} tokens: ${input} in · ${output} out`,
      sourceLink: "Source",
      syncedAt: (value) => `Synced ${value}`,
      refreshOfficialPricing: "Refresh Official Pricing",
      pricingTargetModel: "Pricing target model",
      inputPrice: "Input price",
      cachedInputPrice: "Cached input price",
      outputPrice: "Output price",
      highTierInput: "High-tier input",
      highTierCachedInput: "High-tier cached input",
      highTierOutput: "High-tier output",
      highTierThreshold: "High-tier threshold tokens",
      pricingNotes: "Pricing notes",
      savePricingOverride: "Save Pricing Override",
      overview: "Overview",
      currentModel: "Current model",
      currentStatus: "Current status",
      pricingSource: "Pricing source",
      syncedLabel: "Pricing sync",
      totalModels: "Total models",
      activeModels: "Active models",
      manualModels: "Manual entries",
      searchModels: "Search models",
      filterAll: "All",
      filterEnabled: "Enabled",
      filterDisabled: "Disabled",
      noMatches: "No models match the current search or filter.",
      selectedLabel: "Selected",
      exposureWorkspace: "Exposure controls",
      pricingWorkspace: "Pricing workspace",
      validationWorkspace: "Validation console",
      selectModelHint: "Select a model row to inspect, rename, price, or test it.",
      saving: "Saving",
      saved: "Saved",
      testChat: "Test Chat",
      testPromptPlaceholder: "Test this model",
      testReady: "Ready to test",
      testRunning: "Testing model",
      testFailed: "Test failed",
      emptyResponse: "The model returned no visible text.",
      streamResponse: "Stream Response",
      cancelStream: "Cancel Stream",
      testCancelled: "Streaming cancelled",
      sendTestMessage: "Send Test Message",
      noTestMessages: "No test messages yet.",
      testerUser: "You",
      testerModel: "Model",
    },
    usage: {
      eyebrow: "Activity",
      title: "Usage",
      recentKeyActivity: "Recent key activity",
      topProvidersModels: "Top providers / models",
      noKeys: "No API keys yet.",
      noAttributedUsage: "No attributed usage yet.",
      noModelActivity: "No model activity yet.",
      providers: "Providers",
      models: "Models",
      requestsLimited: (requests, limited) => `${requests} requests · ${limited} limited`,
      lastUsed: (value) => `Last used ${value}`,
      totalTrackedKeys: "Tracked Keys",
      trackedKeyCount: (count) => `${count} keys`,
      attributedProviders: "Attributed Providers",
      attributedModels: "Attributed Models",
    },
    settings: {
      eyebrow: "Configuration",
      title: "Platform Settings",
      gatewayEndpoint: "Gateway endpoint",
      frontendBaseUrl: (url) => `Frontend base URL: ${url}`,
      database: (scheme) => `Database: ${scheme}`,
      authentication: "Authentication",
      primarySignIn: "Primary sign-in: Email + password",
      githubOauth: (enabled, enabledText, disabledText) => `GitHub OAuth: ${enabled ? enabledText : disabledText}`,
      googleOauth: (enabled, enabledText, disabledText) => `Google OAuth: ${enabled ? enabledText : disabledText}`,
      controlPlane: "Control plane",
      adminBoundary: "Admin boundary",
      adminSecretConfigured: (configured, yes, no) => `Admin secret configured: ${configured ? yes : no}`,
      authSeparation: "Session auth and gateway API keys remain separated by design.",
      interfaceLanguage: "Interface language",
    },
  },
  zh: {
    localeLabel: "中文",
    shell: {
      productName: "AgentHub",
      productTagline: "开发者平台",
      navigation: "导航",
      runtime: "运行时",
      gateway: "兼容 OpenAI 的网关",
      developerPlatform: "开发者平台",
      gatewayOperations: "网关控制台",
      signOut: "退出登录",
      language: "语言",
    },
    nav: {
      dashboard: "总览",
      providers: "服务提供方",
      models: "模型",
      accounts: "账户",
      apiKeys: "密钥",
      usage: "用量",
      settings: "设置",
    },
    common: {
      noData: "暂无数据。",
      enabled: "启用",
      disabled: "停用",
      yes: "是",
      no: "否",
      cancel: "取消",
      close: "关闭",
      signedIn: "已登录",
      defaultLabel: "默认",
      create: "创建",
      add: "新增",
      revoke: "吊销",
      rediscover: "重新发现",
      viewModels: "查看模型",
      noActivityYet: "暂无调用",
      notConfigured: "未配置",
      loadedCount: (count) => `已加载 ${count} 个`,
    },
    auth: {
      checkingSession: "正在检查会话…",
      signInTitle: "登录到你的平台",
      registerTitle: "创建操作账户",
      description: "在同一个深色控制台里管理 provider、密钥、模型目录、限额和流量。",
      featureTraffic: "查看请求量、密钥活跃度和限流命中",
      featureProviders: "在同一控制台管理 HTTP 和 CLI provider",
      featureKeys: "用托管 API Key 暴露兼容 OpenAI 的访问入口",
      primaryAccess: "主登录方式",
      createWorkspaceAccess: "创建工作区访问",
      emailSignIn: "邮箱登录",
      emailRegister: "邮箱注册",
      authFailed: "认证失败",
      name: "名称",
      email: "邮箱",
      password: "密码",
      signIn: "登录",
      createAccount: "创建账户",
      useEmailLogin: "使用邮箱登录",
      continueWithGithub: "使用 GitHub 继续",
      continueWithGoogle: "使用 Google 继续",
      providerNote: (githubReady, googleReady) =>
        `GitHub ${githubReady ? "已就绪" : "未配置"} · Google ${googleReady ? "已就绪" : "未配置"}`,
      ready: "已就绪",
      needsConfiguration: "未配置",
    },
    dashboard: {
      overview: "总览",
      platformOverview: "平台概览",
      requests: "请求数",
      requestsSubtitle: "网关总流量",
      activeKeys: "活跃密钥",
      activeKeysSubtitle: "当前可用凭据",
      errorRate: "错误率",
      errorRateSubtitle: "失败请求占比",
      rateLimitHits: "限流命中",
      rateLimitHitsSubtitle: "配额压力",
      traffic: "流量",
      noRuntimeActivity: "当前还没有运行时流量。",
      peakTraffic: (count, label) => `${label} 时段峰值为 ${count} 次请求。`,
      requestsInWindow: (count) => `窗口内 ${count} 次请求`,
      errorCount: (count) => `${count} 次错误`,
      limitedCount: (count) => `${count} 次限流`,
    },
    accounts: {
      eyebrow: "身份",
      title: "账户管理",
      accountName: "账户名称",
      addAccount: "新增账户",
      totalAccounts: "账户总数",
      activeAccounts: "活跃账户",
      pendingNotes: "含备注账户",
      credits: "信用点",
      selectedBalance: (value) => `当前账户余额 ${value}`,
      activeOnly: "全部活跃",
      noteCount: (count) => `${count} 个带备注`,
      empty: "暂无账户。",
      creditDelta: "信用点变动",
      adjustmentNotes: "备注",
      applyCreditAdjustment: "提交信用点调整",
      ledgerEmpty: "暂无信用点流水。",
      balanceAfter: (value) => `余额 ${value}`,
    },
    apiKeys: {
      eyebrow: "访问",
      title: "密钥管理",
      account: "账户",
      keyName: "密钥名称",
      perMinute: "每分钟",
      perHour: "每小时",
      perDay: "每天",
      createKey: "创建 API Key",
      lastCreatedKey: "最近创建的密钥",
      activeKeys: "活跃密钥",
      revokedKeys: "已吊销密钥",
      quotaCoverage: "限额覆盖率",
      quotaCoverageValue: (count, total) => `${total} 个密钥中有 ${count} 个设置了明确限额`,
      noKeys: "暂无 API Key。",
      requestsPerMin: "分钟",
      requestsPerHour: "小时",
      requestsPerDay: "天",
    },
    providers: {
      eyebrow: "运行时",
      title: "服务提供方目录",
      description: "统一管理每个上游运行时的路由策略、健康状态和模型入口。",
      runtimeCoverage: "运行覆盖",
      runtimeCoverageDescription: "当前网关中已注册的 provider 总数。",
      httpTransport: "OpenAI HTTP",
      httpTransportDescription: "当前可通过 HTTP 传输访问的 provider。",
      cliRuntimes: "CLI 运行时",
      cliRuntimesDescription: "当前可通过本地命令执行的 provider。",
      streamingReady: "支持流式",
      streamingReadyDescription: "控制面标记为支持流式输出的 provider。",
      registry: "注册表",
      activeProviders: "已启用 provider",
      compose: "新建",
      registerProvider: "注册 provider",
      registerDescription: "新增上游并决定网关优先使用哪种传输方式。",
      providerName: "Provider 名称",
      exposedModel: "暴露模型",
      routePolicy: "路由策略",
      httpEnabled: "启用 HTTP",
      cliEnabled: "启用 CLI",
      httpBaseUrl: "HTTP Base URL",
      cliCommand: "CLI 命令",
      chatCapable: "支持聊天",
      streamCapable: "支持流式",
      addProvider: "新增 Provider",
      primaryModel: (model) => `主暴露模型：${model}`,
      healthy: "健康",
      offline: "离线",
      awaitingProbe: "等待探测",
      routePolicyHttpFirst: "优先 HTTP",
      routePolicyCliFirst: "优先 CLI",
      routePolicyFixedHttp: "固定 HTTP",
      routePolicyFixedCli: "固定 CLI",
      httpBase: "HTTP 地址",
      cliCommandLabel: "CLI 命令",
      modelCatalog: "模型目录",
      openCatalog: "打开目录",
      openAiHttp: "OpenAI HTTP",
      cliRuntime: "CLI 运行时",
      chatCapableChip: "支持聊天",
      streaming: "流式输出",
      selectedProvider: "当前运行时",
      selectedSummary: "运行时摘要",
      selectedDescription: "聚焦查看当前选中 provider 的传输、健康和模型目录状态。",
      selectionHint: "选择左侧任意 provider 卡片即可查看对应摘要。",
      statusLabel: "健康状态",
      transportLabel: "传输方式",
      capabilitiesLabel: "能力",
      catalogStateLabel: "目录状态",
      catalogPending: "模型目录尚未加载",
      manageModelsHint: "价格、对外展示名和测试对话都在模型页维护。",
    },
    models: {
      eyebrow: "目录",
      title: "模型目录",
      provider: "Provider",
      noProviders: "当前还没有 provider。请先在服务提供方页面新增。",
      source: "来源",
      exposedAs: (modelId) => `暴露为 ${modelId}`,
      disable: "停用",
      enable: "启用",
      rename: "重命名",
      nativeModel: "原生模型名",
      exposedModelId: "暴露模型 ID",
      addManualModel: "手动新增模型",
      officialPrice: "官方 API 定价",
      noOfficialPrice: "该模型目前没有可用的官方 API 定价快照。",
      pricingSummary: (input, output) => `输入 ${input} · 输出 ${output}`,
      cachedPrice: (value) => `缓存输入 ${value}`,
      pricingTier: (threshold, input, output) => `超过 ${threshold.toLocaleString()} tokens：输入 ${input} · 输出 ${output}`,
      sourceLink: "来源",
      syncedAt: (value) => `同步时间 ${value}`,
      refreshOfficialPricing: "刷新官方价格",
      pricingTargetModel: "价格目标模型",
      inputPrice: "输入价格",
      cachedInputPrice: "缓存输入价格",
      outputPrice: "输出价格",
      highTierInput: "高阶输入价",
      highTierCachedInput: "高阶缓存输入价",
      highTierOutput: "高阶输出价",
      highTierThreshold: "高阶阈值 tokens",
      pricingNotes: "价格备注",
      savePricingOverride: "保存价格覆盖",
      overview: "概览",
      currentModel: "当前模型",
      currentStatus: "当前状态",
      pricingSource: "价格来源",
      syncedLabel: "价格同步",
      totalModels: "模型总数",
      activeModels: "启用模型",
      manualModels: "手工条目",
      searchModels: "搜索模型",
      filterAll: "全部",
      filterEnabled: "已启用",
      filterDisabled: "已停用",
      noMatches: "当前搜索或筛选下没有匹配模型。",
      selectedLabel: "已选中",
      exposureWorkspace: "暴露控制",
      pricingWorkspace: "价格工作区",
      validationWorkspace: "验证控制台",
      selectModelHint: "选择左侧模型行后，可直接在右侧重命名、调价和测试。",
      saving: "保存中",
      saved: "已保存",
      testChat: "测试对话",
      testPromptPlaceholder: "测试这个模型",
      testReady: "可以测试",
      testRunning: "正在测试模型",
      testFailed: "测试失败",
      emptyResponse: "模型没有返回可见文本。",
      streamResponse: "流式测试",
      cancelStream: "取消流式",
      testCancelled: "已取消流式输出",
      sendTestMessage: "发送测试消息",
      noTestMessages: "还没有测试消息。",
      testerUser: "你",
      testerModel: "模型",
    },
    usage: {
      eyebrow: "活跃度",
      title: "用量",
      recentKeyActivity: "最近密钥活跃度",
      topProvidersModels: "热门 provider / 模型",
      noKeys: "暂无 API Key。",
      noAttributedUsage: "暂无带归因的用量。",
      noModelActivity: "暂无模型活动。",
      providers: "Provider",
      models: "模型",
      requestsLimited: (requests, limited) => `${requests} 次请求 · ${limited} 次限流`,
      lastUsed: (value) => `最近使用：${value}`,
      totalTrackedKeys: "追踪中的密钥",
      trackedKeyCount: (count) => `${count} 个密钥`,
      attributedProviders: "归因 Provider",
      attributedModels: "归因模型",
    },
    settings: {
      eyebrow: "配置",
      title: "平台设置",
      gatewayEndpoint: "网关地址",
      frontendBaseUrl: (url) => `前端地址：${url}`,
      database: (scheme) => `数据库：${scheme}`,
      authentication: "认证方式",
      primarySignIn: "主登录方式：邮箱 + 密码",
      githubOauth: (enabled, enabledText, disabledText) => `GitHub OAuth：${enabled ? enabledText : disabledText}`,
      googleOauth: (enabled, enabledText, disabledText) => `Google OAuth：${enabled ? enabledText : disabledText}`,
      controlPlane: "控制面",
      adminBoundary: "管理边界",
      adminSecretConfigured: (configured, yes, no) => `已配置 Admin Secret：${configured ? yes : no}`,
      authSeparation: "会话认证和网关 API Key 仍然保持分离。",
      interfaceLanguage: "界面语言",
    },
  },
};
