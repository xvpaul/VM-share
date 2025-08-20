// ===== Tabs =====
const tabSignin   = document.getElementById('tab-signin');
const tabSignup   = document.getElementById('tab-signup');
const panelSignin = document.getElementById('panel-signin');
const panelSignup = document.getElementById('panel-signup');

function activate(tab) {
  const isSignIn = tab === 'signin';
  tabSignin.setAttribute('aria-selected', String(isSignIn));
  tabSignup.setAttribute('aria-selected', String(!isSignIn));

  if (isSignIn) {
    tabSignin.dataset.active = "true";
    delete tabSignup.dataset.active;
  } else {
    tabSignup.dataset.active = "true";
    delete tabSignin.dataset.active;
  }
  panelSignin.classList.toggle('hidden', !isSignIn);
  panelSignup.classList.toggle('hidden', isSignIn);
}

tabSignin.addEventListener('click', () => activate('signin'));
tabSignup.addEventListener('click', () => activate('signup'));

// ===== Sign In (minimal) =====
document.querySelector("#panel-signin form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const login = e.target.querySelector("input[name='login']").value;
  const password = e.target.querySelector("input[name='password']").value;

  try {
    // If your /token expects JSON:
    const res = await fetch("/token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ username: login, password }), // FastAPI token expects 'username'
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Login failed");
    console.log("Signed in:", data);
    window.location.href = "/";
  } catch (err) {
    console.error(err);
  }
});


// ===== Sign Up =====
document
  .querySelector("#panel-signup form")
  .addEventListener("submit", async (e) => {
    e.preventDefault();
    const login = e.target.querySelector("input[name='login']").value;
    const password = e.target.querySelector("input[name='password']").value;
    alert(login, password)
    try {
      const res = await fetch("/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ login, password }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Registration failed");
      console.log("Signed up:", data);
      window.location.href = "/";
    } catch (err) {
      console.error(err);
    }
  });

