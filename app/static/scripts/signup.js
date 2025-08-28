// ===== Tabs (unchanged) =====
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

// ===== Sign In =====
document.querySelector("#panel-signin form").addEventListener("submit", async (e) => {
  e.preventDefault();

  // Get reCAPTCHA token
  const token = grecaptcha.getResponse(window.widgetSignin);
  if (!token) {
    alert("Please complete the reCAPTCHA.");
    return;
  }

  const login = e.target.querySelector("input[name='login']").value;
  const password = e.target.querySelector("input[name='password']").value;

  try {
    const res = await fetch("/auth/token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({
        username: login,        // your backend expects "username"
        password,
        g_recaptcha_response: token
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Login failed");
    // Reset widget for next attempt
    grecaptcha.reset(window.widgetSignin);
    window.location.href = "/";
  } catch (err) {
    console.error(err);
    grecaptcha.reset(window.widgetSignin);
  }
});

// ===== Sign Up =====
document.querySelector("#panel-signup form").addEventListener("submit", async (e) => {
  e.preventDefault();

  // Get reCAPTCHA token
  const token = grecaptcha.getResponse(window.widgetSignup);
  if (!token) {
    alert("Please complete the reCAPTCHA.");
    return;
  }

  const login = e.target.querySelector("input[name='login']").value;
  const password = e.target.querySelector("input[name='password']").value;

  try {
    const res = await fetch("/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({
        login,
        password,
        g_recaptcha_response: token
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Registration failed");
    grecaptcha.reset(window.widgetSignup);
    window.location.href = "/";
  } catch (err) {
    console.error(err);
    grecaptcha.reset(window.widgetSignup);
  }
});
