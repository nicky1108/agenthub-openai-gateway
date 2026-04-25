import { useState } from "react";

import type { ApiKeyRecord, ApiKeyUpdatePayload } from "../../api";
import type { Copy } from "../../i18n";

type ApiKeysPageProps = {
  apiKeys: ApiKeyRecord[];
  copy: Copy;
  createdKey: string | null;
  keyName: string;
  limitDay: string;
  limitHour: string;
  limitMinute: string;
  onCreate: () => Promise<void>;
  onDelete: (id: number) => Promise<void>;
  onUpdate: (id: number, payload: ApiKeyUpdatePayload) => Promise<void>;
  onKeyNameChange: (value: string) => void;
  onLimitDayChange: (value: string) => void;
  onLimitHourChange: (value: string) => void;
  onLimitMinuteChange: (value: string) => void;
  onDismissCreatedKey: () => void;
};

function formatLimit(value: number | null, copy: Copy): string {
  return value === null ? copy.portal.unlimited : String(value);
}

export function ApiKeysPage({
  apiKeys,
  copy,
  createdKey,
  keyName,
  limitDay,
  limitHour,
  limitMinute,
  onCreate,
  onDelete,
  onUpdate,
  onKeyNameChange,
  onLimitDayChange,
  onLimitHourChange,
  onLimitMinuteChange,
  onDismissCreatedKey,
}: ApiKeysPageProps) {
  const [editingKeyId, setEditingKeyId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editLimitMinute, setEditLimitMinute] = useState("");
  const [editLimitHour, setEditLimitHour] = useState("");
  const [editLimitDay, setEditLimitDay] = useState("");
  const totalRequests = apiKeys.reduce((sum, key) => sum + key.total_requests, 0);
  const limitedRequests = apiKeys.reduce((sum, key) => sum + key.limited_requests, 0);
  const recentlyUsedKeys = apiKeys.filter((key) => key.last_used_at).length;

  function startEditing(key: ApiKeyRecord) {
    setEditingKeyId(key.id);
    setEditName(key.name);
    setEditLimitMinute(key.per_minute === null ? "" : String(key.per_minute));
    setEditLimitHour(key.per_hour === null ? "" : String(key.per_hour));
    setEditLimitDay(key.per_day === null ? "" : String(key.per_day));
  }

  async function saveEdit(keyId: number) {
    await onUpdate(keyId, {
      name: editName,
      per_minute: parseEditableLimit(editLimitMinute),
      per_hour: parseEditableLimit(editLimitHour),
      per_day: parseEditableLimit(editLimitDay),
    });
    setEditingKeyId(null);
  }

  return (
    <section className="portal-section">
      <div className="portal-section__header">
        <div>
          <div className="eyebrow">{copy.portal.apiKeysTitle}</div>
          <h1>{copy.portal.apiKeysTitle}</h1>
          <p>{copy.portal.apiKeysLead}</p>
        </div>
      </div>
      <div className="resource-summary-grid">
        <article>
          <span>Active keys</span>
          <strong>{apiKeys.length}</strong>
        </article>
        <article>
          <span>Total requests</span>
          <strong>{totalRequests}</strong>
        </article>
        <article>
          <span>Limited requests</span>
          <strong>{limitedRequests}</strong>
        </article>
        <article>
          <span>Used keys</span>
          <strong>{recentlyUsedKeys}</strong>
        </article>
      </div>
      {createdKey ? (
        <div className="secret-banner">
          <div>
            <strong>{copy.portal.keyReveal}</strong>
            <code>{createdKey}</code>
          </div>
          <button className="ghost-action" onClick={onDismissCreatedKey}>
            OK
          </button>
        </div>
      ) : null}
      <div className="form-panel">
        <div className="form-panel__header">
          <div>
            <h3>Create API key</h3>
            <p>Use one gateway key for managed models and custom providers.</p>
          </div>
        </div>
        <div className="inline-form api-key-form">
        <label>
          <span>{copy.portal.keyName}</span>
          <input
            placeholder={copy.portal.keyName}
            value={keyName}
            onChange={(event) => onKeyNameChange(event.target.value)}
          />
        </label>
        <label>
          <span>{copy.portal.keyLimitMinute}</span>
          <input
            aria-label={copy.portal.keyLimitMinute}
            min={1}
            placeholder={copy.portal.unlimited}
            type="number"
            value={limitMinute}
            onChange={(event) => onLimitMinuteChange(event.target.value)}
          />
        </label>
        <label>
          <span>{copy.portal.keyLimitHour}</span>
          <input
            aria-label={copy.portal.keyLimitHour}
            min={1}
            placeholder={copy.portal.unlimited}
            type="number"
            value={limitHour}
            onChange={(event) => onLimitHourChange(event.target.value)}
          />
        </label>
        <label>
          <span>{copy.portal.keyLimitDay}</span>
          <input
            aria-label={copy.portal.keyLimitDay}
            min={1}
            placeholder={copy.portal.unlimited}
            type="number"
            value={limitDay}
            onChange={(event) => onLimitDayChange(event.target.value)}
          />
        </label>
        <button className="primary-action" disabled={!keyName.trim()} onClick={() => void onCreate()}>
          {copy.common.create}
        </button>
        </div>
      </div>
      {apiKeys.length === 0 ? (
        <div className="empty-state empty-state--action">
          <strong>{copy.portal.noKeys}</strong>
          <p>创建一个 API Key 后即可调用 /v1/models 与 /v1/chat/completions。</p>
        </div>
      ) : (
        <div className="table-shell">
        <table className="data-table">
          <thead>
            <tr>
              <th>{copy.portal.keyName}</th>
              <th>Prefix</th>
              <th>{copy.portal.keyLimits}</th>
              <th>Usage</th>
              <th>Created</th>
              <th>Last Used</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {apiKeys.map((key) => (
              <tr key={key.id}>
                <td>
                  {editingKeyId === key.id ? (
                    <input
                      aria-label="编辑 Key 名称"
                      value={editName}
                      onChange={(event) => setEditName(event.target.value)}
                    />
                  ) : (
                    key.name
                  )}
                </td>
                <td>{key.key_prefix}</td>
                <td className="limit-cell">
                  {editingKeyId === key.id ? (
                    <div className="api-key-edit-form">
                      <input
                        aria-label="编辑每分钟限额"
                        min={1}
                        placeholder={copy.portal.unlimited}
                        type="number"
                        value={editLimitMinute}
                        onChange={(event) => setEditLimitMinute(event.target.value)}
                      />
                      <input
                        aria-label="编辑每小时限额"
                        min={1}
                        placeholder={copy.portal.unlimited}
                        type="number"
                        value={editLimitHour}
                        onChange={(event) => setEditLimitHour(event.target.value)}
                      />
                      <input
                        aria-label="编辑每天限额"
                        min={1}
                        placeholder={copy.portal.unlimited}
                        type="number"
                        value={editLimitDay}
                        onChange={(event) => setEditLimitDay(event.target.value)}
                      />
                    </div>
                  ) : (
                    <>
                      <span>
                        {copy.portal.keyLimitMinute}: {formatLimit(key.per_minute, copy)}
                      </span>
                      <span>
                        {copy.portal.keyLimitHour}: {formatLimit(key.per_hour, copy)}
                      </span>
                      <span>
                        {copy.portal.keyLimitDay}: {formatLimit(key.per_day, copy)}
                      </span>
                    </>
                  )}
                </td>
                <td>
                  <div className="usage-mini-chart" aria-label={`${key.name} usage summary`}>
                    <span>{key.total_requests} total</span>
                    <span>{key.limited_requests} limited</span>
                    {key.total_requests > 0 ? (
                      <>
                        <div className="usage-mini-chart__track">
                          <span
                            className="usage-mini-chart__bar"
                            style={{
                              width: `${usagePercent(key.total_requests, key.total_requests)}%`,
                            }}
                          />
                        </div>
                        <div className="usage-mini-chart__track usage-mini-chart__track--limited">
                          <span
                            className="usage-mini-chart__bar usage-mini-chart__bar--limited"
                            style={{
                              width: `${usagePercent(key.limited_requests, key.total_requests)}%`,
                            }}
                          />
                        </div>
                      </>
                    ) : (
                      <small>No traffic yet</small>
                    )}
                  </div>
                </td>
                <td>{key.created_at ? new Date(key.created_at).toLocaleString() : "—"}</td>
                <td>{key.last_used_at ? new Date(key.last_used_at).toLocaleString() : "—"}</td>
                <td className="data-table__actions">
                  {editingKeyId === key.id ? (
                    <>
                      <button
                        className="primary-action"
                        disabled={!editName.trim()}
                        onClick={() => void saveEdit(key.id)}
                      >
                        保存限额
                      </button>
                      <button className="ghost-action" onClick={() => setEditingKeyId(null)}>
                        取消
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        aria-label={`编辑 ${key.name}`}
                        className="ghost-action ghost-action--bright"
                        onClick={() => startEditing(key)}
                      >
                        编辑
                      </button>
                      <button className="ghost-action ghost-action--danger" onClick={() => void onDelete(key.id)}>
                        {copy.common.delete}
                      </button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}
    </section>
  );
}

function parseEditableLimit(value: string): number | null {
  if (!value.trim()) {
    return null;
  }
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    return null;
  }
  return parsed;
}

function usagePercent(value: number, total: number): number {
  if (total <= 0 || value <= 0) {
    return 0;
  }
  return Math.min(100, Math.round((value / total) * 100));
}
