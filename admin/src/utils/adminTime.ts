/** Wire timestamps are UTC, never browser-local strings or normalized invalid dates. */
export function isUtcTime(value:unknown):value is string {
 if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/.test(value))return false;
 const date=new Date(value);
 return Number.isFinite(date.getTime())&&date.toISOString().slice(0,19)===value.slice(0,19);
}

/** Native date/time controls display the browser timezone; Form stores only UTC wire values. */
export function utcToLocalInput(value: unknown): string {
 if (!isUtcTime(value)) return '';
 const date=new Date(value),pad=(number:number)=>String(number).padStart(2,'0');
 return `${String(date.getFullYear()).padStart(4,'0')}-${pad(date.getMonth()+1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}
export function localInputToUtc(value: string): string {
 if (!value) return '';
 if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?$/.test(value)) return value;
 const date=new Date(value);
 if (!Number.isFinite(date.getTime())) return value;
 const utc=date.toISOString();
 // Reject normalized impossible dates and DST gaps instead of silently moving the requested time.
 return utcToLocalInput(utc).slice(0,value.length)===value ? utc : value;
}
