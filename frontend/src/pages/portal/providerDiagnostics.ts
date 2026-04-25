export type ProviderDiagnostic = {
  tone: "neutral" | "warning" | "danger";
  summary: string;
};

export function summarizeProviderDetail(detail: string | null | undefined): ProviderDiagnostic | null {
  if (!detail) {
    return null;
  }

  const normalized = detail.toLowerCase();
  if (normalized.includes("401") || normalized.includes("403")) {
    return {
      tone: "danger",
      summary: "上游 API key 无效或权限不足。",
    };
  }
  if (normalized.includes("404")) {
    return {
      tone: "warning",
      summary: "上游路径返回 404。优先检查 Base URL 是否已经包含正确的 `/v1` 前缀。",
    };
  }
  if (normalized.includes("local gateway unavailable")) {
    return {
      tone: "warning",
      summary: "平台模型服务暂时不可用。请稍后重试，或联系支持团队。",
    };
  }
  if (normalized.includes("invalid response")) {
    return {
      tone: "warning",
      summary: "上游返回形状不兼容 OpenAI 标准，需要检查 provider 是否真的兼容当前接口。",
    };
  }
  if (normalized.includes("timed out") || normalized.includes("timeout")) {
    return {
      tone: "warning",
      summary: "上游响应超时。需要检查网络、模型延迟或请求体大小。",
    };
  }
  return {
    tone: "neutral",
    summary: "已记录最近一次失败详情，可结合原始错误继续排查。",
  };
}
