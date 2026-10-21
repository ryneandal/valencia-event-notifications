import { validInterestSelection } from './profile.js';

const EMAIL_PATTERN = /^\S+@\S+\.\S+$/;

export function validateOnboardingStep(step, form) {
  if (step === 0 && !EMAIL_PATTERN.test(form.email.trim())) {
    return { field: 'email', message: 'Enter a valid email address.' };
  }
  if (step === 2 && form.locations.length === 0) {
    return { field: 'locations', message: 'Choose at least one search area.' };
  }
  if (step === 3 && !validInterestSelection(form.interests)) {
    return { field: 'interests', message: 'Choose at least one event type from the list.' };
  }
  return null;
}

export function validationTargetId(field) {
  return field === 'email' ? 'email' : `${field}-fieldset`;
}
