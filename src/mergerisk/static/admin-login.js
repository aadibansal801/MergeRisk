const form = document.querySelector('#login');
const message = document.querySelector('#message');

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = form.querySelector('[type="submit"]');
  message.hidden = true;
  button.disabled = true;
  try {
    const response = await fetch('/admin/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: form.elements.email.value, password: form.elements.password.value }),
    });
    if (response.ok) {
      location.assign('/admin');
      return;
    }
    const detail = await response.json().catch(() => ({}));
    message.textContent = typeof detail.detail === 'string' ? detail.detail : 'Sign-in failed. Try again.';
  } catch {
    message.textContent = 'Could not reach the server. Try again.';
  }
  message.hidden = false;
  button.disabled = false;
  form.elements.password.value = '';
});
