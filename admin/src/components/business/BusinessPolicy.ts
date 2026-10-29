import { resourceConfig, validateQueryValue } from '@/config/resourceConfig';
import type { ListOperation } from '@/services/admin/api';
import type { Schemas } from '@/services/admin/types';
import { AdminApiError } from '@/services/admin/errors';

/** ProTable Select uses string keys; convert only fields with matching contract and meta kinds. */
export function normalizeTableParams(resource: ListOperation, params: Record<string, unknown>, meta?: Schemas['AdminMeta']) {
  const normalized = { ...params };
  const descriptors = meta?.queries.find((item) => item.resource === resource)?.filters ?? [];
  for (const field of resourceConfig[resource].filters) {
    if (!descriptors.some((item) => item.name === field.name && item.kind === field.kind)) continue;
    let value = normalized[field.name];
    if (Array.isArray(value) && value.length === 1) { value = value[0]; normalized[field.name] = value; }
    if (field.kind === 'boolean' && (value === 'true' || value === 'false')) normalized[field.name] = value === 'true';
    if (field.kind === 'enum' && field.schema.type === 'integer' && typeof value === 'string') {
      const allowed = field.schema.enum?.find((entry) => typeof entry === 'number' && String(entry) === value);
      if (allowed !== undefined) normalized[field.name] = allowed;
    }
  }
  return normalized;
}

/** A filled supported field must not silently broaden a query when invalid. */
export function checkedTableParams(resource: ListOperation, params: Record<string, unknown>, meta?: Schemas['AdminMeta']) {
  const result = normalizeTableParams(resource, params, meta);
  const descriptors = meta?.queries.find((item) => item.resource === resource)?.filters ?? [];
  for (const field of resourceConfig[resource].filters) {
    const descriptor = descriptors.find((item) => item.name === field.name && item.kind === field.kind);
    if (!descriptor) continue;
    let value = result[field.name];
    if (value === undefined || value === null || value === '' || (Array.isArray(value) && value.length === 0)) continue;
    if (Array.isArray(value) && value.length === 1) value = value[0];
    if (!validateQueryValue(field.schema, value) || (field.kind === 'enum' && !descriptor.allowed_values?.includes(String(value)))) {
      throw new AdminApiError(422, 'invalid_filter', undefined, undefined, [{ field: field.name, message: '请检查此筛选条件。' }]);
    }
  }
  return result;
}

export function sampledSystemState(component: Pick<Schemas['ComponentStatus'], 'status' | 'checked_at'>) {
  return component.status === 'ok' && component.checked_at === null ? 'unknown' : component.status;
}

export function accessFailureKind(error: unknown): 'conflict' | 'unknown' | 'rejected' {
  if (error instanceof AdminApiError && error.status === 409) return 'conflict';
  if (!(error instanceof AdminApiError) || error.outcomeUnknown || error.status >= 500 || error.status === 0) return 'unknown';
  return 'rejected';
}

export function canChangeAccess(user: Schemas['UserDetail'] | undefined, actorId: string | undefined, ready: boolean) {
  return Boolean(ready && user && actorId && user.id !== actorId && !user.access.protected_account);
}
