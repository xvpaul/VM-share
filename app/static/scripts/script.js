// =====================
// Auth Modal Handling
// =====================
const authBtn = document.getElementById("auth-btn");
const logoutBtn = document.getElementById("logout-btn");
const authModal = document.getElementById("auth-modal");
const closeAuth = document.getElementById("close-auth");

const tabLogin = document.getElementById("tab-login");
const tabSignup = document.getElementById("tab-signup");
const loginForm = document.getElementById("login-form");
const signupForm = document.getElementById("signup-form");
const authMsg = document.getElementById("auth-msg");

const alpineBtn = document.getElementById("alpine-btn");
const debianBtn = document.getElementById("debian-btn");

// Toggle modal
authBtn.addEventListener("click", () => {
  authModal.classList.remove("hidden");
});
closeAuth.addEventListener("click", () => {
  authModal.classList.add("hidden");
});

// Switch tabs
tabLogin.addEventListener("click", () => {
  tabLogin.classList.add("border-b-2", "border-white");
  tabSignup.classList.remove("border-b-2", "border-white");
  loginForm.classList.remove("hidden");
  signupForm.classList.add("hidden");
});
tabSignup.addEventListener("click", () => {
  tabSignup.classList.add("border-b-2", "border-white");
  tabLogin.classList.remove("border-b-2", "border-white");
  signupForm.classList.remove("hidden");
  loginForm.classList.add("hidden");
});

// =====================
// Auth Functions
// =====================
async function registerOrLogin(url, login, password) {
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ login, password })
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Authentication failed");

    // Save token
    localStorage.setItem("access_token", data.access_token);
    authMsg.textContent = "";
    authModal.classList.add("hidden");
    authBtn.classList.add("hidden");
    logoutBtn.classList.remove("hidden");
    console.log(`Logged in as ${login}`);
  } catch (err) {
    authMsg.textContent = err.message;
    console.error("Auth error:", err);
  }
}

// Login form submit
loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const login = loginForm.querySelector("input[placeholder='Email']").value;
  const password = loginForm.querySelector("input[placeholder='Password']").value;
  await registerOrLogin("/token", login, password);
});

// Signup form submit
signupForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const login = signupForm.querySelector("input[placeholder='Email']").value;
  const password = signupForm.querySelector("input[placeholder='Password']").value;
  await registerOrLogin("/register", login, password);
});

// Logout
logoutBtn.addEventListener("click", () => {
  localStorage.removeItem("access_token");
  logoutBtn.classList.add("hidden");
  authBtn.classList.remove("hidden");
});

// =====================
// VM Launch
// =====================
async function runVM(os_type) {
  try {
    const token = localStorage.getItem("access_token");
    if (!token) {
      alert("Please log in first.");
      return;
    }

    const res = await fetch("/run-script", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`,
      },
      body: JSON.stringify({ os_type }),
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "VM launch failed");

    if (data.redirect) {
      window.location.href = data.redirect;
    } else {
      alert("VM started but no redirect URL was provided.");
    }
  } catch (err) {
    console.error("VM launch error:", err);
    alert(err.message);
  }
}

alpineBtn.addEventListener("click", () => runVM("alpine"));
debianBtn.addEventListener("click", () => runVM("bodhi"));
