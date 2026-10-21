const MADRID = 'Europe/Madrid';
const encoder = new TextEncoder();
const PUBLIC_FIELDS = ['id', 'event_key', 'title', 'url', 'start_at', 'end_at', 'time_precision', 'location', 'description', 'source'];

export function validDate(value) {
  if (typeof value !== 'string' || !/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(value) || value.startsWith('0000')) return false;
  const parsed = Date.parse(value + 'T00:00:00Z');
  return Number.isFinite(parsed) && new Date(parsed).toISOString().slice(0, 10) === value;
}

export function validTimestamp(value) {
  if (typeof value !== 'string') return false;
  const match = /^([0-9]{4}-[0-9]{2}-[0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.[0-9]{1,6})?(Z|[+-]([0-9]{2}):([0-9]{2}))$/.exec(value);
  return Boolean(match && validDate(match[1]) && Number(match[2]) < 24 &&
    Number(match[3]) < 60 && Number(match[4]) < 60 &&
    (!match[6] || (Number(match[6]) < 24 && Number(match[7]) < 60)) &&
    Number.isFinite(Date.parse(value)) &&
    new Date(value).getUTCFullYear() >= 1 && new Date(value).getUTCFullYear() <= 9999);
}

export function safePublicUrl(value) {
  if (typeof value !== 'string' || value.length > 4096 || /[\s\\\u0000-\u001f\u007f]/u.test(value)) return false;
  try {
    const url = new URL(value);
    return /^https?:\/\//.test(value) && ['http:', 'https:'].includes(url.protocol) &&
      Boolean(url.hostname) && !url.username && !url.password &&
      !/^\/(?:api|account|login|signin|sign-in|verify|onboarding)(?:\/|$)/i.test(url.pathname) &&
      ![...url.searchParams.keys()].some((key) => /^(?:token|access_token|auth|authorization|session|session_id|email|password|user_id|account_id|magic_link)$/i.test(key));
  } catch {
    return false;
  }
}

export function boundedText(value, max, min = 0) {
  return typeof value === 'string' && value.length <= max && value.trim().length >= min &&
    !/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/u.test(value);
}

// Validate public fields while deliberately ignoring private fields. All export
// helpers below construct their output from an explicit public projection.
export function validPublicEvent(event) {
  return Boolean(event && typeof event === 'object' && !Array.isArray(event) &&
    PUBLIC_FIELDS.every((field) => Object.hasOwn(event, field)) &&
    Number.isSafeInteger(event.id) && event.id > 0 &&
    typeof event.event_key === 'string' && /^[A-Za-z0-9._:-]{1,128}$/.test(event.event_key) &&
    boundedText(event.title, 500, 1) && safePublicUrl(event.url) &&
    validTimestamp(event.start_at) && ['datetime', 'date', 'unverified'].includes(event.time_precision) &&
    (event.end_at === null || (validTimestamp(event.end_at) && Date.parse(event.end_at) > Date.parse(event.start_at))) &&
    boundedText(event.location, 500) && boundedText(event.description, 8000) &&
    boundedText(event.source, 80, 1));
}

export function madridDate(timestamp) {
  if (!validTimestamp(timestamp)) throw new Error('The event date is not available.');
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: MADRID, year: 'numeric', month: '2-digit', day: '2-digit'
  }).formatToParts(new Date(timestamp));
  const part = (name) => parts.find((item) => item.type === name).value;
  return part('year') + '-' + part('month') + '-' + part('day');
}

export function planDateLabel(date) {
  if (!validDate(date)) throw new Error('The planning date is not available.');
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'UTC', weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
  }).formatToParts(new Date(date + 'T12:00:00Z'));
  return ['weekday', 'day', 'month', 'year'].map((name) => parts.find((part) => part.type === name).value).join(' ');
}

export function eventTimeLabel(event) {
  if (!validPublicEvent(event)) return 'Date and time not confirmed';
  if (event.time_precision === 'unverified') return 'Date and time not confirmed';
  const date = planDateLabel(madridDate(event.start_at));
  if (event.time_precision === 'date') return date + ' · Time not confirmed';
  const time = new Intl.DateTimeFormat('en-GB', {
    timeZone: MADRID, hour: '2-digit', minute: '2-digit'
  });
  const end = event.end_at
    ? (madridDate(event.end_at) === madridDate(event.start_at) ? '' : planDateLabel(madridDate(event.end_at)) + ' · ') + time.format(new Date(event.end_at))
    : null;
  return date + ' · ' + time.format(new Date(event.start_at)) +
    (end ? ' – ' + end : '') + ' (València time)';
}

