import { describe, expect, test } from 'vitest';

import examples from '../shared/jev-preview.examples.json';
import schema from '../shared/jev-preview.schema.json';
import {
  parseDigestPreview,
  savedEventTypes,
  validPreviewEvaluation
} from '../pages/src/preview.js';

const summary = {
  correlation_id: 'fixture-run', dry_run: true, event_count: 1, rendered_count: 1, sent_count: 0
};
const envelope = (evaluation) => ({
  contract_version: 'jev-preview-v1', summary, evaluations: [evaluation]
});

function planningEnvelope() {
  return {
    ...envelope(structuredClone(examples.matched)),
    plans: {
      version: 'brisa-plans-v1', date: '2026-10-22', checked_at: '2026-10-21T20:00:00Z',
      delivery_enabled: false,
      coverage: {
        state: 'complete', collected_count: 1,
        sources: [{ name: 'ajuntament_agenda', status: 'ok', fetched_count: 8, event_count: 1, checked_at: '2026-10-21T20:00:00Z' }]
      },
      recommendations: [{
        id: 7, event_key: 'fixture-jazz', title: 'Jazz in the garden', url: 'https://example.org/jazz',
        start_at: '2026-10-22T19:00:00+02:00', end_at: null, time_precision: 'datetime',
        location: '', description: 'Public listing', source: 'ajuntament_agenda',
        position: 1, reason: 'Suggested from your saved choices.', used_fallback: false, type_decision: 'eligible'
      }],
      excluded_count: 0
    }
  };
}

describe('shared Jev preview contract', () => {
  test.each(Object.entries(examples))('accepts the shared %s example unchanged', (_, example) => {
    expect(validPreviewEvaluation(example)).toBe(true);
    expect(parseDigestPreview(envelope(example), example.selected_event_types).evaluations[0]).toEqual(example);
  });

  test.each(schema.required)('rejects an evaluation without required %s', (key) => {
    const malformed = structuredClone(examples.matched);
    delete malformed[key];
    expect(validPreviewEvaluation(malformed)).toBe(false);
  });

  test.each([
    ['unrecognized property', (value) => { value.provider_raw_response = 'untrusted'; }],
    ['unknown taxonomy', (value) => { value.taxonomy_version = 'event-types-v2'; }],
    ['unsafe event URL', (value) => { value.event.url = 'javascript:alert(1)'; }],
    ['relative event URL', (value) => { value.event.url = '/event'; }],
    ['malformed event URL', (value) => { value.event.url = 'https://'; }],
    ['blank event key', (value) => { value.event.event_key = ''; }],
    ['unknown event property', (value) => { value.event.email = 'fake@example.com'; }],
    ['invalid evaluated time', (value) => { value.evaluated_at = 'tomorrow'; }],
    ['duplicate types', (value) => { value.selected_event_types.push('live_music'); }],
    ['unsupported type', (value) => { value.selected_event_types[0] = 'anything'; }],
    ['Boolean probability', (value) => { value.components[0].p_yes = true; }],
    ['NaN probability', (value) => { value.components[0].p_yes = NaN; }],
    ['out-of-range confidence', (value) => { value.components[0].confidence = 1.1; }],
    ['zero weight', (value) => { value.components[0].weight = 0; }],
    ['negative score', (value) => { value.irrelevance_score = -1; }],
    ['too-high threshold', (value) => { value.threshold = 2; }],
    ['null evaluated score', (value) => { value.irrelevance_score = null; }],
    ['unknown evaluated decision', (value) => { value.decision = 'unknown'; }],
    ['empty evaluated model', (value) => { value.model = ''; }],
    ['null evaluated contribution', (value) => { value.components[0].contribution = null; }],
    ['missing answer', (value) => { value.components.pop(); }],
    ['duplicate answer', (value) => { value.components[1] = value.components[0]; }],
    ['wrong question ID', (value) => { value.components[0].question_id = 'event_type:film'; }],
    ['fallback with components', (value) => { value.status = 'fallback'; }],
    ['uncertain with score', (value) => { value.status = 'uncertain'; }]
  ])('rejects %s', (_, mutate) => {
    const malformed = structuredClone(examples.matched);
    mutate(malformed);
    expect(validPreviewEvaluation(malformed)).toBe(false);
  });

  test('keeps backend decisions and numbers authoritative', () => {
    const result = parseDigestPreview(envelope(examples.threshold_equality), ['food_drink', 'live_music']);
    expect(result.evaluations[0].irrelevance_score).toBe(0.6);
    expect(result.evaluations[0].decision).toBe('eligible');
    expect(result.evaluations[0].components).toEqual(examples.threshold_equality.components);
  });

  test('rejects responses for a different saved selection or with duplicate events', () => {
    expect(() => parseDigestPreview(envelope(examples.matched), ['film'])).toThrow(/try again/i);
    expect(() => parseDigestPreview({ ...envelope(examples.matched), evaluations: [examples.matched, examples.matched] }, examples.matched.selected_event_types)).toThrow(/try again/i);
  });

  test('preserves legacy summaries but rejects unsupported or incomplete envelopes', () => {
    expect(parseDigestPreview({ summary }, ['film']).evaluations).toBeNull();
    expect(() => parseDigestPreview({ summary, evaluations: [] }, ['film'])).toThrow();
    expect(() => parseDigestPreview({ ...envelope(examples.matched), contract_version: 'jev-preview-v2' }, ['live_music', 'food_drink'])).toThrow();
    expect(() => parseDigestPreview({ summary: { ...summary, sent_count: 1 } }, ['film'])).toThrow();
  });

  test.each([-1, 0.5, '0', null, true, NaN, Infinity])('rejects invalid failure_count %s', (failure_count) => {
    expect(() => parseDigestPreview({ summary: { ...summary, failure_count } }, ['film'])).toThrow();
  });

  test.each([
    ['empty', []], ['nonempty', [examples.matched]]
  ])('rejects an incomplete run even when evaluations are %s', (_, evaluations) => {
    const payload = { ...envelope(examples.matched), summary: { ...summary, failure_count: 1 }, evaluations };
    expect(() => parseDigestPreview(payload, examples.matched.selected_event_types)).toThrow('Brisa could not finish this preview. Please try again.');
  });

  test('accepts a successful all-irrelevant run with no rendered digest', () => {
    const payload = { ...envelope(examples.irrelevant), summary: { ...summary, rendered_count: 0, failure_count: 0 } };
    expect(parseDigestPreview(payload, examples.irrelevant.selected_event_types).evaluations).toEqual([examples.irrelevant]);
  });

  test('accepts only complete bounded saved selections and preserves legacy IDs', () => {
    const blob = (names) => JSON.stringify({ top_interest_clusters: names.map((name) => ({ name })) });
    expect(savedEventTypes(blob(['kid-friendly_culture', 'film']))).toEqual(['kid-friendly_culture', 'film']);
    expect(savedEventTypes(blob(['live_music', 'unsupported']))).toBeNull();
    expect(savedEventTypes(blob(['live_music', 'live_music']))).toBeNull();
    expect(savedEventTypes(blob([]))).toBeNull();
    expect(savedEventTypes('{}')).toBeNull();
    expect(savedEventTypes('invalid JSON')).toBeNull();
  });
});

