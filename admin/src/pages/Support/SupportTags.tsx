import { Tag } from 'antd';
import { supportLabel } from './supportPolicy';

/** Priority and state are shown as text tags; color only reinforces the label. */
export function PriorityTag({ value }: { value: string }) {
  return value === 'priority' ? <Tag color="red">{supportLabel('priority', value)}</Tag> : <Tag>{supportLabel('priority', value)}</Tag>;
}
export function TicketStateTag({ value }: { value: string }) {
  return <Tag color={value === 'open' ? 'processing' : value === 'resolved' ? 'success' : 'default'}>{supportLabel('state', value)}</Tag>;
}
