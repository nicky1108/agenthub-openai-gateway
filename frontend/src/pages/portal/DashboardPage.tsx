import type { DashboardSummary } from "../../api";
import type { Copy } from "../../i18n";

type DashboardPageProps = {
  apiKeyCount: number;
  copy: Copy;
  dashboard: DashboardSummary | null;
  onRetrySync: () => Promise<void>;
  providerCount: number;
  syncRetrying: boolean;
};

export function DashboardPage({
  apiKeyCount,
  copy,
  dashboard,
  onRetrySync,
  providerCount,
  syncRetrying,
}: DashboardPageProps) {
  const credits = dashboard?.credits_balance ?? 0;
  const requests24h = dashboard?.request_count_24h ?? 0;
  const requests7d = dashboard?.request_count_7d ?? 0;
  const platformTraffic = dashboard?.platform_requests_24h ?? 0;
  const customTraffic = dashboard?.custom_requests_24h ?? 0;
  const accountSync = dashboard?.account_sync;
  const localMirror = accountSync?.local_mirror;
  const totalTraffic = platformTraffic + customTraffic;
  const platformShare = totalTraffic > 0 ? Math.round((platformTraffic / totalTraffic) * 100) : 0;
  const customShare = totalTraffic > 0 ? 100 - platformShare : 0;
  const pendingSync = accountSync?.sync_queue?.pending ?? 0;
  const failedSync = accountSync?.sync_queue?.failed ?? 0;
  const syncHealthy = Boolean(accountSync && failedSync === 0 && pendingSync === 0);
  const accountStatusLabel = !accountSync ? "Preparing" : syncHealthy ? "Ready" : "Needs review";
  const accountStatusBody = !accountSync
    ? "Your workspace is still being prepared."
    : syncHealthy
      ? "API keys, credits, and model access are available."
      : `${pendingSync} updates in progress · ${failedSync} need review`;
  const modelAccessLabel = localMirror || syncHealthy ? "Available" : "Checking";
  const modelAccessBody = localMirror || syncHealthy
    ? `${providerCount} custom provider${providerCount === 1 ? "" : "s"} connected`
    : "Managed model access is being verified.";

  return (
    <section className="portal-section">
      <div className="portal-section__header">
        <div>
          <div className="eyebrow">{copy.portal.dashboardTitle}</div>
          <h1>{copy.portal.dashboardTitle}</h1>
          <p>{copy.portal.dashboardLead}</p>
        </div>
      </div>
      <div className="gateway-health-grid">
        <article className="health-card health-card--ok">
          <span>Gateway API</span>
          <strong>OpenAI compatible</strong>
          <small>/v1/models · /v1/chat/completions</small>
        </article>
        <article className={syncHealthy ? "health-card health-card--ok" : "health-card health-card--warning"}>
          <span>Account status</span>
          <strong>{accountStatusLabel}</strong>
          <small>{accountStatusBody}</small>
        </article>
        <article className={localMirror || syncHealthy ? "health-card health-card--ok" : "health-card"}>
          <span>Model access</span>
          <strong>{modelAccessLabel}</strong>
          <small>{modelAccessBody}</small>
        </article>
      </div>
      <div className="metric-grid">
        <article className="metric-card">
          <span>{copy.portal.creditsBalance}</span>
          <strong>{credits.toFixed(2)}</strong>
          <small>Manual credits balance</small>
        </article>
        <article className="metric-card">
          <span>{copy.portal.apiKeyCount}</span>
          <strong>{apiKeyCount}</strong>
          <small>Keys accepted by this gateway</small>
        </article>
        <article className="metric-card">
          <span>{copy.portal.localProviderCount}</span>
          <strong>{providerCount}</strong>
          <small>Bring-your-own providers</small>
        </article>
        <article className="metric-card">
          <span>{copy.portal.request24h}</span>
          <strong>{requests24h}</strong>
          <small>Latest 24-hour activity</small>
        </article>
        <article className="metric-card">
          <span>{copy.portal.request7d}</span>
          <strong>{requests7d}</strong>
          <small>Seven-day total</small>
        </article>
      </div>
      <div className="detail-grid">
        <article className="detail-panel traffic-panel">
          <h3>{copy.portal.platformTraffic}</h3>
          <p>{platformTraffic}</p>
          <div className="traffic-bar" aria-label="platform traffic share">
            <span style={{ width: `${platformShare}%` }} />
          </div>
          <small>{platformShare}% of 24h traffic</small>
        </article>
        <article className="detail-panel traffic-panel">
          <h3>{copy.portal.customTraffic}</h3>
          <p>{customTraffic}</p>
          <div className="traffic-bar traffic-bar--custom" aria-label="custom traffic share">
            <span style={{ width: `${customShare}%` }} />
          </div>
          <small>{customShare}% of 24h traffic</small>
        </article>
        {accountSync ? (
          <article className="detail-panel detail-panel--sync">
            <div className="detail-panel__title-row">
              <div>
                <h3>Workspace status</h3>
                <p>{accountSync.linked ? "Your account is connected and ready to serve requests." : "Your workspace is still being finalized."}</p>
              </div>
              <span className={syncHealthy ? "status-pill status-pill--ok" : "status-pill status-pill--warning"}>
                {syncHealthy ? "Ready" : "Review"}
              </span>
            </div>
            <div className="sync-summary">
              <span>API keys <strong>{apiKeyCount}</strong></span>
              <span>Custom providers <strong>{providerCount}</strong></span>
              <span>Updates pending <strong>{pendingSync}</strong></span>
            </div>
            <div className="detail-panel__meta">
              <span>{syncHealthy ? "Everything required for API access is in place." : "A recent account change is still being applied."}</span>
              <span>{failedSync > 0 ? `${failedSync} update${failedSync > 1 ? "s" : ""} need${failedSync > 1 ? "" : "s"} manual review.` : "No failed updates detected."}</span>
              <span>
                {localMirror
                  ? `${localMirror.api_keys.length} key cop${localMirror.api_keys.length === 1 ? "y is" : "ies are"} active for managed model access.`
                  : "Managed model access is still being verified."}
              </span>
            </div>
            <div className="detail-panel__actions">
              <button
                className="ghost-action ghost-action--bright"
                disabled={syncRetrying}
                onClick={() => void onRetrySync()}
              >
                {syncRetrying ? "Refreshing..." : "Refresh status"}
              </button>
            </div>
          </article>
        ) : null}
        <article className="detail-panel detail-panel--wide">
          <h3>{copy.portal.routingCardTitle}</h3>
          <p>{copy.portal.routingCardBody}</p>
          <div className="route-summary">
            <span>{"platform:model -> managed service"}</span>
            <span>{"provider:model -> your provider"}</span>
          </div>
        </article>
      </div>
    </section>
  );
}
