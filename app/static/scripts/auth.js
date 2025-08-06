export function setupAuth() {
  const authBtn    = document.getElementById('auth-btn');
  const logoutBtn  = document.getElementById('logout-btn');
  const authModal  = document.getElementById('auth-modal');
  const closeAuth  = document.getElementById('close-auth');
  const tabLogin   = document.getElementById("tab-login");
  const tabSignup  = document.getElementById("tab-signup");
  const loginForm  = document.getElementById("login-form");
  const signupForm = document.getElementById("signup-form");
  const authMsg    = document.getElementById("auth-msg");

  function updateAuthUI() {
    const hasToken = !!localStorage.getItem('token');
    authBtn.classList.toggle('hidden',  hasToken);
    logoutBtn.classList.toggle('hidden', !hasToken);
  }

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

  authBtn.addEventListener('click', e => {
    e.stopPropagation();
    authModal.classList.remove('hidden');
    document.getElementById('menu-panel')?.classList.add('hidden');
  });

  closeAuth.addEventListener('click', () => {
    authModal.classList.add('hidden');
  });

  logoutBtn.addEventListener('click', () => {
    localStorage.removeItem('token');
    updateAuthUI();
    document.getElementById('menu-panel')?.classList.add('hidden');
  });

  loginForm.addEventListener('submit', async e => {
    e.preventDefault();
    const login    = document.getElementById('login-input').value.trim();
    const password = document.getElementById('password-input').value;
    await handleAuth('/login', login, password);
  });

  signupForm.addEventListener('submit', async e => {
    e.preventDefault();
    const login    = document.getElementById('signup-login').value.trim();
    const password = document.getElementById('signup-password').value;
    await handleAuth('/register', login, password);
  });

  async function handleAuth(endpoint, login, password) {
    try {
      const resp = await fetch(endpoint, {
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
        authMsg.textContent = `Auth failed: ${data.detail || data.message || "Unknown error"}`;
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
  }

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

  return { updateAuthUI };
}