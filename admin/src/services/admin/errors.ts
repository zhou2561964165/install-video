/** Render only local messages. Unexpected backend payloads are never displayed/logged. */
const messages: Record<number, string> = {
  0: '网络连接中断，无法确认请求结果。', 400: '请求无法处理。',
  401: '登录失败或会话已过期，请重新登录。', 403: '无权限访问此功能。',
  404: '记录不存在或已不可见。', 409: '记录已变化或幂等键冲突，请刷新后重新核对。',
  422: '请求参数不符合要求，请检查筛选条件或表单。',
  429: '请求过于频繁，请稍后再试。', 502: '服务响应不符合管理接口约定，请联系管理员核对。', 503: '管理服务或此能力尚未就绪，请稍后手动重试。',
};
export class AdminApiError extends Error {
  constructor(public status: number, public errorType = 'unknown', public requestId?: string,
    public retryAfter?: number, public fieldErrors: {field: string; message: string}[] = [],
    public outcomeUnknown = false) { super(messages[status] ?? '请求未完成，请联系管理员并提供请求编号。'); this.name = 'AdminApiError'; }
}
const record = (v: unknown): Record<string, unknown> => v && typeof v === 'object' ? v as Record<string, unknown> : {};
const safeCode = (v: unknown, limit = 128) => typeof v === 'string' && /^[A-Za-z0-9_.:-]+$/.test(v) && v.length <= limit ? v : undefined;
export function normalizeAdminError(value: unknown, write = false): AdminApiError {
  if (value instanceof AdminApiError) return value;
  const response = record(record(value).response), data = record(response.data), detail = record(data.detail);
  const status = typeof response.status === 'number' ? response.status : 0;
  const headers = record(response.headers);
  const retry = Number(headers['retry-after']);
  const fieldErrors = Array.isArray(detail.field_errors) ? detail.field_errors.flatMap(item => {
    const field = safeCode(record(item).field, 64);
    return field ? [{field, message: '此字段不符合要求。'}] : [];
  }) : [];
  return new AdminApiError(status, safeCode(detail.error_type) ?? 'unknown',
    safeCode(detail.request_id) ?? safeCode(headers['x-request-id']),
    Number.isFinite(retry) && retry > 0 ? Math.ceil(retry) : undefined,
    fieldErrors, write && (status === 0 || status >= 500));
}
