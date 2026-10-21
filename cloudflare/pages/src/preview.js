import schema from '../../shared/jev-preview.schema.json';
import { INTEREST_CLUSTERS, validInterestSelection } from './profile.js';

export const PREVIEW_CONTRACT_VERSION = 'jev-preview-v1';

const typeChecks = {
  object: (value) => value !== null && typeof value === 'object' && !Array.isArray(value),
  array: Array.isArray,
  string: (value) => typeof value === 'string',
  number: (value) => typeof value === 'number' && Number.isFinite(value),
  null: (value) => value === null
};

function isWebUrl(value) {
  try {
    return /^https?:\/\//.test(value) && ['https:', 'http:'].includes(new URL(value).protocol);
  } catch {
    return false;
  }
}

// Implements the keywords used by the frozen v1 schema, shared with the Worker.
// A future schema version must review this boundary before the UI accepts it.
function matchesSchema(value, rule) {
  if (rule.$ref) return matchesSchema(value, schema.$defs[rule.$ref.split('/').at(-1)]);
  if (rule.type && ![rule.type].flat().some((type) => typeChecks[type]?.(value))) return false;
  if ('const' in rule && value !== rule.const) return false;
  if (rule.enum && !rule.enum.includes(value)) return false;
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return false;
    if (rule.minimum !== undefined && value < rule.minimum) return false;
    if (rule.maximum !== undefined && value > rule.maximum) return false;
    if (rule.exclusiveMinimum !== undefined && value <= rule.exclusiveMinimum) return false;
  }
  if (typeof value === 'string') {
    if (rule.minLength !== undefined && value.length < rule.minLength) return false;
    if (rule.pattern && !new RegExp(rule.pattern).test(value)) return false;
    if (rule.format === 'uri' && !isWebUrl(value)) return false;
    if (rule.format === 'date-time' && (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/i.test(value) || !Number.isFinite(Date.parse(value)))) return false;
  }
  if (Array.isArray(value)) {
    if (rule.minItems !== undefined && value.length < rule.minItems) return false;
    if (rule.maxItems !== undefined && value.length > rule.maxItems) return false;
    if (rule.uniqueItems && new Set(value.map((item) => JSON.stringify(item))).size !== value.length) return false;
    if (rule.items && !value.every((item) => matchesSchema(item, rule.items))) return false;
  }
  if (typeChecks.object(value)) {
    if (rule.required?.some((key) => !Object.hasOwn(value, key))) return false;
    if (rule.additionalProperties === false && Object.keys(value).some((key) => !Object.hasOwn(rule.properties || {}, key))) return false;
    if (Object.entries(rule.properties || {}).some(([key, child]) => Object.hasOwn(value, key) && !matchesSchema(value[key], child))) return false;
  }
  if (rule.allOf && !rule.allOf.every((child) => matchesSchema(value, child))) return false;
  if (rule.if && matchesSchema(value, rule.if) && rule.then && !matchesSchema(value, rule.then)) return false;
  return true;
}

export function validPreviewEvaluation(value) {
  if (!matchesSchema(value, schema)) return false;
  if (value.status === 'fallback') return true;
  const types = value.components.map((component) => component.event_type);
  return types.length === value.selected_event_types.length &&
    new Set(types).size === types.length &&
    value.components.every((component) =>
      value.selected_event_types.includes(component.event_type) &&
      component.question_id === `event_type:${component.event_type}`
    );
}

export function savedEventTypes(preferencesBlob) {
  try {
    const types = JSON.parse(preferencesBlob).top_interest_clusters.map(({ name }) => name);
    return validInterestSelection(types) ? types : null;
  } catch {
    return null;
  }
}

export function eventTypeLabel(name) {
  return INTEREST_CLUSTERS.find((type) => type.name === name)?.label || name;
}

export function parseDigestPreview(payload, selectedTypes) {
  const fail = () => {
    throw new Error('We could not read this preview safely. Please try again.');
  };
  const summary = payload?.summary;
  if (!summary || typeof summary.correlation_id !== 'string' || summary.dry_run !== true ||
      summary.sent_count !== 0 || !Number.isInteger(summary.event_count) || summary.event_count < 0 ||
      !Number.isInteger(summary.rendered_count) || summary.rendered_count < 0) fail();
  if (summary.failure_count !== undefined &&
      (!Number.isInteger(summary.failure_count) || summary.failure_count < 0)) fail();
  if (summary.failure_count > 0) {
    throw new Error('Brisa could not finish this preview. Please try again.');
  }

  // Older Workers return summary only while the feature is off.
  if (payload.contract_version === undefined && payload.evaluations === undefined) {
    return { summary, evaluations: null, selectedTypes };
  }
  if (payload.contract_version !== PREVIEW_CONTRACT_VERSION || !Array.isArray(payload.evaluations)) fail();
  const seen = new Set();
  for (const evaluation of payload.evaluations) {
    if (!validPreviewEvaluation(evaluation) || seen.has(evaluation.event.event_key) ||
        evaluation.selected_event_types.length !== selectedTypes.length ||
        !selectedTypes.every((type) => evaluation.selected_event_types.includes(type))) fail();
    seen.add(evaluation.event.event_key);
  }
  return { summary, evaluations: payload.evaluations, selectedTypes };
}
