/** Wire timestamps are UTC, never browser-local strings or normalized invalid dates. */
export function isUtcTime(value:unknown):value is string {
 if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/.test(value))return false;
 const date=new Date(value);
 return Number.isFinite(date.getTime())&&date.toISOString().slice(0,19)===value.slice(0,19);
}
