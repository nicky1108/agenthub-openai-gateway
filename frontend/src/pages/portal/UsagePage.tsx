import type { ApiKeyRecord, PortalUsageRecord, PortalUsageRecordsPage } from "../../api";
import type { Locale } from "../../i18n";

type UsagePageProps = {
  apiKeys: ApiKeyRecord[];
  locale: Locale;
  onKeyFilterChange: (nextKeyId: string) => void | Promise<void>;
  onPageChange: (nextOffset: number) => void | Promise<void>;
  selectedKeyId: string;
  usageRecords: PortalUsageRecordsPage;
};

const labels = {
  zh: {
    title: "流水记录",
    lead: "逐条查看每次模型调用消耗的信用点、API Key 和 token 明细。",
    allKeys: "全部 API Key",
    filter: "按 API Key 过滤",
    time: "时间",
    apiKey: "API Key",
    route: "Provider / Model",
    outcome: "结果",
    tokens: "Tokens in/cache/out",
    credits: "信用点",
    usd: "USD",
    source: "计费来源",
    empty: "还没有调用流水。",
    previous: "上一页",
    next: "下一页",
    pageStatus: (current: number, total: number, records: number) => `第 ${current} / ${total} 页，共 ${records} 条`,
  },
  en: {
    title: "Usage Records",
    lead: "Review credit, API key, and token details for each model call.",
    allKeys: "All API keys",
    filter: "Filter by API key",
    time: "Time",
    apiKey: "API Key",
    route: "Provider / Model",
    outcome: "Outcome",
    tokens: "Tokens in/cache/out",
    credits: "Credits",
    usd: "USD",
    source: "Billing source",
    empty: "No usage records yet.",
    previous: "Previous",
    next: "Next",
    pageStatus: (current: number, total: number, records: number) => `Page ${current} / ${total}, ${records} records`,
  },
};

export function UsagePage({
  apiKeys,
  locale,
  onKeyFilterChange,
  onPageChange,
  selectedKeyId,
  usageRecords,
}: UsagePageProps) {
  const copy = labels[locale];
  const limit = Math.max(usageRecords.limit, 1);
  const totalPages = Math.max(Math.ceil(usageRecords.total / limit), 1);
  const currentPage = Math.min(Math.floor(usageRecords.offset / limit) + 1, totalPages);
  const previousOffset = Math.max(usageRecords.offset - limit, 0);
  const nextOffset = usageRecords.offset + limit;

  return (
    <section className="portal-section">
      <div className="portal-section__header usage-records__header">
        <div>
          <h1>{copy.title}</h1>
          <p>{copy.lead}</p>
        </div>
        <span className="status-pill">{copy.pageStatus(currentPage, totalPages, usageRecords.total)}</span>
      </div>

      <div className="usage-records__toolbar">
        <label>
          <span>{copy.filter}</span>
          <select
            aria-label={copy.filter}
            value={selectedKeyId}
            onChange={(event) => void onKeyFilterChange(event.target.value)}
          >
            <option value="">{copy.allKeys}</option>
            {apiKeys.map((apiKey) => (
              <option key={apiKey.id} value={apiKey.id}>
                {`${apiKey.name} · ${apiKey.key_prefix}`}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="table-shell">
        <table className="data-table usage-records__table">
          <thead>
            <tr>
              <th>{copy.time}</th>
              <th>{copy.apiKey}</th>
              <th>{copy.route}</th>
              <th>{copy.outcome}</th>
              <th>{copy.tokens}</th>
              <th>{copy.credits}</th>
              <th>{copy.usd}</th>
              <th>{copy.source}</th>
            </tr>
          </thead>
          <tbody>
            {usageRecords.items.length === 0 ? (
              <tr>
                <td colSpan={8}>{copy.empty}</td>
              </tr>
            ) : (
              usageRecords.items.map((row) => <UsageRecordRow key={row.id} locale={locale} row={row} />)
            )}
          </tbody>
        </table>
      </div>

      <div className="pagination-row usage-records__pagination">
        <button
          className="ghost-action"
          disabled={currentPage <= 1}
          onClick={() => void onPageChange(previousOffset)}
          type="button"
        >
          {copy.previous}
        </button>
        <span>{copy.pageStatus(currentPage, totalPages, usageRecords.total)}</span>
        <button
          className="ghost-action"
          disabled={nextOffset >= usageRecords.total}
          onClick={() => void onPageChange(nextOffset)}
          type="button"
        >
          {copy.next}
        </button>
      </div>
    </section>
  );
}

function UsageRecordRow({ locale, row }: { locale: Locale; row: PortalUsageRecord }) {
  const providerModel = [row.provider_name, row.model_id].filter(Boolean);

  return (
    <tr>
      <td>{formatDate(row.created_at, locale)}</td>
      <td>
        <div className="usage-records__key">
          <strong>{row.api_key_name ?? `#${row.api_key_id}`}</strong>
          <code>{row.key_prefix ?? row.api_key_id}</code>
        </div>
      </td>
      <td>
        <div className="usage-records__route">
          <span>{row.provider_name ?? "-"}</span>
          <code>{providerModel.length > 0 ? row.model_id ?? "-" : "-"}</code>
        </div>
      </td>
      <td>
        <span className={`status-pill status-pill--${outcomeTone(row.outcome)}`}>{row.outcome}</span>
      </td>
      <td>{formatUsageTokens(row, locale)}</td>
      <td>{formatCredits(row.credits_charged, locale)}</td>
      <td>{formatUsd(row.usd_amount)}</td>
      <td>{formatSource(row)}</td>
    </tr>
  );
}

function formatDate(value: string, locale: Locale): string {
  return new Date(value).toLocaleString(locale === "zh" ? "zh-CN" : "en-US");
}

function formatUsageTokens(row: PortalUsageRecord, locale: Locale): string {
  if (row.input_tokens == null && row.output_tokens == null && row.cached_input_tokens == null) {
    return "-";
  }
  return [
    formatInteger(row.input_tokens ?? 0, locale),
    formatInteger(row.cached_input_tokens ?? 0, locale),
    formatInteger(row.output_tokens ?? 0, locale),
  ].join(" / ");
}

function formatInteger(value: number, locale: Locale): string {
  return value.toLocaleString(locale === "zh" ? "zh-CN" : "en-US", { maximumFractionDigits: 0 });
}

function formatCredits(value: number | null | undefined, locale: Locale): string {
  if (value == null) {
    return "-";
  }
  return value.toLocaleString(locale === "zh" ? "zh-CN" : "en-US", {
    maximumFractionDigits: 4,
  });
}

function formatUsd(value: number | null | undefined): string {
  if (value == null) {
    return "-";
  }
  return `$${value.toLocaleString("en-US", {
    minimumFractionDigits: 4,
    maximumFractionDigits: 6,
  })}`;
}

function formatSource(row: PortalUsageRecord): string {
  if (row.pricing_source && row.token_source) {
    return `${row.pricing_source} / ${row.token_source}`;
  }
  return row.pricing_source ?? row.token_source ?? "-";
}

function outcomeTone(outcome: string): "ok" | "warning" | "danger" {
  if (outcome === "success") {
    return "ok";
  }
  if (outcome === "rate_limited") {
    return "warning";
  }
  return "danger";
}
