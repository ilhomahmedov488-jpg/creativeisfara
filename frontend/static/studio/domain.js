export const ZONE = 'Asia/Dushanbe';
export const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
export function safeMedia(value, origin = location.origin) {
  if (!value) return '';
  try { const url = new URL(value, origin); return ['http:','https:'].includes(url.protocol) ? url.href : ''; }
  catch { return ''; }
}
export function parts(value = Date.now()) {
  return Object.fromEntries(new Intl.DateTimeFormat('en-CA', {
    timeZone:ZONE, year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', hourCycle:'h23',
  }).formatToParts(new Date(value)).map(p => [p.type, p.value]));
}
export function today() { const p=parts(); return `${p.year}-${p.month}-${p.day}`; }
export function localInput(value) { if (!value) return ''; const p=parts(value); return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`; }
export const apiDateTime = value => value ? `${value}:00+05:00` : null;
export const manager = user => user?.cabinet === 'management';
export const staff = user => !!user?.member;
export function countdown(start, serverOffset=0, now=Date.now()) {
  const seconds = Math.max(0, Math.floor((new Date(start).getTime()-now-serverOffset)/1000));
  return [Math.floor(seconds/86400), Math.floor(seconds%86400/3600), Math.floor(seconds%3600/60), seconds%60];
}
export function estimate(catalog, event, packageCode, extras) {
  const rates = Object.fromEntries(catalog.map(item=>[item.code, Math.round(Number(item.price)*100)]));
  if (!(packageCode in rates)) return null;
  const included = event==='wedding' && packageCode==='premium' ? ['album','foteha_one'] : [];
  if (included.length && extras.includes('foteha_two')) return null;
  const codes=[...new Set([packageCode,...extras])];
  if (codes.some(code=>!(code in rates))) return null;
  const cents=codes.reduce((sum,code)=>sum+(included.includes(code)?0:rates[code]),0);
  return {total:cents/100, deposit:Math.round(cents*.2)/100};
}
export function changeAllowed(booking, currentDay=today()) {
  if (!['new','confirmed'].includes(booking.status)) return false;
  const original=booking.shoot_start ? localInput(booking.shoot_start).slice(0,10) : booking.date;
  return (Date.parse(original+'T00:00:00+05:00')-Date.parse(currentDay+'T00:00:00+05:00'))/86400000>=15;
}
export const transitions = {new:['new','confirmed','cancelled'],confirmed:['confirmed','editing','cancelled'],editing:['editing','ready','cancelled'],ready:['ready'],cancelled:['cancelled']};
