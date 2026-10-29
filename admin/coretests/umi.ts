import { vi } from 'vitest';
export const request = vi.fn();
export const history = { push: vi.fn(), replace: vi.fn(), location: { pathname: '/users', search: '' } };
