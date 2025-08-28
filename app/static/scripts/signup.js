// ===== Tabs =====
const tabSignin   = document.getElementById('tab-signin');
const tabSignup   = document.getElementById('tab-signup');
const panelSignin = document.getElementById('panel-signin');
const panelSignup = document.getElementById('panel-signup');

function activate(tab) {
  const isSignIn = tab === 'signin';
  tabSignin.setAttribute('aria-selected', String(isSignIn));
  tabSignup.setAttribute('aria-selected', String(!isSignIn));
  if (isSignIn) { tabSignin.dataset.active = "true"; delete tabSignup.dataset.active; }
  else { tabSignup.dataset.active = "true"; delete tabSignin.dataset.active; }
  panelSignin.classList.toggle('hidden', !isSignIn);
  panelSignup.classList.toggle('hidden', isSignIn);
}
tabSignin.addEventListener('click', () => activate('signin'));
tabSignup.addEventListener('click', () => activate('signup'));

// Helper to read JSON error safely
async function readJsonSafe(res) {
  try { return await res.json(); } catch { return {}; }
}

// ===== Sign In =====
document.querySelector("#panel-signin form").addEventListener("submit", async (e) => {
  e.preventDefault();

  // inputs
  const login = e.target.querySelector("input[name='login']").value.trim();
  const password = e.target.querySelector("input[name='password']").value;

  // captcha
  const token = grecaptcha.getResponse(window.widgetSignin);
  if (!token) {
    alert("Please complete the reCAPTCHA.");
    return;
  }

  try {
    const body = {
      username: login,                // backend expects "username"
      password,
      g_recaptcha_response: token,    // required by your LoginJSON
    };

    const res = await fetch("/auth/token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const err = await readJsonSafe(res);
      console.error("Login failed:", res.status, err);
      throw new Error(err.detail || `Login failed (${res.status})`);
    }

    // success
    grecaptcha.reset(window.widgetSignin);
    const data = await res.json();
    console.log("Signed in:", data);
    window.location.href = "/";
  } catch (err) {
    console.error(err);
    grecaptcha.reset(window.widgetSignin);
  }
});

// ===== Sign Up =====
document.querySelector("#panel-signup form").addEventListener("submit", async (e) => {
  e.preventDefault();

  // inputs
  const login = e.target.querySelector("#login-signup").value.trim();
  const password = e.target.querySelector("#password2").value;
  const confirm = e.target.querySelector("#confirm").value;

  if (password !== confirm) {
    alert("Passwords do not match.");
    return;
  }

  // captcha
  const token = grecaptcha.getResponse(window.widgetSignup);
  if (!token) {
    alert("Please complete the reCAPTCHA.");
    return;
  }

  try {
    const body = {
      login,                          // backend expects "login"
      password,
      g_recaptcha_response: token,    // required by your RegisterJSON
    };

    const res = await fetch("/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const err = await readJsonSafe(res);
      console.error("Register failed:", res.status, err);
      throw new Error(err.detail || `Registration failed (${res.status})`);
    }

    grecaptcha.reset(window.widgetSignup);
    const data = await res.json();
    console.log("Signed up:", data);
    window.location.href = "/";
  } catch (err) {
    console.error(err);
    grecaptcha.reset(window.widgetSignup);
  }
});
