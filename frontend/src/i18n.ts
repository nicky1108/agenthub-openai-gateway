export const LOCALE_STORAGE_KEY = "agenthub-public-gateway-locale";

export type Locale = "zh" | "en";

export type Copy = {
  common: {
    loading: string;
    signIn: string;
    register: string;
    docs: string;
    product: string;
    console: string;
    signOut: string;
    credits: string;
    create: string;
    delete: string;
    providers: string;
    apiKeys: string;
    dashboard: string;
    save: string;
    locale: string;
  };
  public: {
    brand: string;
    heroLabel: string;
    heroTitle: string;
    heroBody: string;
    heroPrimary: string;
    heroSecondary: string;
    metrics: {
      compatibility: string;
      managed: string;
      custom: string;
    };
    featureTitle: string;
    featureManagedTitle: string;
    featureManagedBody: string;
    featureOpsTitle: string;
    featureOpsBody: string;
    featureRouteTitle: string;
    featureRouteBody: string;
    posterTitle: string;
    posterBody: string;
    ctaTitle: string;
    ctaBody: string;
    productTitle: string;
    productLead: string;
    docsTitle: string;
    legalTerms: string;
    legalPrivacy: string;
  };
  auth: {
    loginTitle: string;
    registerTitle: string;
    subtitle: string;
    name: string;
    email: string;
    password: string;
    submitLogin: string;
    submitRegister: string;
    switchToLogin: string;
    switchToRegister: string;
    github: string;
    google: string;
    backHome: string;
  };
  portal: {
    overviewTitle: string;
    overviewBody: string;
    dashboardTitle: string;
    dashboardLead: string;
    apiKeysTitle: string;
    apiKeysLead: string;
    providersTitle: string;
    providersLead: string;
    creditsBalance: string;
    request24h: string;
    request7d: string;
    apiKeyCount: string;
    localProviderCount: string;
    platformTraffic: string;
    customTraffic: string;
    noKeys: string;
    noProviders: string;
    keyReveal: string;
    keyName: string;
    keyLimitMinute: string;
    keyLimitHour: string;
    keyLimitDay: string;
    keyLimits: string;
    unlimited: string;
    providerName: string;
    providerUrl: string;
    providerSecret: string;
    docsShortcut: string;
    routingCardTitle: string;
    routingCardBody: string;
  };
  docs: {
    title: string;
    lead: string;
    authTitle: string;
    modelsTitle: string;
    chatTitle: string;
    routingTitle: string;
    routingBody: string;
  };
  legal: {
    termsTitle: string;
    privacyTitle: string;
    body: string;
  };
};