function publicEvent(event) {
  if (!validPublicEvent(event)) throw new Error('The public event details could not be read safely.');
  return Object.fromEntries(PUBLIC_FIELDS.map((field) => [field, event[field]]));
}

export function eventCopyText(event) {
  const item = publicEvent(event);
  return [item.title.replace(/\s+/gu, ' ').trim(), eventTimeLabel(item), item.url].join('\n');
}

export function shortlistCopyText(events) {
  if (!Array.isArray(events) || !events.length || events.length > 100) throw new Error('Choose a shortlist to copy.');
  return events.map(eventCopyText).join('\n\n');
}

export function directionsUrl(location) {
  if (!boundedText(location, 500, 1)) return null;
  return 'https://www.google.com/maps/dir/?api=1&destination=' + encodeURIComponent(location.trim());
}

export function canExportCalendar(event) {
  return validPublicEvent(event) && event.time_precision !== 'unverified';
}

function escapeText(value) {
  return value.replace(/\\/g, '\\\\').replace(/\r\n|\r|\n/g, '\\n').replace(/;/g, '\\;').replace(/,/g, '\\,');
}

// RFC 5545 sections 3.1, 3.3.11, 3.6.1 and 3.6.6:
// https://www.rfc-editor.org/rfc/rfc5545.html
// Fold by UTF-8 octets without splitting a code point; continuation space
// counts toward the next physical line's 75-octet limit.
function foldLine(value) {
  const lines = [];
  let line = '';
  let size = 0;
  for (const character of value) {
    const bytes = encoder.encode(character).length;
    if (size + bytes > 75) {
      lines.push(line);
      line = ' ';
      size = 1;
    }
    line += character;
    size += bytes;
  }
  lines.push(line);
  return lines.join('\r\n');
}

function utcDateTime(value) {
  return new Date(value).toISOString().replace(/[-:]/g, '').replace(/\.[0-9]{3}Z$/, 'Z');
}

function publicUid(event) {
  let hash = 14695981039346656037n;
  for (const byte of encoder.encode(event.url + '\n' + event.start_at + '\n' + event.title)) {
    hash = BigInt.asUintN(64, (hash ^ BigInt(byte)) * 1099511628211n);
  }
  return hash.toString(16) + '@valencia-event-notifications.pages.dev';
}

export function eventCalendar(event, { reminder = false, now = new Date() } = {}) {
  const item = publicEvent(event);
  if (!canExportCalendar(item)) throw new Error('Confirm the event date with the organizer before adding it to your calendar.');
  if (typeof reminder !== 'boolean' || !(now instanceof Date) || !Number.isFinite(now.getTime())) throw new Error('The calendar options are invalid.');
  if (reminder && item.time_precision !== 'datetime') throw new Error('A timed reminder needs a confirmed start time.');
  const dateOnly = item.time_precision === 'date';
  const lines = [
    'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Brisa//Event planning//EN', 'CALSCALE:GREGORIAN',
    'BEGIN:VEVENT', 'UID:' + publicUid(item), 'DTSTAMP:' + utcDateTime(now),
    dateOnly ? 'DTSTART;VALUE=DATE:' + madridDate(item.start_at).replace(/-/g, '') : 'DTSTART:' + utcDateTime(item.start_at),
    'SUMMARY:' + escapeText((dateOnly ? 'Save the date: ' : '') + item.title),
    'DESCRIPTION:' + escapeText((dateOnly ? 'Start time not confirmed. Check the organizer before making plans.\n' : '') + 'Organizer details: ' + item.url),
    'URL:' + item.url,
    'TRANSP:TRANSPARENT'
  ];
  // A missing end is intentionally omitted; never invent an event duration.
  if (!dateOnly && item.end_at) lines.push('DTEND:' + utcDateTime(item.end_at));
  if (item.location.trim()) lines.push('LOCATION:' + escapeText(item.location));
  if (reminder) lines.push('BEGIN:VALARM', 'ACTION:DISPLAY', 'TRIGGER:-PT1H', 'DESCRIPTION:' + escapeText(item.title), 'END:VALARM');
  lines.push('END:VEVENT', 'END:VCALENDAR');
  return lines.map(foldLine).join('\r\n') + '\r\n';
}

export function calendarFilename(event) {
  const item = publicEvent(event);
  return 'brisa-' + madridDate(item.start_at) + '.ics';
}
