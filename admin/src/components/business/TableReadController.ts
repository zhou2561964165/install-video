export type TableReadResult<T> = { data: T[]; total: number; success: boolean };
export type TableReadSuccess<T> = { result: TableReadResult<T>; asOf: string };

/** Guard only our request side effects. ProTable still owns rendering/paging/cancellation. */
export function createTableReadController<T>(effects: {
  success: (value: TableReadSuccess<T>) => void;
  failure: (error: unknown) => void;
}) {
  let sequence = 0;
  let mounted = true;
  let last: TableReadResult<T> = { data: [], total: 0, success: false };
  return {
    activate() { mounted = true; },
    dispose() { mounted = false; sequence += 1; },
    last() { return last; },
    async request(load: () => Promise<TableReadSuccess<T>>): Promise<TableReadResult<T>> {
      const current = ++sequence;
      const eligible = () => mounted && current === sequence;
      try {
        const value = await load();
        if (!eligible()) return { ...last, success: false };
        last = value.result;
        effects.success(value);
        return value.result;
      } catch (error) {
        if (eligible()) effects.failure(error);
        return { ...last, success: false };
      }
    },
  };
}
