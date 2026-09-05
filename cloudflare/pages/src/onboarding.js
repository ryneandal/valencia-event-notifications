const EMAIL_PATTERN = /^\S+@\S+\.\S+$/;

export function validateOnboardingStep(step, form) {
  if (step === 0 && !EMAIL_PATTERN.test(form.email.trim())) {
    return { field: 'email', message: 'Enter a valid email address.' };
  }
  if (step === 2 && form.locations.length === 0) {
    return { field: 'locations', message: 'Choose at least one search area.' };
  }
  if (step === 3 && form.interests.length === 0) {
    return { field: 'interests', message: 'Choose at least one interest cluster.' };
  }
  return null;
}

export function validationTargetId(field) {
  return field === 'email' ? 'email' : `${field}-fieldset`;
}
