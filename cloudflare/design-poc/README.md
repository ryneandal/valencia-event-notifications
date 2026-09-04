# Brisa design PoC

Brisa is a static, SPA-style onboarding exploration for the València Next-Day Events Digest. It presents sign-up and preference capture as a small daily cultural ritual: calm enough to complete with coffee, warm enough to feel local, and clear about how preferences shape the automated digest.

## Aesthetic direction

- **Palette:** deep sea navy and muted Mediterranean teal provide trust and structure; cream paper, citrus yellow, sun orange, and terracotta coral bring in beach light and Valencia's tiled, warm character.
- **Type:** Fraunces gives the editorial moments a human, slightly literary voice; DM Sans keeps dashboard copy practical; DM Mono marks metadata and system labels.
- **Shape and texture:** generous paper-like surfaces, small radii, hand-drawn-feeling wave lines, and CSS-built event artwork keep the interface tactile without requiring image assets or a build step.
- **Components:** split editorial welcome panel, five-step progress journey, email capture, household/audience choices, interest chips, location/timing/accessibility controls, review state, privacy reassurance, and a digest-ready success state with a small illustrative preview.

## Preview

No dependencies or build tooling are required. Open [`index.html`](index.html) directly in a browser, or serve this directory for a more realistic local preview:

```bash
python3 -m http.server 4173 --directory cloudflare/design-poc
```

Then visit `http://localhost:4173`. The Google Fonts import is optional; the layout falls back to system fonts when offline. The UI interactions are intentionally demo-only: completing onboarding stores a representative preferences object in `localStorage` and does not call the production API.
