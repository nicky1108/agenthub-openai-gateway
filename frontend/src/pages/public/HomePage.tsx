import type { AuthAccount } from "../../api";
import type { Copy, Locale } from "../../i18n";

type HomePageProps = {
  authUser: AuthAccount | null;
  copy: Copy;
  locale: Locale;
  onNavigate: (pathname: string) => void;
  onToggleLocale: () => void;
};

function PublicHeader({ authUser, copy, locale, onNavigate, onToggleLocale }: HomePageProps) {
  return (
    <header className="site-header">
      <button className="site-logo" onClick={() => onNavigate("/")}>
        <span className="site-logo__mark" />
        <span>{copy.public.brand}</span>
      </button>
      <nav className="site-nav">
        <button onClick={() => onNavigate("/product")}>{copy.common.product}</button>
        <button onClick={() => onNavigate("/docs")}>{copy.common.docs}</button>
        <button onClick={() => onNavigate("/legal/terms")}>{copy.public.legalTerms}</button>
        <button onClick={() => onNavigate("/legal/privacy")}>{copy.public.legalPrivacy}</button>
      </nav>
      <div className="site-header__actions">
        <button className="locale-switch" onClick={onToggleLocale}>
          {copy.common.locale}
        </button>
        <button
          className="ghost-action"
          onClick={() => onNavigate(authUser ? "/portal" : "/login")}
        >
          {authUser ? copy.common.console : copy.common.signIn}
        </button>
      </div>
    </header>
  );
}

