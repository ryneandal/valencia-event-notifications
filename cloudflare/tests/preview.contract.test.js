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
