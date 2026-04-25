import type { AuthAccount } from "../../api";
import type { Copy, Locale } from "../../i18n";

type LegalPageProps = {
  authUser: AuthAccount | null;
  copy: Copy;
  locale: Locale;
  onNavigate: (pathname: string) => void;
  onToggleLocale: () => void;
  variant: "terms" | "privacy";
};

export function LegalPage({ authUser, copy, onNavigate, onToggleLocale, variant }: LegalPageProps) {
  const title = variant === "terms" ? copy.legal.termsTitle : copy.legal.privacyTitle;

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
          <button className="ghost-action" onClick={() => onNavigate(authUser ? "/portal" : "/login")}>
            {authUser ? copy.common.console : copy.common.signIn}
          </button>
        </div>
      </header>
      <main className="subpage-body legal-body">
        <section className="subpage-intro">
          <div className="eyebrow">{title}</div>
          <h1>{title}</h1>
          <p>{copy.legal.body}</p>
        </section>
      </main>
    </div>
  );
}
