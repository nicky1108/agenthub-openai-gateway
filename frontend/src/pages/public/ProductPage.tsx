import type { AuthAccount } from "../../api";
import type { Copy, Locale } from "../../i18n";

type ProductPageProps = {
  authUser: AuthAccount | null;
  copy: Copy;
  locale: Locale;
  onNavigate: (pathname: string) => void;
  onToggleLocale: () => void;
};

export function ProductPage({ authUser, copy, locale, onNavigate, onToggleLocale }: ProductPageProps) {
  const isZh = locale === "zh";

  return (
    <div className="site-shell site-shell--subpage">
      <header className="site-header">
        <button className="site-logo" onClick={() => onNavigate("/")}>
          <span className="site-logo__mark" />
          <span>{copy.public.brand}</span>
        </button>
        <div className="site-header__actions">
          <button className="locale-switch" onClick={onToggleLocale}>
            {copy.common.locale}
          </button>
          {authUser?.is_admin ? (
            <button className="ghost-action" onClick={() => onNavigate("/admin")}>
              {copy.common.admin}
            </button>
          ) : null}
          <button className="ghost-action" onClick={() => onNavigate(authUser ? "/portal" : "/login")}>
            {authUser ? copy.common.console : copy.common.signIn}
          </button>
        </div>
      </header>
      <main className="subpage-body">
        <section className="subpage-intro">
          <div className="eyebrow">{copy.public.productTitle}</div>
          <h1>{copy.public.heroTitle}</h1>
          <p>{copy.public.productLead}</p>
        </section>
        <section className="comparison-section">
          <div>
            <div className="eyebrow">{isZh ? "模型路由" : "Model routing"}</div>
            <h2>{isZh ? "两类模型，一个标准入口。" : "Two model sources, one standard endpoint."}</h2>
          </div>
          <div className="comparison-table" role="table" aria-label="platform and custom model comparison">
            <div role="row">
              <strong role="cell">{isZh ? "能力" : "Capability"}</strong>
              <strong role="cell">{isZh ? "平台模型" : "Managed models"}</strong>
              <strong role="cell">{isZh ? "自定义 Provider" : "Custom providers"}</strong>
            </div>
            <div role="row">
              <span role="cell">{isZh ? "模型 ID" : "Model ID"}</span>
              <span role="cell"><code>codex:gpt-5.4</code></span>
              <span role="cell"><code>provider-slug:model</code></span>
            </div>
            <div role="row">
              <span role="cell">{isZh ? "计费方式" : "Billing"}</span>
              <span role="cell">{isZh ? "信用点" : "Credits"}</span>
              <span role="cell">{isZh ? "自定义 Provider 自行结算" : "Your provider account"}</span>
            </div>
            <div role="row">
              <span role="cell">{isZh ? "适合场景" : "Best for"}</span>
              <span role="cell">{isZh ? "快速接入、统一管理" : "Fast onboarding and unified management"}</span>
              <span role="cell">{isZh ? "已有额度、专属模型、区域模型" : "Existing quota, private models, or regional endpoints"}</span>
            </div>
          </div>
        </section>
        <section className="detail-grid">
          <article>
            <h3>{copy.public.featureManagedTitle}</h3>
            <p>{copy.public.featureManagedBody}</p>
          </article>
          <article>
            <h3>{copy.public.featureRouteTitle}</h3>
            <p>{copy.public.featureRouteBody}</p>
          </article>
          <article>
            <h3>{copy.public.featureOpsTitle}</h3>
            <p>{copy.public.featureOpsBody}</p>
          </article>
          <article>
            <h3>{copy.portal.routingCardTitle}</h3>
            <p>{copy.portal.routingCardBody}</p>
          </article>
        </section>
      </main>
    </div>
  );
}
