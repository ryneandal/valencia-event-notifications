import { describe, expect, test } from 'vitest';

import {
  calendarFilename, canExportCalendar, directionsUrl, eventCalendar, eventCopyText,
  eventTimeLabel, planDateLabel, safePublicUrl, shortlistCopyText, validDate,
  validPublicEvent, validTimestamp
} from '../pages/src/planning.js';

const event = {
  id: 7, event_key: 'public-screening', title: 'Cinema by the river',
  url: 'https://example.org/screening', start_at: '2026-10-22T19:30:45+02:00',
  end_at: '2026-10-22T21:00:45+02:00', time_precision: 'datetime',
  location: 'Plaça del Mercat, València', description: 'An outdoor screening.',
  source: 'ajuntament_agenda'
};
const now = new Date('2026-10-21T12:34:56Z');
const unfold = (text) => text.replace(/\r\n /g, '');

describe('public planning actions', () => {
  test('copies only title, honest date/time, and organizer link in shortlist order', () => {
    const privateEvent = {
      ...event, email: 'private@example.org', user_id: 'private-user', preferences_blob: 'private profile',
      reason: 'private reason', irrelevance_score: 0.12345, event_key: 'private-key',
      position: 1, account_url: 'https://brisa.example/account'
    };
    const text = eventCopyText(privateEvent);
    expect(text.split('\n')).toEqual([
      event.title, 'Thursday 22 October 2026 · 19:30 – 21:00 (València time)', event.url
    ]);
    expect(text).not.toMatch(/private|0\.12345|account/);
    const second = { ...event, id: 8, title: 'Second choice', url: 'https://example.org/second' };
    expect(shortlistCopyText([second, privateEvent])).toBe(eventCopyText(second) + '\n\n' + text);
  });

  test('never presents synthetic noon or publication timestamps as event times', () => {
    expect(eventTimeLabel({ ...event, time_precision: 'date' })).toBe('Thursday 22 October 2026 · Time not confirmed');
    expect(eventTimeLabel({ ...event, time_precision: 'unverified' })).toBe('Date and time not confirmed');
    expect(eventCopyText({ ...event, time_precision: 'unverified' })).not.toContain('19:30');
    expect(planDateLabel('2026-10-22')).toBe('Thursday 22 October 2026');
  });

  test('includes the end date for an event that continues into another day', () => {
    expect(eventTimeLabel({ ...event, end_at: '2026-10-23T01:00:00+02:00' })).toBe(
      'Thursday 22 October 2026 · 19:30 – Friday 23 October 2026 · 01:00 (València time)'
    );
  });

  test.each([
    'javascript:alert(1)', '/relative', 'https://', 'https://user:password@example.org/event',
    'https://example.org/line\nINJECT', 'https://example.org\\event',
    'https://example.org/api/verify?token=private', 'https://example.org/account',
    'https://example.org/event?access_token=secret', 'https://example.org/event?email=private'
  ])('refuses unsafe or private event URL %s', (url) => {
    expect(safePublicUrl(url)).toBe(false);
    expect(() => eventCopyText({ ...event, url })).toThrow();
    expect(() => eventCalendar({ ...event, url }, { now })).toThrow();
  });

  test('directions send only the explicit public location, escaped in a fixed HTTPS endpoint', () => {
    const location = 'Carrer A & B?place=1 # València';
    const url = new URL(directionsUrl(location));
    expect(url.origin).toBe('https://www.google.com');
    expect(url.pathname).toBe('/maps/dir/');
    expect([...url.searchParams.entries()]).toEqual([['api', '1'], ['destination', location]]);
    expect(directionsUrl('')).toBeNull();
    expect(directionsUrl(null)).toBeNull();
  });

  test.each(['2026-02-30', '2026-13-01', '2026-00-01', '2026-1-01', '0000-01-01', null])('rejects impossible date %s', (value) => {
    expect(validDate(value)).toBe(false);
  });

  test.each([
    '2026-02-30T12:00:00Z', '2026-10-22T24:00:00Z', '2026-10-22T12:60:00Z',
    '2026-10-22T12:00:60Z', '2026-10-22T12:00:00+24:00', '2026-10-22T12:00:00',
    '2026-10-22', '9999-12-31T23:00:00-02:00', null
  ])('rejects unzoned or impossible timestamp %s', (value) => {
    expect(validTimestamp(value)).toBe(false);
    expect(validPublicEvent({ ...event, start_at: value })).toBe(false);
  });
});

