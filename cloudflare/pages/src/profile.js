export const AUDIENCE_OPTIONS = [
  { value: 'solo_adult', label: 'Just me', detail: 'A personal shortlist' },
  { value: 'couple', label: 'Two of us', detail: 'Plans that work as a pair' },
  {
    value: 'family_with_school_age_kids',
    label: 'Our family',
    detail: 'School-age children included'
  },
  { value: 'friends_group', label: 'Friends', detail: 'Ideas for a small group' }
];

export const LOCATION_OPTIONS = [
  { value: 'Valencia city', label: 'València city', detail: 'Easy city plans' },
  { value: 'Valencia metro area', label: 'Metro area', detail: 'Nearby towns and coast' },
  {
    value: 'easy day trips (<=60-90 min)',
    label: 'Day trips',
    detail: 'Up to 60–90 minutes away'
  }
];

export const INTEREST_CLUSTERS = [
  {
    name: 'local_festivals_spectacle',
    label: 'Festivals & spectacle',
    icon: '✦',
    includes: ['parades', 'fireworks', 'street art/monuments', 'processions', 'flower battles']
  },
  {
    name: 'hands_on_learning',
    label: 'Hands-on discovery',
    icon: '◌',
    includes: [
      'science museum',
      'interactive exhibits',
      'kids workshops',
      'aquarium/planetarium/IMAX-style shows'
    ]
  },
  {
    name: 'animals_and_nature',
    label: 'Animals & nature',
    icon: '⌁',
    includes: ['zoo/animal park', 'keeper talks', 'boat trips', 'wetlands/birding', 'sunset nature']
  },
  {
    name: 'parks_and_play',
    label: 'Parks & play',
    icon: '☼',
    includes: ['destination playgrounds', 'Turia-style park events', 'picnics', 'bike-friendly outings']
  },
  {
    name: 'kid-friendly_culture',
    label: 'Culture for everyone',
    icon: '◒',
    includes: ['craft markets', 'family theatre/puppets', 'street performances', 'museum family days']
  }
];

export const POSITIVE_SIGNAL_OPTIONS = [
  ['kid_focused', 'Made for children'],
  ['interactive', 'Interactive'],
  ['workshop', 'Workshops'],
  ['animals', 'Animals'],
  ['outdoors', 'Outdoors'],
  ['park', 'Parks'],
  ['daytime', 'Daytime'],
  ['stroller_friendly', 'Stroller-friendly'],
  ['accessible', 'Accessible'],
  ['near_transit', 'Near public transit'],
  ['short_duration_or_drop_in', 'Short or drop-in']
];

export const NEGATIVE_SIGNAL_OPTIONS = [
  ['starts_after_20', 'Starts after 20:00'],
  ['adult_nightlife', 'Adult nightlife'],
  ['very_loud_no_family_area', 'Very loud without a family area'],
  ['crowd_extreme', 'Extreme crowds'],
  ['long_static_format', 'Long, seated formats']
];

export const SEASONAL_ANCHORS = [
  {
    name: 'Fallas',
    label: 'Fallas',
    months: ['Feb', 'Mar'],
    notes: 'daytime monument walks; mascleta/fireworks are loud'
  },
  {
    name: 'Semana_Santa_Marinera',
    label: 'Semana Santa Marinera',
    months: ['Mar', 'Apr'],
    notes: 'processions in maritime districts'
  },
  {
    name: 'Gran_Feria_de_Julio',
    label: 'Gran Fira de Juliol',
    months: ['Jul'],
    notes: 'citywide summer culture nights + finale events'
  },
  {
    name: 'La_Tomatina_Bunol_day_trip',
    label: 'La Tomatina day trip',
    months: ['Aug'],
    notes: 'ticketed; huge crowds; messy novelty'
  }
];

export const DEFAULT_FORM_STATE = {
  email: '',
  audience: 'family_with_school_age_kids',
  locations: ['Valencia city'],
  interests: ['local_festivals_spectacle', 'parks_and_play'],
  positiveSignals: ['interactive', 'outdoors', 'daytime', 'near_transit'],
  negativeSignals: ['starts_after_20', 'crowd_extreme'],
  seasonalAnchors: ['Fallas', 'Gran_Feria_de_Julio']
};

export function buildPersonalizationProfile(formState) {
  const selectedInterests = new Set(formState.interests);
  const selectedAnchors = new Set(formState.seasonalAnchors);

  return {
    audience: formState.audience,
    location_scope: LOCATION_OPTIONS.filter(({ value }) =>
      formState.locations.includes(value)
    ).map(({ value }) => value),
    top_interest_clusters: INTEREST_CLUSTERS.filter(({ name }) =>
      selectedInterests.has(name)
    ).map(({ name, includes }) => ({ name, includes })),
    strong_positive_signals: POSITIVE_SIGNAL_OPTIONS.map(([value]) => value).filter(
      (value) => formState.positiveSignals.includes(value)
    ),
    strong_negative_signals: NEGATIVE_SIGNAL_OPTIONS.map(([value]) => value).filter(
      (value) => formState.negativeSignals.includes(value)
    ),
    seasonal_anchors: SEASONAL_ANCHORS.filter(({ name }) => selectedAnchors.has(name)).map(
      ({ name, months, notes }) => ({ name, months, notes })
    )
  };
}

export function hydrateFormState(email, preferencesBlob) {
  if (!preferencesBlob) return { ...DEFAULT_FORM_STATE, email: email || '' };

  try {
    const profile = JSON.parse(preferencesBlob);
    return {
      email: email || '',
      audience: profile.audience || DEFAULT_FORM_STATE.audience,
      locations: Array.isArray(profile.location_scope)
        ? profile.location_scope
        : DEFAULT_FORM_STATE.locations,
      interests: Array.isArray(profile.top_interest_clusters)
        ? profile.top_interest_clusters.map(({ name }) => name)
        : DEFAULT_FORM_STATE.interests,
      positiveSignals: Array.isArray(profile.strong_positive_signals)
        ? profile.strong_positive_signals
        : DEFAULT_FORM_STATE.positiveSignals,
      negativeSignals: Array.isArray(profile.strong_negative_signals)
        ? profile.strong_negative_signals
        : DEFAULT_FORM_STATE.negativeSignals,
      seasonalAnchors: Array.isArray(profile.seasonal_anchors)
        ? profile.seasonal_anchors.map(({ name }) => name)
        : DEFAULT_FORM_STATE.seasonalAnchors
    };
  } catch {
    return { ...DEFAULT_FORM_STATE, email: email || '' };
  }
}
