import schema from '../../shared/jev-preview.schema.json';
import { INTEREST_CLUSTERS, validInterestSelection } from './profile.js';
import { boundedText, safePublicUrl, validDate, validPublicEvent, validTimestamp } from './planning.js';

export const PREVIEW_CONTRACT_VERSION = 'jev-preview-v1';

const typeChecks = {
  object: (value) => value !== null && typeof value === 'object' && !Array.isArray(value),
  array: Array.isArray,
  string: (value) => typeof value === 'string',
  number: (value) => typeof value === 'number' && Number.isFinite(value),
  null: (value) => value === null
};

function isWebUrl(value) {
  return safePublicUrl(value);
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
    if (rule.format === 'date-time' && !validTimestamp(value)) return false;
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

function exactKeys(value, keys) {
  return typeChecks.object(value) && Object.keys(value).length === keys.length &&
    keys.every((key) => Object.hasOwn(value, key));
}

const count = (value, max = 1_000_000) => Number.isSafeInteger(value) && value >= 0 && value <= max;
const recommendationKeys = ['id', 'event_key', 'title', 'url', 'start_at', 'end_at', 'time_precision', 'location', 'description', 'source', 'position', 'reason', 'used_fallback', 'type_decision'];

export function validPreviewPlans(plans, summary) {
  if (!exactKeys(plans, ['version', 'date', 'checked_at', 'delivery_enabled', 'coverage', 'recommendations', 'excluded_count']) ||
      plans.version !== 'brisa-plans-v1' || !validDate(plans.date) ||
      !validTimestamp(plans.checked_at) || typeof plans.delivery_enabled !== 'boolean' ||
      !exactKeys(plans.coverage, ['state', 'collected_count', 'sources']) ||
      !count(plans.coverage.collected_count) || plans.coverage.collected_count !== summary.event_count ||
      !count(plans.excluded_count, plans.coverage.collected_count) ||
      !Array.isArray(plans.coverage.sources) || plans.coverage.sources.length > 32 ||
      !Array.isArray(plans.recommendations) || plans.recommendations.length > 100 ||
      plans.recommendations.length > plans.coverage.collected_count) return false;
  if (summary.digest_date !== undefined && plans.date !== summary.digest_date) return false;
  const sourceNames = new Set();
  for (const source of plans.coverage.sources) {
    if (!exactKeys(source, ['name', 'status', 'fetched_count', 'event_count', 'checked_at']) ||
        !boundedText(source.name, 80, 1) || sourceNames.has(source.name) ||
        !['ok', 'error'].includes(source.status) ||
        !count(source.fetched_count) || !count(source.event_count) ||
        !validTimestamp(source.checked_at)) return false;
    sourceNames.add(source.name);
  }
  const checked = plans.coverage.sources.filter((source) => source.status === 'ok').length;
  const expected = checked === 0 ? 'unavailable' : checked === plans.coverage.sources.length ? 'complete' : 'partial';
  if (plans.coverage.state !== expected) return false;
  const ids = new Set();
  const keys = new Set();
  for (const [index, event] of plans.recommendations.entries()) {
    if (!exactKeys(event, recommendationKeys) || !validPublicEvent(event) ||
        ids.has(event.id) || keys.has(event.event_key) || event.position !== index + 1 ||
        !boundedText(event.reason, 180, 1) || typeof event.used_fallback !== 'boolean' ||
        !['eligible', 'irrelevant', 'unknown'].includes(event.type_decision)) return false;
    ids.add(event.id);
    keys.add(event.event_key);
  }
  return true;
}

export function parseDigestPreview(payload, selectedTypes) {
  const fail = () => {
    throw new Error('We could not read this preview safely. Please try again.');
  };
  if (!validInterestSelection(selectedTypes)) fail();
  const summary = payload?.summary;
  if (!summary || typeof summary.correlation_id !== 'string' || summary.dry_run !== true ||
      summary.sent_count !== 0 || !Number.isInteger(summary.event_count) || summary.event_count < 0 ||
      !Number.isInteger(summary.rendered_count) || summary.rendered_count < 0) fail();
  if (summary.failure_count !== undefined &&
      (!Number.isInteger(summary.failure_count) || summary.failure_count < 0)) fail();
  if (summary.failure_count > 0) {
    throw new Error('Brisa could not finish this preview. Please try again.');
  }
  const plans = payload.plans === undefined ? null : payload.plans;
  if (plans !== null && !validPreviewPlans(plans, summary)) fail();
  if (Object.hasOwn(payload, 'plans') && plans === null) fail();

  // Older Workers return summary only while the feature is off.
  if (payload.contract_version === undefined && payload.evaluations === undefined) {
    // The new plans extension belongs to the versioned envelope.
    if (plans !== null) fail();
    return { summary, evaluations: null, selectedTypes, plans: null };
  }
  if (payload.contract_version !== PREVIEW_CONTRACT_VERSION || !Array.isArray(payload.evaluations)) fail();
  const seen = new Set();
  for (const evaluation of payload.evaluations) {
    if (!validPreviewEvaluation(evaluation) || seen.has(evaluation.event.event_key) ||
        evaluation.selected_event_types.length !== selectedTypes.length ||
        !selectedTypes.every((type) => evaluation.selected_event_types.includes(type))) fail();
    seen.add(evaluation.event.event_key);
  }
  return { summary, evaluations: payload.evaluations, selectedTypes, plans };
}