describe('calendar files', () => {
  // RFC 5545 §§3.1, 3.3.11, 3.6.1, 3.6.6:
  // https://www.rfc-editor.org/rfc/rfc5545.html
  test('writes exact UTC seconds and an explicit end without adding a default reminder', () => {
    const calendar = unfold(eventCalendar(event, { now }));
    expect(calendar).toContain('DTSTAMP:20261021T123456Z\r\n');
    expect(calendar).toContain('DTSTART:20261022T173045Z\r\n');
    expect(calendar).toContain('DTEND:20261022T190045Z\r\n');
    expect(calendar).not.toContain('VALARM');
    expect(calendar).not.toContain('METHOD:');
    expect(calendar).toMatch(/^BEGIN:VCALENDAR\r\n/);
    expect(calendar).toMatch(/END:VEVENT\r\nEND:VCALENDAR\r\n$/);
    expect(calendarFilename(event)).toBe('brisa-2026-10-22.ics');
    expect(eventCalendar({ ...event, end_at: null }, { now })).not.toContain('DTEND');
  });

  test('adds only the explicitly chosen display reminder', () => {
    const calendar = unfold(eventCalendar(event, { now, reminder: true }));
    expect(calendar).toContain('BEGIN:VALARM\r\nACTION:DISPLAY\r\nTRIGGER:-PT1H\r\n');
    expect(calendar).toContain('DESCRIPTION:Cinema by the river\r\nEND:VALARM');
    expect(calendar).not.toContain('ATTENDEE');
    expect(() => eventCalendar(event, { now, reminder: 'true' })).toThrow();
  });

  test('uses Madrid dates for date-only events and does not invent a time, end, or reminder', () => {
    const dateOnly = { ...event, start_at: '2026-10-21T23:00:00Z', time_precision: 'date' };
    const calendar = unfold(eventCalendar(dateOnly, { now }));
    expect(calendar).toContain('DTSTART;VALUE=DATE:20261022\r\n');
    expect(calendar).toContain('SUMMARY:Save the date: Cinema by the river\r\n');
    expect(calendar).toContain('Start time not confirmed.');
    expect(calendar).not.toContain('DTEND');
    expect(calendar).not.toContain('VALARM');
    expect(() => eventCalendar(dateOnly, { now, reminder: true })).toThrow(/confirmed start time/);
    expect(canExportCalendar(dateOnly)).toBe(true);
  });

  test('refuses unknown event dates and invalid end times', () => {
    expect(canExportCalendar({ ...event, time_precision: 'unverified' })).toBe(false);
    expect(() => eventCalendar({ ...event, time_precision: 'unverified' }, { now })).toThrow(/Confirm the event date/);
    for (const end_at of [event.start_at, '2026-10-21T09:00:00Z', 'not-a-date']) {
      expect(() => eventCalendar({ ...event, end_at }, { now })).toThrow();
    }
  });

  test('escapes newline property injection and text delimiters without leaking private fields', () => {
    const dirty = {
      ...event, title: 'Jazz, strings; live\\show\r\nATTENDEE:mailto:attacker@example.org',
      location: 'Hall\rBEGIN:VALARM\nTRIGGER:-PT0S',
      reason: 'private reason', preferences_blob: 'private profile', email: 'private@example.org'
    };
    const calendar = unfold(eventCalendar(dirty, { now }));
    const lines = calendar.split('\r\n');
    expect(lines.filter((line) => line === 'BEGIN:VEVENT')).toHaveLength(1);
    expect(lines.some((line) => /^(ATTENDEE|BEGIN:VALARM|TRIGGER)/.test(line))).toBe(false);
    expect(calendar).toContain('SUMMARY:Jazz\\, strings\\; live\\\\show\\nATTENDEE:mailto:attacker@example.org');
    expect(calendar).toContain('LOCATION:Hall\\nBEGIN:VALARM\\nTRIGGER:-PT0S');
    expect(calendar).not.toContain('private');
  });

  test('folds every UTF-8 line at 75 octets without splitting emoji or losing text', () => {
    const title = 'València 🎻 '.repeat(35);
    const calendar = eventCalendar({ ...event, title }, { now });
    for (const line of calendar.split('\r\n')) {
      expect(new TextEncoder().encode(line).length).toBeLessThanOrEqual(75);
      expect(line).not.toMatch(/[\ud800-\udbff]$|^[\udc00-\udfff]/u);
    }
    expect(unfold(calendar)).toContain('SUMMARY:' + title + '\r\n');
    expect(calendar).toContain('\r\n ');
    expect(calendar).not.toMatch(/(?<!\r)\n/);
  });

  test('builds stable event UIDs only from public event facts', () => {
    const uid = (value) => unfold(eventCalendar(value, { now })).split('\r\n').find((line) => line.startsWith('UID:'));
    expect(uid(event)).toBe(uid({ ...event, id: 77, event_key: 'private-id', user_id: 9 }));
    expect(uid(event)).not.toBe(uid({ ...event, url: 'https://example.org/other' }));
    expect(uid(event)).not.toContain(event.event_key);
  });
});
