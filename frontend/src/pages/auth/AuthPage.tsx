import { useState, type FormEvent } from "react";

import {
  loginWithPassword,
  registerWithPassword,
  type AuthAccount,
  type AuthProviderStatus,
} from "../../api";
import type { Copy, Locale } from "../../i18n";

type AuthPageProps = {
  authProviders: AuthProviderStatus;
  copy: Copy;
  locale: Locale;
  mode: "login" | "register";
  onAuthenticated: (account: AuthAccount) => void;
  onNavigate: (pathname: string) => void;
  onToggleLocale: () => void;
};

export function AuthPage({
  authProviders,
  copy,
  locale,
  mode,
  onAuthenticated,
  onNavigate,
  onToggleLocale,
}: AuthPageProps) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const isZh = locale === "zh";
  const authIntro = isZh
    ? "一个账户即可管理 API Key、信用点和模型接入。"
    : "Use one account to manage API keys, credits, and model access.";
  const authBenefits = isZh
    ? ["创建 API Key", "查看信用点与请求量", "接入自定义 Provider"]
    : ["Create API keys", "Track credits and usage", "Connect custom providers"];

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const account =
        mode === "login"
          ? await loginWithPassword({ email, password })
          : await registerWithPassword({ name, email, password });
      onAuthenticated(account);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "request failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-shell">
      <button className="site-logo auth-shell__brand" onClick={() => onNavigate("/")}>
        <span className="site-logo__mark" />
        <span>{copy.public.brand}</span>
      </button>
      <aside className="auth-shell__context">
        <div className="eyebrow">Public gateway</div>
        <h2>{authIntro}</h2>
        <div className="auth-benefit-list">
          {authBenefits.map((item) => (
            <span key={item}>{item}</span>
          ))}
        </div>
      </aside>
      <div className="auth-shell__panel">
        <div className="eyebrow">{mode === "login" ? copy.auth.loginTitle : copy.auth.registerTitle}</div>
        <h1>{mode === "login" ? copy.auth.loginTitle : copy.auth.registerTitle}</h1>
        <p>{copy.auth.subtitle}</p>
        {error ? <div className="inline-error">{error}</div> : null}
        <form className="auth-form" onSubmit={handleSubmit}>
          {mode === "register" ? (
            <label>
              <span>{copy.auth.name}</span>
              <input required value={name} onChange={(event) => setName(event.target.value)} />
            </label>
          ) : null}
          <label>
            <span>{copy.auth.email}</span>
            <input required type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
          </label>
          <label>
            <span>{copy.auth.password}</span>
            <input required type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
          </label>
          <button className="primary-action" disabled={submitting} type="submit">
            {mode === "login" ? copy.auth.submitLogin : copy.auth.submitRegister}
          </button>
        </form>
        <div className="auth-shell__links">
          <button onClick={() => onNavigate(mode === "login" ? "/register" : "/login")}>
            {mode === "login" ? copy.auth.switchToRegister : copy.auth.switchToLogin}
          </button>
          <button onClick={onToggleLocale}>{copy.common.locale}</button>
        </div>
        <div className="auth-shell__oauth">
          {authProviders.github_enabled ? (
            <a className="oauth-link" href="/auth/oauth/github">
              {copy.auth.github}
            </a>
          ) : null}
          {authProviders.google_enabled ? (
            <a className="oauth-link" href="/auth/oauth/google">
              {copy.auth.google}
            </a>
          ) : null}
        </div>
      </div>
    </div>
  );
}