export function HomePage(props: HomePageProps) {
  const { authUser, copy, locale, onNavigate } = props;
  const proofPoints =
    locale === "zh"
      ? ["OpenAI 标准接口", "平台模型 + 自带 Provider", "客户控制台已闭环"]
      : ["OpenAI-compatible API", "Managed + BYOK providers", "Customer console included"];
  const launchSteps =
    locale === "zh"
      ? [
          ["01", "开通客户账号", "注册后即可在控制台管理 API Key、信用点和 Provider 状态。"],
          ["02", "选择模型来源", "平台模型直接调用，自定义 Provider 使用稳定的 namespaced model id。"],
          ["03", "上线模型调用", "沿用 OpenAI SDK 接入，后续可扩展团队、审计与 SLA。"],
        ]
      : [
          ["01", "Create customer access", "Sign in and manage API keys, credits, and provider status in one console."],
          ["02", "Choose model sources", "Use managed models directly or connect custom providers with stable namespaced model IDs."],
          ["03", "Launch model calls", "Keep OpenAI SDK compatibility, then expand teams, audit, and SLA controls."],
        ];
  const customerOutcomes =
    locale === "zh"
      ? [
          ["标准入口", "一个 base URL 覆盖托管模型和自带模型，不要求客户改多套 SDK。"],
          ["清晰边界", "平台信用点和自定义 Provider 额度分开呈现，账单说明更简单。"],
          ["可演进", "从官网、文档到控制台形成闭环，后续可以自然接入团队和审计能力。"],
        ]
      : [
          ["Standard entrypoint", "One base URL covers managed and BYOK models without multiple SDK paths."],
          ["Clear boundaries", "Managed credits and custom provider quota stay visible without mixing billing models."],
          ["Ready to evolve", "The website, docs, and console form a complete loop that can grow into teams and audit controls."],
        ];

  return (
    <div className="site-shell">
      <PublicHeader {...props} />
      <main>
        <section className="hero-section">
          <div className="hero-copy">
            <div className="eyebrow">{copy.public.heroLabel}</div>
            <h1>{copy.public.heroTitle}</h1>
            <p>{copy.public.heroBody}</p>
            <div className="hero-actions">
              <button className="primary-action" onClick={() => onNavigate(authUser ? "/portal" : "/register")}>
                {authUser ? copy.public.heroPrimary : copy.common.register}
              </button>
              <button className="ghost-action ghost-action--bright" onClick={() => onNavigate("/docs")}>
                {copy.public.heroSecondary}
              </button>
            </div>
            <div className="hero-proof">
              {proofPoints.map((item) => (
                <span key={item}>{item}</span>
              ))}
            </div>
          </div>
          <div className="hero-panel product-preview product-preview--showcase" aria-label="AgentHub product preview">
            <div className="product-preview__topbar">
              <div>
                <span className="status-pill status-pill--ok">Gateway live</span>
                <strong>Customer Console</strong>
              </div>
              <code>https://api.agenthub.dev/v1</code>
            </div>
            <div className="preview-command-center">
              <div className="preview-command-center__metric">
                <span>Requests · 24h</span>
                <strong>128K</strong>
                <small>99.96% routed</small>
              </div>
              <div className="preview-command-center__metric">
                <span>Active keys</span>
                <strong>42</strong>
                <small>8 teams online</small>
              </div>
              <div className="preview-command-center__metric preview-command-center__metric--accent">
                <span>Custom providers</span>
                <strong>17</strong>
                <small>Customer models ready</small>
              </div>
            </div>
            <div className="preview-route-map">
              <div className="preview-route-card preview-route-card--platform">
                <span>Managed model</span>
                <strong>codex:gpt-5.4</strong>
                <small>credits billing</small>
              </div>
              <div className="preview-route-rail">
                <span />
                <span />
                <span />
              </div>
              <div className="preview-route-card">
                <span>Customer provider</span>
                <strong>minimax-cn:MiniMax-M2.7</strong>
                <small>custom quota</small>
              </div>
            </div>
            <div className="preview-activity">
              <div>
                <span>Live request</span>
                <strong>chat.completions → routed in 184ms</strong>
              </div>
              <div className="preview-activity__bar" />
            </div>
            <pre className="hero-code">
              <code>{`curl /v1/chat/completions \\
  -H "Authorization: Bearer $AGENTHUB_KEY" \\
  -d '{"model":"codex:gpt-5.4"}'`}</code>
            </pre>
          </div>
        </section>

        <section className="customer-outcomes">
          {customerOutcomes.map(([title, body]) => (
            <article key={title}>
              <strong>{title}</strong>
              <p>{body}</p>
            </article>
          ))}
        </section>

        <section className="feature-strip feature-strip--product">
          <div className="feature-strip__lead">
            <div className="eyebrow">Product surface</div>
            <h2>{copy.public.featureTitle}</h2>
          </div>
          <article>
            <h3>{copy.public.featureManagedTitle}</h3>
            <p>{copy.public.featureManagedBody}</p>
          </article>
          <article>
            <h3>{copy.public.featureOpsTitle}</h3>
            <p>{copy.public.featureOpsBody}</p>
          </article>
          <article>
            <h3>{copy.public.featureRouteTitle}</h3>
            <p>{copy.public.featureRouteBody}</p>
          </article>
        </section>

        <section className="poster-section">
          <div className="poster-section__copy">
            <div className="eyebrow">Gateway workflow</div>
            <h2>{copy.public.posterTitle}</h2>
            <p>{copy.public.posterBody}</p>
          </div>
          <div className="poster-section__canvas">
            <div className="route-lane">
              <span>Client SDK</span>
              <strong>OpenAI-compatible request</strong>
            </div>
            <div className="route-lane route-lane--gateway">
              <span>Public Gateway</span>
              <strong>namespaced model routing</strong>
            </div>
            <div className="route-lane-grid">
              <div>
                <span>platform</span>
                <strong>Managed Models</strong>
              </div>
              <div>
                <span>custom</span>
                <strong>Customer Providers</strong>
              </div>
            </div>
          </div>
        </section>

        <section className="launch-section">
          <div>
            <div className="eyebrow">Launch path</div>
            <h2>{locale === "zh" ? "从官网到可调用接口，三步完成对外开放。" : "From website to callable API in three deliberate steps."}</h2>
          </div>
          <div className="launch-steps">
            {launchSteps.map(([step, title, body]) => (
              <article key={step}>
                <span>{step}</span>
                <h3>{title}</h3>
                <p>{body}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="cta-section cta-section--product">
          <div>
            <h2>{copy.public.ctaTitle}</h2>
            <p>{copy.public.ctaBody}</p>
          </div>
          <button className="primary-action" onClick={() => onNavigate(authUser ? "/portal" : "/register")}>
            {authUser ? copy.common.console : copy.public.heroPrimary}
          </button>
        </section>
      </main>
    </div>
  );
}
