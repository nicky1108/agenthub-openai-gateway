import { startTransition, useEffect, useState } from "react";

type NavigateOptions = {
  replace?: boolean;
};

export function navigate(pathname: string, options: NavigateOptions = {}): void {
  const current = window.location.pathname || "/";
  if (current === pathname) {
    return;
  }
  startTransition(() => {
    if (options.replace) {
      window.history.replaceState({}, "", pathname);
    } else {
      window.history.pushState({}, "", pathname);
    }
    window.dispatchEvent(new PopStateEvent("popstate"));
  });
}

export function usePathname(): string {
  const [pathname, setPathname] = useState(window.location.pathname || "/");

  useEffect(() => {
    const handleChange = () => setPathname(window.location.pathname || "/");
    window.addEventListener("popstate", handleChange);
    return () => window.removeEventListener("popstate", handleChange);
  }, []);

  return pathname;
}