export const messages: Record<Locale, Copy> = {
  zh: {
    common: {
      loading: "正在连接服务…",
      signIn: "登录",
      register: "注册",
      docs: "文档",
      product: "产品",
      console: "控制台",
      signOut: "退出登录",
      credits: "信用点",
      create: "创建",
      delete: "删除",
      providers: "模型提供商",
      apiKeys: "API Keys",
      dashboard: "总览",
      save: "保存",
      locale: "English",
    },
    public: {
      brand: "AgentHub Public Gateway",
      heroLabel: "公网 AI 网关",
      heroTitle: "统一 AI 模型接入的标准 API。",
      heroBody:
        "AgentHub Public Gateway 把平台模型、自定义 Provider、API Key 和客户控制台整理成一套可试用、可上线的 OpenAI 兼容入口。",
      heroPrimary: "进入控制台",
      heroSecondary: "查看接入文档",
      metrics: {
        compatibility: "OpenAI 兼容接口",
        managed: "平台托管模型",
        custom: "自定义 Provider",
      },
      featureTitle: "为什么外部客户愿意直接接入",
      featureManagedTitle: "平台托管与自带 Provider 共存",
      featureManagedBody: "平台模型按信用点计费，自定义 Provider 保留独立额度，账单边界清晰。",
      featureOpsTitle: "从第一天就是公网产品面",
      featureOpsBody: "官网、登录、控制台、API Keys、Provider 管理都在同一套客户界面里闭环。",
      featureRouteTitle: "路由透明，不靠猜",
      featureRouteBody: "平台模型和自定义模型都暴露为稳定的 namespaced model id，客户端不用额外切 endpoint。",
      posterTitle: "把多家模型能力统一成客户可接入、可管理的 API。",
      posterBody: "一套地址、一组 API Key、一个控制台，覆盖模型调用、用量追踪和 Provider 管理。",
      ctaTitle: "先跑通接入，再决定扩展计费和组织体系。",
      ctaBody: "从模型列表到流式对话都保持 OpenAI 兼容，客户可以直接用熟悉的 SDK 接入。",
      productTitle: "产品结构",
      productLead: "通过一个 OpenAI 兼容入口调用平台模型或自定义 Provider，并在控制台管理 Key、用量与信用点。",
      docsTitle: "快速接入",
      legalTerms: "服务条款",
      legalPrivacy: "隐私政策",
    },
    auth: {
      loginTitle: "登录公网控制台",
      registerTitle: "创建公网客户账号",
      subtitle: "邮箱密码和第三方登录都统一回到同一套控制台会话。",
      name: "显示名称",
      email: "邮箱",
      password: "密码",
      submitLogin: "登录",
      submitRegister: "注册",
      switchToLogin: "已有账号？去登录",
      switchToRegister: "还没有账号？去注册",
      github: "使用 GitHub 登录",
      google: "使用 Google 登录",
      backHome: "返回首页",
    },
    portal: {
      overviewTitle: "客户控制台",
      overviewBody: "看 credits、调用量、API Keys，以及自定义 provider 的运行状态。",
      dashboardTitle: "Dashboard",
      dashboardLead: "查看信用点、API Key、调用量和 Provider 状态。",
      apiKeysTitle: "API Key 管理",
      apiKeysLead: "创建、复制一次性明文、撤销、查看最近使用情况。",
      providersTitle: "自定义 Provider",
      providersLead: "接入你已有的模型服务，统一生成可调用的模型 ID。",
      creditsBalance: "当前信用点余额",
      request24h: "24 小时请求",
      request7d: "7 天请求",
      apiKeyCount: "API Key 数量",
      localProviderCount: "自定义 Provider 数量",
      platformTraffic: "平台模型流量",
      customTraffic: "自定义流量",
      noKeys: "还没有 API Key。",
      noProviders: "还没有自定义 Provider。",
      keyReveal: "新 Key 只展示这一次，请立即保存。",
      keyName: "Key 名称",
      keyLimitMinute: "每分钟限额",
      keyLimitHour: "每小时限额",
      keyLimitDay: "每天限额",
      keyLimits: "限额",
      unlimited: "不限",
      providerName: "Provider 名称",
      providerUrl: "Provider Base URL",
      providerSecret: "Provider API Key",
      docsShortcut: "查看接入文档",
      routingCardTitle: "路由规则",
      routingCardBody: "平台模型和自定义 Provider 都通过同一个 OpenAI 兼容接口调用，客户端只需要切换模型 ID。",
    },
    docs: {
      title: "接入文档",
      lead: "用一个 Base URL 完成鉴权、列出模型、发起非流式或流式对话。",
      authTitle: "认证",
      modelsTitle: "列出模型",
      chatTitle: "发送一次非流式对话",
      routingTitle: "模型命名规则",
      routingBody:
        "平台模型和自定义模型都会用 namespaced model id 暴露。自定义 provider 的默认模型使用 `provider-slug:default`。",
    },
    legal: {
      termsTitle: "服务条款",
      privacyTitle: "隐私政策",
      body:
        "我们只处理提供网关服务所需的账户、API Key、调用用量和 Provider 配置数据。",
    },
  },
  en: {
    common: {
      loading: "Connecting to the service…",
      signIn: "Sign In",
      register: "Register",
      docs: "Docs",
      product: "Product",
      console: "Console",
      signOut: "Sign Out",
      credits: "Credits",
      create: "Create",
      delete: "Delete",
      providers: "Providers",
      apiKeys: "API Keys",
      dashboard: "Overview",
      save: "Save",
      locale: "中文",
    },
    public: {
      brand: "AgentHub Public Gateway",
      heroLabel: "Public AI Gateway",
      heroTitle: "A standard API for unified AI model access.",
      heroBody:
        "AgentHub Public Gateway packages managed models, custom providers, API keys, and the customer console into one testable, OpenAI-compatible entrypoint.",
      heroPrimary: "Open Console",
      heroSecondary: "Read Docs",
      metrics: {
        compatibility: "OpenAI-compatible API",
        managed: "Managed Platform Models",
        custom: "Custom Providers",
      },
      featureTitle: "Why external customers can connect directly",
      featureManagedTitle: "Managed and bring-your-own can coexist",
      featureManagedBody: "Managed models use credits. Custom providers keep their own quota and billing boundary.",
      featureOpsTitle: "A real public product surface",
      featureOpsBody: "Website, auth, dashboard, API keys, and provider management all sit inside one customer-facing product shell.",
      featureRouteTitle: "Routing is explicit",
      featureRouteBody: "Platform and custom models are both exposed as stable namespaced model IDs, so clients do not need multiple endpoints.",
      posterTitle: "Unify multiple model sources into one customer-ready API.",
      posterBody: "One base URL, one API key workflow, and one console for model calls, usage, and provider management.",
      ctaTitle: "Ship the customer loop first, expand billing and org controls later.",
      ctaBody: "Model listing, non-streaming chat, and streaming chat stay OpenAI-compatible so customers can keep their existing SDKs.",
      productTitle: "Product Shape",
      productLead: "Call managed models or custom providers through one OpenAI-compatible endpoint, then manage keys, usage, and credits in the console.",
      docsTitle: "Quickstart",
      legalTerms: "Terms",
      legalPrivacy: "Privacy",
    },
    auth: {
      loginTitle: "Sign in to the public console",
      registerTitle: "Create your public customer account",
      subtitle: "Email/password and third-party auth both land in the same customer console session.",
      name: "Display Name",
      email: "Email",
      password: "Password",
      submitLogin: "Sign In",
      submitRegister: "Create Account",
      switchToLogin: "Already have an account? Sign in",
      switchToRegister: "Need an account? Register",
      github: "Continue with GitHub",
      google: "Continue with Google",
      backHome: "Back to Home",
    },
    portal: {
      overviewTitle: "Public Customer Console",
      overviewBody: "Track credits, request volume, API keys, and your own provider runtime from one place.",
      dashboardTitle: "Dashboard",
      dashboardLead: "Track credits, API keys, request volume, and provider status.",
      apiKeysTitle: "API Key Management",
      apiKeysLead: "Create, reveal once, revoke, and inspect recent key activity.",
      providersTitle: "Custom Providers",
      providersLead: "Connect your existing model service and receive stable model IDs for API calls.",
      creditsBalance: "Credit Balance",
      request24h: "Requests · 24h",
      request7d: "Requests · 7d",
      apiKeyCount: "API Key Count",
      localProviderCount: "Custom Provider Count",
      platformTraffic: "Managed Traffic",
      customTraffic: "Custom Traffic",
      noKeys: "No API keys yet.",
      noProviders: "No custom providers yet.",
      keyReveal: "A new key is shown once only. Store it now.",
      keyName: "Key Name",
      keyLimitMinute: "Per-minute limit",
      keyLimitHour: "Per-hour limit",
      keyLimitDay: "Per-day limit",
      keyLimits: "Limits",
      unlimited: "Unlimited",
      providerName: "Provider Name",
      providerUrl: "Provider Base URL",
      providerSecret: "Provider API Key",
      docsShortcut: "Open Docs",
      routingCardTitle: "Routing Rule",
      routingCardBody: "Managed models and custom providers are both called through one OpenAI-compatible API. Clients only switch the model ID.",
    },
    docs: {
      title: "Integration Docs",
      lead: "Use one base URL to authenticate, list models, and send non-streaming or streaming chat completions.",
      authTitle: "Authentication",
      modelsTitle: "List Models",
      chatTitle: "Send One Non-Streaming Chat Completion",
      routingTitle: "Model Naming",
      routingBody:
        "Managed and custom models both use namespaced model IDs. The default custom provider model is exposed as `provider-slug:default`.",
    },
    legal: {
      termsTitle: "Terms",
      privacyTitle: "Privacy",
      body:
        "We process account, API key, usage, and provider configuration data only as needed to deliver the gateway service.",
    },
  },
} as const;
