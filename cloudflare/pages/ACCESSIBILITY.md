# PoC accessibility verification

Last checked: 2026-09-05

This is the lightweight accessibility acceptance pass for the onboarding PoC.
It does not replace a dedicated audit with assistive-technology users.

## Automated checks

- Invalid email submission associates `email-error` with the email field, sets
  `aria-invalid`, and moves focus to the field.
- Submitting a valid step through the form advances onboarding and moves focus to
  the new step heading.
- The progress indicator exposes its current step, total steps, and step name.
- Required selection groups expose their requirement and associated field-level
  errors.
- API tests distinguish invalid input from retryable service and network errors.

Run these checks with `pnpm --dir cloudflare test`.

## Manual PoC pass

- Confirmed that the native form provides keyboard/Enter submission and that all
  interactive controls retain visible focus styling, including visually hidden
  radio buttons and checkboxes through their containing cards.
- Inspected label, legend, alert, live-status, and progress relationships in the
  rendered React markup.
- Emulated Chromium at 375 x 812 and 320 x 568 CSS pixels. In both cases the
  document width equals the viewport width; the only intentionally overflowing
  element is a decorative sea line clipped by the story illustration.
- Confirmed that `prefers-reduced-motion: reduce` reduces nonessential transition
  duration and disables smooth scrolling.

Before a broader public launch, repeat the complete flow with VoiceOver and at
200% browser zoom, and run a contrast audit against the final brand palette.
