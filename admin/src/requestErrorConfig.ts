import type { RequestConfig } from '@umijs/max';
import { normalizeAdminError } from './services/admin/errors';
import { clearSession } from './services/admin/session';

/** Official errorConfig extension point. Safe local errors remain rejected. */
export const errorConfig: RequestConfig = {
  errorConfig: { errorHandler: (error,options) => {
    // Installed Umi invokes this hook even for skipErrorHandler. The adapter must
    // own its epoch-aware clearing and write-outcome decoding exactly once.
    if(options?.skipErrorHandler)throw error;
    const normalized=normalizeAdminError(error);
    if(normalized.status===401)clearSession('unauthorized');
    throw normalized;
  } },
  requestInterceptors: [],
  responseInterceptors: [],
};
