// Menu + Auth modal
const menuBtn    = document.getElementById('menu-button');
const menuPanel  = document.getElementById('menu-panel');
const authBtn    = document.getElementById('auth-btn');
const authModal  = document.getElementById('auth-modal');
const closeAuth  = document.getElementById('close-auth');
const authForm   = document.getElementById('auth-form');

menuBtn.addEventListener('click', e => {
  e.stopPropagation();
  menuPanel.classList.toggle('hidden');
});

authBtn.addEventListener('click', e => {
  e.stopPropagation();
  authModal.classList.remove('hidden');
  menuPanel.classList.add('hidden');
});

closeAuth.addEventListener('click', () => {
  authModal.classList.add('hidden');
});

authForm.addEventListener('submit', async e => {
  e.preventDefault();
  const login    = document.getElementById('login-input').value.trim();
  const password = document.getElementById('password-input').value;

  try {
    const resp = await fetch('/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ login, password })
    });
    const text = await resp.text();
    let data;

    try {
      data = JSON.parse(text);
    } catch {
      throw new Error(`Server error (${resp.status}): ${text}`);
    }

    if (!resp.ok) {
      alert(`Registration failed: ${data.detail || data.message || "Unknown error"}`);
      return;
    }

    alert(`Success! Logged in as: ${login}`);
    if (data.access_token) localStorage.setItem('token', data.access_token);
    authModal.classList.add('hidden');

  } catch (err) {
    console.error(err);
    alert('An error occurred: ' + err.message);
  }
});

// Global key + click handlers
window.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    authModal.classList.add('hidden');
    document.getElementById('vm-choice').classList.add('hidden');
    document.getElementById('reveal-btn').classList.remove('hidden');
  }
});

window.addEventListener('click', e => {
  if (e.target === authModal) {
    authModal.classList.add('hidden');
  }
});

// VM choice reveal logic
(function() {
  const wrap         = document.getElementById('toggle-wrap');
  const revealBtn    = document.getElementById('reveal-btn');
  const choiceCtr    = document.getElementById('vm-choice');
  const alpineBtn    = document.getElementById('alpine-btn');
  const ubuntuBtn    = document.getElementById('ubuntu-btn');

  revealBtn.addEventListener('mouseenter', () => {
    revealBtn.classList.add('hidden');
    choiceCtr.classList.remove('hidden');
  });

  wrap.addEventListener('mouseleave', () => {
    choiceCtr.classList.add('hidden');
    revealBtn.classList.remove('hidden');
  });

  alpineBtn.addEventListener('click', async () => {
    try {
      const resp = await fetch('/api/run-script', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({})
      });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      if (data.redirect) {
        setTimeout(() => {
          window.location.href = data.redirect;
        }, 300);
      }
    } catch (err) {
      console.error(err);
      alert('Error running script: ' + err.message);
    }
  });

  ubuntuBtn.addEventListener('click', () => {
    alert('Ubuntu VM is not implemented yet.');
  });
})();
