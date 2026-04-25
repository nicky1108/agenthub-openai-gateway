import type { AuthAccount } from "./api";
import type { Locale } from "./i18n";

type PublicRoute = "home" | "product" | "docs";

type PublicSiteProps = {
  authUser: AuthAccount | null;
  locale: Locale;
  route: PublicRoute;
  onNavigate: (path: string) => void;
  onToggleLocale: () => void;
};

const copy = {
  en: {
    brand: "AgentHub",
    product: "Product",
    docs: "Docs",
    signIn: "Sign in",
    register: "Create account",
    console: "User portal",
    admin: "Admin console",
    locale: "中文",
    heroTitle: "One OpenAI-compatible gateway for managed and custom models.",
    heroBody:
      "Run Codex CLI and Gemini CLI on your server, expose a public API, and let customers add their own OpenAI-compatible or Anthropic-compatible providers.",
    primary: "Open user portal",
    secondary: "Read API docs",
    proof: ["Single /v1 API base", "Customer API keys", "Custom providers", "Local usage ledger"],
    productTitle: "Product surface",
    productLead:
      "AgentHub keeps the operator admin console separate from the customer portal while both use the same local gateway database.",
    docsTitle: "API docs",
    docsLead: "Use the same OpenAI SDK path for platform models and customer-added providers.",
  },
  zh: {
    brand: "AgentHub",
    product: "产品",
    docs: "文档",
    signIn: "登录",
    register: "注册账号",
    console: "用户门户",
    admin: "管理后台",
    locale: "English",
    heroTitle: "一个 OpenAI 兼容入口，同时服务平台模型和自定义模型。",
    heroBody:
      "只需要在服务器安装 Codex CLI 和 Gemini CLI，就能对外提供 API Gateway，并允许用户添加 OpenAI 兼容或 Anthropic 兼容服务商。",
    primary: "进入用户门户",
    secondary: "查看 API 文档",
    proof: ["统一 /v1 API Base", "用户自助 API Key", "自定义模型服务商", "本地用量账本"],
    productTitle: "产品形态",
    productLead:
      "AgentHub 将你的运营管理后台和客户自助门户分开，但两者共享同一个本地网关数据库。",
    docsTitle: "API 文档",
    docsLead: "平台模型和用户添加的 Provider 都走同一套 OpenAI SDK 接入路径。",
  },
} satisfies Record<Locale, Record<string, string | string[]>>;

function PublicHeader({ authUser, locale, onNavigate, onToggleLocale }: PublicSiteProps) {
  const t = copy[locale];
  return (
    <header className="public-header">
      <button className="public-logo" type="button" onClick={() => onNavigate("/")}>
        <span className="public-logo-mark">AG</span>
        <span>{t.brand as string}</span>
      </button>
      <nav className="public-nav" aria-label="Public navigation">
        <button type="button" onClick={() => onNavigate("/product")}>{t.product as string}</button>
        <button type="button" onClick={() => onNavigate("/docs")}>{t.docs as string}</button>
        <button type="button" onClick={() => onNavigate("/admin")}>{t.admin as string}</button>
      </nav>
      <div className="public-actions">
        <button type="button" onClick={onToggleLocale}>{t.locale as string}</button>
        <button type="button" onClick={() => onNavigate(authUser ? "/portal" : "/login")}>
          {authUser ? (t.console as string) : (t.signIn as string)}
        </button>
        {!authUser ? <button type="button" onClick={() => onNavigate("/register")}>{t.register as string}</button> : null}
      </div>
    </header>
  );
}

function Home({ locale, onNavigate }: Pick<PublicSiteProps, "locale" | "onNavigate">) {
  const t = copy[locale];
  const proof = t.proof as string[];
  return (
    <main className="public-main">
      <section className="public-hero">
        <div>
          <span className="section-eyebrow">AgentHub Gateway</span>
          <h1>{t.heroTitle as string}</h1>
          <p>{t.heroBody as string}</p>
          <div className="public-hero-actions">
            <button type="button" onClick={() => onNavigate("/portal")}>{t.primary as string}</button>
            <button type="button" onClick={() => onNavigate("/docs")}>{t.secondary as string}</button>
          </div>
          <div className="public-proof">
            {proof.map((item) => <span key={item}>{item}</span>)}
          </div>
        </div>
        <aside className="public-terminal" aria-label="API request example">
          <strong>https://your-domain.example/v1</strong>
          <pre>{`curl /v1/chat/completions \\
  -H "Authorization: Bearer $AGENTHUB_KEY" \\
  -d '{"model":"codex:gpt-5.4"}'`}</pre>
        </aside>
      </section>
    </main>
  );
}

function Product({ locale }: Pick<PublicSiteProps, "locale">) {
  const t = copy[locale];
  return (
    <main className="public-main">
      <section className="public-page-card">
        <span className="section-eyebrow">{t.productTitle as string}</span>
        <h1>{t.productLead as string}</h1>
        <div className="public-grid">
          <article>
            <strong>Operator admin</strong>
            <p>Provider registry, accounts, credits, pricing, usage, and runtime health stay under `/admin`.</p>
          </article>
          <article>
            <strong>Customer portal</strong>
            <p>Customer API keys, balance, provider presets, custom models, and API examples stay under `/portal`.</p>
          </article>
          <article>
            <strong>Unified API</strong>
            <p>`/v1/models` and `/v1/chat/completions` expose platform and customer custom models.</p>
          </article>
        </div>
      </section>
    </main>
  );
}

function Docs({ locale }: Pick<PublicSiteProps, "locale">) {
  const t = copy[locale];
  return (
    <main className="public-main">
      <section className="public-page-card">
        <span className="section-eyebrow">{t.docsTitle as string}</span>
        <h1>{t.docsLead as string}</h1>
        <div className="api-example-block">
          <span>Base URL</span>
          <code>https://your-domain.example/v1</code>
        </div>
        <div className="api-example-block">
          <span>List models</span>
          <pre>{`curl https://your-domain.example/v1/models \\
  -H "Authorization: Bearer $AGENTHUB_KEY"`}</pre>
        </div>
        <div className="api-example-block">
          <span>Chat completions</span>
          <pre>{`curl https://your-domain.example/v1/chat/completions \\
  -H "Authorization: Bearer $AGENTHUB_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"model":"provider-slug:model-id","messages":[{"role":"user","content":"Reply with only OK"}]}'`}</pre>
        </div>
      </section>
    </main>
  );
}

export function PublicSite(props: PublicSiteProps) {
  return (
    <div className="public-shell">
      <PublicHeader {...props} />
      {props.route === "product" ? <Product locale={props.locale} /> : null}
      {props.route === "docs" ? <Docs locale={props.locale} /> : null}
      {props.route === "home" ? <Home locale={props.locale} onNavigate={props.onNavigate} /> : null}
    </div>
  );
}
