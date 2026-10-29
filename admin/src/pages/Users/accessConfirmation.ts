export type AccessConfirmation = { open: boolean; conflict: boolean };
export type AccessConfirmationEvent =
  | { type: 'open' | 'close' | 'conflict' }
  | { type: 'refresh_result'; success: boolean };

export const initialAccessConfirmation: AccessConfirmation = { open: false, conflict: false };

/** Dialog visibility never acknowledges a conflict; only a successful explicit refresh does. */
export function accessConfirmationReducer(state: AccessConfirmation, event: AccessConfirmationEvent): AccessConfirmation {
  switch (event.type) {
    case 'open': return { ...state, open: true };
    case 'close': return { ...state, open: false };
    case 'conflict': return { ...state, conflict: true };
    case 'refresh_result': return event.success ? { open: false, conflict: false } : state;
  }
}
