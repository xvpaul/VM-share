document.addEventListener("DOMContentLoaded", () => {
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
  const tinyBtn = document.getElementById("tinycore-btn");

  // --- NEW: initialize UI from cookie or localStorage ---
  initAuthUI();

  async function initAuthUI() {
    try {
      // Try cookie-based session first
      const r = await fetch("/me", { credentials: "include" });
      if (r.ok) {
        authBtn.classList.add("hidden");
        logoutBtn.classList.remove("hidden");
        return;
      }
    } catch (_) {}
    // Fallback: header token
    const token = localStorage.getItem("access_token");
    if (token) {
      authBtn.classList.add("hidden");
      logoutBtn.classList.remove("hidden");
    } else {
      logoutBtn.classList.add("hidden");
      authBtn.classList.remove("hidden");
    }
  }

  // Toggle modal
  authBtn.addEventListener("click", () => authModal.classList.remove("hidden"));
  closeAuth.addEventListener("click", () => authModal.classList.add("hidden"));

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

  // Auth
  async function registerOrLogin(url, login, password) {
    try {
      const payload = url === "/token" ? { username: login, password } : { login, password };
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        credentials: "include", // <-- ensure cookie is stored
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Authentication failed");

      // keep supporting header-based flows too (optional)
      if (data.access_token) localStorage.setItem("access_token", data.access_token);

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

  loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const login = loginForm.querySelector("input[placeholder='Email']").value;
    const password = loginForm.querySelector("input[placeholder='Password']").value;
    await registerOrLogin("/token", login, password);
  });

  signupForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const login = signupForm.querySelector("input[placeholder='Email']").value;
    const password = signupForm.querySelector("input[placeholder='Password']").value;
    await registerOrLogin("/register", login, password);
  });

  // Logout clears cookie on server + localStorage
  logoutBtn.addEventListener("click", async () => {
    try {
      await fetch("/auth/logout", { method: "POST", credentials: "include" });
    } catch (_) {}
    localStorage.removeItem("access_token");
    logoutBtn.classList.add("hidden");
    authBtn.classList.remove("hidden");
  });

  // VM launch — works with either cookie or header token
  async function runVM(os_type) {
    try {
      const token = localStorage.getItem("access_token");
      const headers = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const res = await fetch("api/run-script", {
        method: "POST",
        headers,
        credentials: "include", // <-- send cookie too if present
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
  tinyBtn.addEventListener("click", () => runVM("tiny"));
});
