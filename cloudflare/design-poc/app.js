(() => {
  const steps = [...document.querySelectorAll('.step')];
  const progress = document.querySelector('#progress-bar');
  const stepLabel = document.querySelector('#step-label');
  const next = document.querySelector('#next-button');
  const back = document.querySelector('#back-button');
  const toast = document.querySelector('#toast');
  const success = document.querySelector('#success-screen');
  let current = 1;
  let toastTimer;

  const showToast = (message) => {
    toast.textContent = message;
    toast.classList.add('is-visible');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove('is-visible'), 2500);
  };

  const updateReview = () => {
    const email = document.querySelector('#email').value.trim() || 'you@example.com';
    const audience = document.querySelector('input[name="audience"]:checked');
    const audienceNames = {'just-me': 'Just me', two: 'Two of us', family: 'Our family', friends: 'My friends & me'};
    const interests = [...document.querySelectorAll('input[name="interest"]:checked')].map((input) => input.closest('label').querySelector('span:nth-of-type(2)').textContent);
    const timing = document.querySelector('input[name="time"]:checked')?.value === 'evening' ? 'The evening before at 18:00' : 'Tomorrow at 07:30';
    document.querySelector('#review-email').textContent = email;
    document.querySelector('#review-audience').textContent = audienceNames[audience?.value] || 'Just me';
    document.querySelector('#review-interests').textContent = interests.length ? interests.join(', ') : 'A little bit of everything';
    document.querySelector('#review-timing').textContent = timing;
    document.querySelector('#success-email').textContent = email;
  };

  const showStep = (number) => {
    current = Math.max(1, Math.min(5, number));
    steps.forEach((step) => { step.hidden = Number(step.dataset.step) !== current; });
    progress.style.width = `${current * 20}%`;
    stepLabel.innerHTML = `Step ${String(current).padStart(2, '0')} <span>of 05</span>`;
    back.hidden = current === 1;
    next.innerHTML = current === 5 ? 'Create my digest <svg aria-hidden="true"><use href="#i-arrow"></use></svg>' : 'Continue <svg aria-hidden="true"><use href="#i-arrow"></use></svg>';
    if (current === 5) updateReview();
    document.querySelector('.form-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  next.addEventListener('click', () => {
    if (current === 1 && !document.querySelector('#email').checkValidity()) { document.querySelector('#email').reportValidity(); return; }
    if (current < 5) { showStep(current + 1); return; }
    const preferences = { email: document.querySelector('#email').value.trim(), audience: document.querySelector('input[name="audience"]:checked')?.value, interests: [...document.querySelectorAll('input[name="interest"]:checked')].map((input) => input.value), area: document.querySelector('#area').value, timing: document.querySelector('input[name="time"]:checked')?.value, accessible: document.querySelector('.toggle-row input').checked };
    localStorage.setItem('brisa-preferences', JSON.stringify(preferences));
    success.hidden = false;
    showToast('Your preferences are safely saved');
  });
  back.addEventListener('click', () => showStep(current - 1));
  document.querySelectorAll('[data-back]').forEach((button) => button.addEventListener('click', () => showStep(Number(button.dataset.back))));
  document.querySelectorAll('.interest-chip').forEach((chip) => chip.addEventListener('click', () => chip.classList.toggle('is-checked', chip.querySelector('input').checked)));
  document.querySelector('[data-action="login"]').addEventListener('click', () => showToast('Sign in is coming soon — this is a design preview'));
  document.querySelector('.close-button').addEventListener('click', () => showToast('Your progress is kept on this device'));
  document.querySelector('[data-action="restart"]').addEventListener('click', () => { success.hidden = true; showStep(1); });
})();
