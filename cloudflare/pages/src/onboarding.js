import { AUDIENCE_OPTIONS, validInterestSelection } from './profile.js';

const EMAIL_PATTERN = /^\S+@\S+\.\S+$/;

export function validateEmail(email) {
  return EMAIL_PATTERN.test(email.trim())
    ? null
    : { field: 'email', message: 'Enter a valid email address.' };
}

export function onboardingStepFor(field) {
  return field === 'email' ? 3 : field === 'interests' ? 1 : 0;
}

export function validateOnboardingStep(step, form) {
  if ((step === 0 || step === 3) && !AUDIENCE_OPTIONS.some(({ value }) => value === form.audience)) {
    return { field: 'audience', message: 'Choose who you are planning for.' };
  }
  if ((step === 0 || step === 3) && form.locations.length === 0) {
    return { field: 'locations', message: 'Choose at least one search area.' };
  }
  if ((step === 1 || step === 3) && !validInterestSelection(form.interests)) {
    return { field: 'interests', message: 'Choose at least one event type from the list.' };
  }
  return step === 3 ? validateEmail(form.email) : null;
}

export function validationTargetId(field) {
  return field === 'email' ? 'email' : `${field}-fieldset`;
}
