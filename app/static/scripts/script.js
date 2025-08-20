// =====================
// Auth Modal Handling
// =====================
document.addEventListener("DOMContentLoaded", () => {
const track = document.getElementById("os-track");
const prevBtn = document.getElementById("os-prev");
const nextBtn = document.getElementById("os-next");

let perView = getSlidesPerView();
let originalSlides = Array.from(track.children);
let total = originalSlides.length;
let current = total; // start in middle after clones
let isTransitioning = false;

// Clone slides
function setupClones() {
  const head = originalSlides.slice(-perView).map(el => el.cloneNode(true));
  const tail = originalSlides.slice(0, perView).map(el => el.cloneNode(true));
  head.forEach(clone => track.insertBefore(clone, track.firstChild));
  tail.forEach(clone => track.appendChild(clone));
  originalSlides = Array.from(track.children).slice(perView, perView + total);
}

// Get how many slides are visible
function getSlidesPerView() {
  const w = window.innerWidth;
  if (w >= 1024) return 3;
  if (w >= 640) return 2;
  return 1;
}

// Animate to index
function goTo(index) {
  const slide = track.children[index];
  if (!slide || isTransitioning) return;
  isTransitioning = true;
  track.style.transition = "transform 0.5s ease";
  track.style.transform = `translateX(-${slide.offsetLeft}px)`;
}

// Instant jump
function jumpTo(index) {
  const slide = track.children[index];
  if (!slide) return;
  track.style.transition = "none";
  track.style.transform = `translateX(-${slide.offsetLeft}px)`;
}

// Loop around if on clone
function checkLoop() {
  const realStart = perView;
  const realEnd = track.children.length - perView;
  if (current >= realEnd) {
    current = realStart;
    jumpTo(current);
  } else if (current < realStart) {
    current = realEnd - 1;
    jumpTo(current);
  }
}

// Navigation
function next() {
  if (isTransitioning) return;
  current++;
  goTo(current);
}
function prev() {
  if (isTransitioning) return;
  current--;
  goTo(current);
}

nextBtn.addEventListener("click", next);
prevBtn.addEventListener("click", prev);

// Reset on resize
window.addEventListener("resize", () => {
  perView = getSlidesPerView();
  setTimeout(() => jumpTo(current), 10);
});

// Transition end = unlock & check loop
track.addEventListener("transitionend", (e) => {
  if (e.propertyName === "transform") {
    isTransitioning = false;
    checkLoop();
  }
});

// Setup
setupClones();
setTimeout(() => jumpTo(current), 0);


  const authBtn   = document.getElementById("auth-btn");
  const logoutBtn = document.getElementById("logout-btn");
  const authModal = document.getElementById("auth-modal");
  const closeAuth = document.getElementById("close-auth");

  const tabLogin  = document.getElementById("tab-login");
  const tabSignup = document.getElementById("tab-signup");
  const loginForm = document.getElementById("login-form");
  const signupForm= document.getElementById("signup-form");
  const authMsg   = document.getElementById("auth-msg");

  const alpineBtn = document.getElementById("alpine-btn");
  const tinyBtn   = document.getElementById("tinycore-btn");

  // --- INIT: determine UI from cookie session ---
  initAuthUI();

  async function initAuthUI() {
    try {
      const r = await fetch("/me", { credentials: "include" });
      if (r.ok) {
        authBtn.classList.add("hidden");
        logoutBtn.classList.remove("hidden");
        return;
      }
    } catch (_) {}
    // not authenticated
    logoutBtn.classList.add("hidden");
    authBtn.classList.remove("hidden");
  }

  // Toggle modal
  authBtn.addEventListener("click", () => authModal.classList.remove("hidden"));
  closeAuth.addEventListener("click", () => authModal.classList.add("hidden"));

  // Switch tabs
  tabLogin.addEventListener("click", () => {
    tabLogin.classList.add("border-b-2","border-white");
    tabSignup.classList.remove("border-b-2","border-white");
    loginForm.classList.remove("hidden");
    signupForm.classList.add("hidden");
  });
  tabSignup.addEventListener("click", () => {
    tabSignup.classList.add("border-b-2","border-white");
    tabLogin.classList.remove("border-b-2","border-white");
    signupForm.classList.remove("hidden");
    loginForm.classList.add("hidden");
  });

  // =====================
  // Auth Functions (cookie-only)
  // =====================
  async function registerOrLogin(url, login, password) {
    try {
      const payload = url === "/token" ? { username: login, password } : { login, password };
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",            // <— send/receive cookie
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Authentication failed");

      authMsg.textContent = "";
      authModal.classList.add("hidden");
      authBtn.classList.add("hidden");
      logoutBtn.classList.remove("hidden");
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

  // Logout (server clears cookie)
  logoutBtn.addEventListener("click", async () => {
    try { await fetch("/logout", { method: "POST", credentials: "include" }); } catch (_){}
    logoutBtn.classList.add("hidden");
    authBtn.classList.remove("hidden");
  });

  // =====================
  // VM Launch (cookie-only)
  // =====================
  async function runVM(os_type) {
    try {
      const res = await fetch("api/run-script", {
        method: "POST",
        headers: { "Content-Type": "application/json" }, // no Authorization header
        credentials: "include",                          // <— rely on cookie
        body: JSON.stringify({ os_type }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "VM launch failed");
      if (data.redirect) window.location.href = data.redirect;
      else alert("VM started but no redirect URL was provided.");
    } catch (err) {
      console.error("VM launch error:", err);
      alert(err.message);
    }
  }

  alpineBtn.addEventListener("click", () => runVM("alpine"));
  tinyBtn.addEventListener("click", () => runVM("tiny"));
});
