import { useEffect, useState } from "react";

import {
  getAuthProviders,
  getCurrentAccount,
  type AuthAccount,
  type AuthProviderStatus,
} from "./api";
import { navigate, usePathname } from "./app/router";
import {
  LOCALE_STORAGE_KEY,
  type Locale,
  messages,
} from "./i18n";
import { AdminShell } from "./pages/admin/AdminShell";
import { AuthPage } from "./pages/auth/AuthPage";
import { PortalShell } from "./pages/portal/PortalShell";
import { DocsPage } from "./pages/public/DocsPage";
import { HomePage } from "./pages/public/HomePage";
import { LegalPage } from "./pages/public/LegalPage";
import { ProductPage } from "./pages/public/ProductPage";

export default function App() {
  const pathname = usePathname();
  const [locale, setLocale] = useState<Locale>(() => {
    const stored = globalThis.localStorage?.getItem(LOCALE_STORAGE_KEY);
    return stored === "en" ? "en" : "zh";
  });
  const [authUser, setAuthUser] = useState<AuthAccount | null>(null);
  const [authState, setAuthState] = useState<"loading" | "authenticated" | "unauthenticated">("loading");
  const [authProviders, setAuthProviders] = useState<AuthProviderStatus>({
    email_password_enabled: true,
    github_enabled: false,
    google_enabled: false,
  });

  useEffect(() => {
    globalThis.localStorage?.setItem(LOCALE_STORAGE_KEY, locale);
  }, [locale]);

  useEffect(() => {
    void getAuthProviders()
      .then(setAuthProviders)
      .catch(() => {
        setAuthProviders({
          email_password_enabled: true,
          github_enabled: false,
          google_enabled: false,
        });
      });

    void getCurrentAccount()
      .then((account) => {
        setAuthUser(account);
        setAuthState("authenticated");
      })
      .catch(() => {
        setAuthUser(null);
        setAuthState("unauthenticated");
      });
  }, []);

  useEffect(() => {
    if (authState === "loading") {
      return;
    }
    if (pathname.startsWith("/portal") && authState === "unauthenticated") {
      navigate("/login", { replace: true });
      return;
    }
    if ((pathname === "/login" || pathname === "/register") && authState === "authenticated") {
      navigate("/portal", { replace: true });
    }
  }, [authState, pathname]);

  const copy = messages[locale];

  if (authState === "loading") {
    return (
      <div className="app-loading">
        <div className="app-loading__panel">
          <div className="app-loading__pulse" />
          <p>{copy.common.loading}</p>
        </div>
      </div>
    );
  }

  if (pathname.startsWith("/admin")) {
    if (authState === "unauthenticated") {
      navigate("/login", { replace: true });
      return null;
    }
    if (!authUser?.is_admin) {
      navigate("/portal", { replace: true });
      return null;
    }
    return (
      <AdminShell
        adminSecret=""
        locale={locale}
        onLogout={() => {
          setAuthUser(null);
          setAuthState("unauthenticated");
          navigate("/", { replace: true });
        }}
      />
    );
  }

  if (pathname === "/login" || pathname === "/register") {
    return (
      <AuthPage
        authProviders={authProviders}
        copy={copy}
        locale={locale}
        mode={pathname === "/register" ? "register" : "login"}
        onAuthenticated={(account) => {
          setAuthUser(account);
          setAuthState("authenticated");
          navigate("/portal", { replace: true });
        }}
        onNavigate={navigate}
        onToggleLocale={() => setLocale(locale === "zh" ? "en" : "zh")}
      />
    );
  }

  if (pathname.startsWith("/portal")) {
    return (
      <PortalShell
        copy={copy}
        locale={locale}
        onLogout={() => {
          setAuthUser(null);
          setAuthState("unauthenticated");
          navigate("/", { replace: true });
        }}
        onNavigate={navigate}
        onToggleLocale={() => setLocale(locale === "zh" ? "en" : "zh")}
        pathname={pathname}
        user={authUser}
      />
    );
  }

  if (pathname === "/product") {
    return (
      <ProductPage
        authUser={authUser}
        copy={copy}
        locale={locale}
        onNavigate={navigate}
        onToggleLocale={() => setLocale(locale === "zh" ? "en" : "zh")}
      />
    );
  }

  if (pathname === "/docs") {
    return (
      <DocsPage
        authUser={authUser}
        copy={copy}
        locale={locale}
        onNavigate={navigate}
        onToggleLocale={() => setLocale(locale === "zh" ? "en" : "zh")}
      />
    );
  }

  if (pathname === "/legal/terms") {
    return (
      <LegalPage
        authUser={authUser}
        copy={copy}
        locale={locale}
        onNavigate={navigate}
        onToggleLocale={() => setLocale(locale === "zh" ? "en" : "zh")}
        variant="terms"
      />
    );
  }

  if (pathname === "/legal/privacy") {
    return (
      <LegalPage
        authUser={authUser}
        copy={copy}
        locale={locale}
        onNavigate={navigate}
        onToggleLocale={() => setLocale(locale === "zh" ? "en" : "zh")}
        variant="privacy"
      />
    );
  }

  return (
    <HomePage
      authUser={authUser}
      copy={copy}
      locale={locale}
      onNavigate={navigate}
      onToggleLocale={() => setLocale(locale === "zh" ? "en" : "zh")}
    />
  );
}