describe('additive planning preview contract', () => {
  test('keeps the authoritative ranked shortlist and public facts intact', () => {
    const payload = planningEnvelope();
    expect(parseDigestPreview(payload, examples.matched.selected_event_types).plans).toEqual(payload.plans);
    const legacy = parseDigestPreview(envelope(examples.matched), examples.matched.selected_event_types);
    expect(legacy.plans).toBeNull();
  });

  test.each([
    ['unknown version', (value) => { value.plans.version = 'unknown'; }],
    ['private top-level field', (value) => { value.plans.user_id = 1; }],
    ['private event field', (value) => { value.plans.recommendations[0].email = 'private@example.org'; }],
    ['unsafe URL', (value) => { value.plans.recommendations[0].url = 'javascript:alert(1)'; }],
    ['credential URL', (value) => { value.plans.recommendations[0].url = 'https://user:password@example.org/jazz'; }],
    ['account URL', (value) => { value.plans.recommendations[0].url = 'https://example.org/api/verify?token=secret'; }],
    ['string id', (value) => { value.plans.recommendations[0].id = '7'; }],
    ['Boolean id', (value) => { value.plans.recommendations[0].id = true; }],
    ['unsafe integer id', (value) => { value.plans.recommendations[0].id = Number.MAX_SAFE_INTEGER + 1; }],
    ['zero id', (value) => { value.plans.recommendations[0].id = 0; }],
    ['invalid event key', (value) => { value.plans.recommendations[0].event_key = 'a\nb'; }],
    ['missing public description', (value) => { delete value.plans.recommendations[0].description; }],
    ['oversized description', (value) => { value.plans.recommendations[0].description = 'a'.repeat(8001); }],
    ['numeric reason', (value) => { value.plans.recommendations[0].reason = 1; }],
    ['non-Boolean fallback', (value) => { value.plans.recommendations[0].used_fallback = 0; }],
    ['unknown decision', (value) => { value.plans.recommendations[0].type_decision = 'recommended'; }],
    ['wrong rank position', (value) => { value.plans.recommendations[0].position = 2; }],
    ['duplicate events', (value) => { value.plans.recommendations.push({ ...value.plans.recommendations[0], position: 2 }); value.summary = { ...value.summary, event_count: 2 }; value.plans.coverage.collected_count = 2; }],
    ['impossible date', (value) => { value.plans.date = '2026-02-30'; }],
    ['invalid check time', (value) => { value.plans.checked_at = 'tomorrow'; }],
    ['null start time', (value) => { value.plans.recommendations[0].start_at = null; }],
    ['unzoned time', (value) => { value.plans.recommendations[0].start_at = '2026-10-22T19:00:00'; }],
    ['invalid precision', (value) => { value.plans.recommendations[0].time_precision = 'estimated'; }],
    ['end before start', (value) => { value.plans.recommendations[0].end_at = '2026-10-21T19:00:00Z'; }],
    ['string delivery state', (value) => { value.plans.delivery_enabled = 'false'; }],
    ['Boolean collection count', (value) => { value.plans.coverage.collected_count = true; }],
    ['wrong collection count', (value) => { value.plans.coverage.collected_count = 2; }],
    ['negative exclusion count', (value) => { value.plans.excluded_count = -1; }],
    ['excess exclusion count', (value) => { value.plans.excluded_count = 2; }],
    ['fractional source count', (value) => { value.plans.coverage.sources[0].fetched_count = 0.5; }],
    ['unknown source status', (value) => { value.plans.coverage.sources[0].status = 'failed'; }],
    ['private source details', (value) => { value.plans.coverage.sources[0].raw_error = 'private'; }],
    ['null source time', (value) => { value.plans.coverage.sources[0].checked_at = null; }],
    ['duplicate source', (value) => { value.plans.coverage.sources.push({ ...value.plans.coverage.sources[0] }); }],
    ['inconsistent coverage state', (value) => { value.plans.coverage.state = 'unavailable'; }],
    ['excess sources', (value) => { value.plans.coverage.sources = Array.from({ length: 33 }, (_, i) => ({ ...value.plans.coverage.sources[0], name: 'source-' + i })); }],
    ['excess recommendations', (value) => { value.plans.recommendations = Array.from({ length: 101 }, (_, i) => ({ ...value.plans.recommendations[0], id: i + 1, event_key: 'event-' + i, position: i + 1 })); value.summary = { ...value.summary, event_count: 101 }; value.plans.coverage.collected_count = 101; }]
  ])('rejects %s without falling back to misleading legacy output', (_, mutate) => {
    const payload = planningEnvelope();
    mutate(payload);
    expect(() => parseDigestPreview(payload, examples.matched.selected_event_types)).toThrow(/read this preview safely/);
  });

  test('does not accept unversioned, null, or mismatched-date plans', () => {
    const payload = planningEnvelope();
    expect(() => parseDigestPreview({ ...payload, plans: null }, examples.matched.selected_event_types)).toThrow();
    expect(() => parseDigestPreview({ summary, plans: payload.plans }, ['film'])).toThrow();
    payload.summary = { ...summary, digest_date: '2026-10-23' };
    expect(() => parseDigestPreview(payload, examples.matched.selected_event_types)).toThrow();
  });

  test('accepts partial and unavailable coverage without relabeling them as empty', () => {
    const payload = planningEnvelope();
    payload.plans.coverage.sources.push({ name: 'other_source', status: 'error', fetched_count: 0, event_count: 0, checked_at: payload.plans.checked_at });
    payload.plans.coverage.state = 'partial';
    expect(parseDigestPreview(payload, examples.matched.selected_event_types).plans.coverage.state).toBe('partial');
    payload.plans.coverage.sources.forEach((source) => { source.status = 'error'; });
    payload.plans.coverage.state = 'unavailable';
    expect(parseDigestPreview(payload, examples.matched.selected_event_types).plans.coverage.state).toBe('unavailable');
  });
});
