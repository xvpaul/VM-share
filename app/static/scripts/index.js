// Menu + Auth modal
const menuBtn    = document.getElementById('menu-button');
const menuPanel  = document.getElementById('menu-panel');
const authBtn    = document.getElementById('auth-btn');
const logoutBtn  = document.getElementById('logout-btn');
const authModal  = document.getElementById('auth-modal');
const closeAuth  = document.getElementById('close-auth');

// Tab switching
const tabLogin   = document.getElementById("tab-login");
const tabSignup  = document.getElementById("tab-signup");
const loginForm  = document.getElementById("login-form");
const signupForm = document.getElementById("signup-form");
const authMsg    = document.getElementById("auth-msg");

tabLogin.addEventListener("click", () => {
  loginForm.classList.remove("hidden");
  signupForm.classList.add("hidden");
  tabLogin.classList.add("border-sky-500", "text-white");
  tabSignup.classList.remove("border-sky-500", "text-white");
  tabSignup.classList.add("text-white/60");
});

tabSignup.addEventListener("click", () => {
  signupForm.classList.remove("hidden");
  loginForm.classList.add("hidden");
  tabSignup.classList.add("border-sky-500", "text-white");
  tabLogin.classList.remove("border-sky-500", "text-white");
  tabLogin.classList.add("text-white/60");
});

// Toggle login/logout button visibility based on token
function updateAuthUI() {
  const hasToken = !!localStorage.getItem('token');
  authBtn.classList.toggle('hidden',  hasToken);
  logoutBtn.classList.toggle('hidden', !hasToken);
}

// Menu open/close
menuBtn.addEventListener('click', e => {
  e.stopPropagation();
  menuPanel.classList.toggle('hidden');
});

// Open auth modal
authBtn.addEventListener('click', e => {
  e.stopPropagation();
  authModal.classList.remove('hidden');
  menuPanel.classList.add('hidden');
});

// Logout action
logoutBtn.addEventListener('click', () => {
  localStorage.removeItem('token');
  updateAuthUI();
  menuPanel.classList.add('hidden');
});

// Close modal
closeAuth.addEventListener('click', () => {
  authModal.classList.add('hidden');
});

// Handle login form
loginForm.addEventListener('submit', async e => {
  e.preventDefault();
  const login    = document.getElementById('login-input').value.trim();
  const password = document.getElementById('password-input').value;

  try {
    const resp = await fetch('/login', {
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
      authMsg.textContent = `Login failed: ${data.detail || data.message || "Unknown error"}`;
      return;
    }

    authMsg.textContent = '';
    alert(`Logged in as: ${login}`);
    if (data.access_token) {
      localStorage.setItem('token', data.access_token);
      updateAuthUI();
    }
    authModal.classList.add('hidden');

  } catch (err) {
    console.error(err);
    authMsg.textContent = 'An error occurred: ' + err.message;
  }
});

// Handle signup form
signupForm.addEventListener('submit', async e => {
  e.preventDefault();
  const login    = document.getElementById('signup-login').value.trim();
  const password = document.getElementById('signup-password').value;

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
      authMsg.textContent = `Registration failed: ${data.detail || data.message || "Unknown error"}`;
      return;
    }

    authMsg.textContent = '';
    alert(`Success! Logged in as: ${login}`);
    if (data.access_token) {
      localStorage.setItem('token', data.access_token);
      updateAuthUI();
    }
    authModal.classList.add('hidden');

  } catch (err) {
    console.error(err);
    authMsg.textContent = 'An error occurred: ' + err.message;
  }
});

// Global keyboard + click
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

// VM choice logic
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
    const token = localStorage.getItem('token');
    if (!token) {
      alert('You must log in first.');
      return;
    }

    try {
      const resp = await fetch('/api/run-script', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({})
      });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      if (data.redirect) {
        setTimeout(() => window.location.href = data.redirect, 300);
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

// Init
updateAuthUI();
