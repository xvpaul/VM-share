document.addEventListener("DOMContentLoaded", () => {
  // =====================
  // Carousel
  // =====================
  const track  = document.getElementById("os-track");
  const prevBtn = document.getElementById("os-prev");
  const nextBtn = document.getElementById("os-next");

  let perView = getSlidesPerView();
  let originalSlides = Array.from(track.children);
  let total = originalSlides.length;
  let current = perView;             // start at first *real* slide
  let isTransitioning = false;

  function getSlidesPerView() {
    const w = window.innerWidth;
    if (w >= 1024) return 3;
    if (w >= 640)  return 2;
    return 1;
  }

  // Clone node but remove any duplicate IDs inside
  function cloneWithoutIds(el) {
    const c = el.cloneNode(true);
    if (c.id) c.removeAttribute("id");
    c.querySelectorAll("[id]").forEach(n => n.removeAttribute("id"));
    return c;
  }

  function setupClones() {
    // remove existing clones if any (keep the middle block of "real" slides)
    if (track.children.length > total) {
      const real = Array.from(track.children).slice(perView, perView + total);
      track.innerHTML = "";
      real.forEach(n => track.appendChild(n));
    }

    const head = originalSlides.slice(-perView).map(cloneWithoutIds);
    const tail = originalSlides.slice(0,  perView).map(cloneWithoutIds);

    head.forEach(clone => track.insertBefore(clone, track.firstChild));
    tail.forEach(clone => track.appendChild(clone));

    // refresh "real" slice
    originalSlides = Array.from(track.children).slice(perView, perView + total);
  }

  function goTo(index) {
    const slide = track.children[index];
    if (!slide || isTransitioning) return;
    isTransitioning = true;
    track.style.transition = "transform 0.5s ease";
    track.style.transform  = `translateX(-${slide.offsetLeft}px)`;
  }

  function jumpTo(index) {
    const slide = track.children[index];
    if (!slide) return;
    track.style.transition = "none";
    track.style.transform  = `translateX(-${slide.offsetLeft}px)`;
  }

  function checkLoop() {
    const realStart = perView;
    const realEnd   = track.children.length - perView;
    if (current >= realEnd) {
      current = realStart;
      jumpTo(current);
    } else if (current < realStart) {
      current = realEnd - 1;
      jumpTo(current);
    }
  }

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

  // Transition end/cancel → unlock and normalize
  function onTransitionDone(e) {
    if (e.propertyName !== "transform") return;
    isTransitioning = false;
    checkLoop();
    // sanity align to the exact target position
    Promise.resolve().then(() => jumpTo(current));
  }
  track.addEventListener("transitionend", onTransitionDone);
  track.addEventListener("transitioncancel", onTransitionDone);

  // Init
  setupClones();
  // ensure each slide is fixed width so track doesn't cover arrows weirdly
  track.querySelectorAll(".os-slide").forEach(s => s.style.flex = "0 0 auto");
  jumpTo(current);

  // Handle responsive changes by rebuilding clones when perView changes
  window.addEventListener("resize", () => {
    const newPer = getSlidesPerView();
    if (newPer === perView) {
      // still ensure offset aligns after relayout
      setTimeout(() => jumpTo(current), 0);
      return;
    }
    // compute logical index within originals before rebuild
    const realStart = perView;
    const visibleIndex = current - realStart;       // 0..total-1
    perView = newPer;
    setupClones();
    current = perView + Math.max(0, Math.min(total - 1, visibleIndex));
    jumpTo(current);
  });

  // =====================
  // Auth & VM (unchanged auth, but VM uses delegation)
  // =====================
  // ===== Auth header (no modal, separate auth page) =====
const authBtn   = document.getElementById("auth-btn");
const logoutBtn = document.getElementById("logout-btn"); // legacy; we'll hide it

initHeaderAuth();

async function initHeaderAuth() {
  if (!authBtn) return; // header not present

  const authed = await isAuthenticated();

  if (!authed) {
    // Show simple redirect button
    authBtn.classList.remove("hidden");
    authBtn.textContent = "Log in / Sign Up";
    authBtn.onclick = () => { window.location.href = "/signup"; };
    logoutBtn?.classList.add("hidden");
    // remove any stale menu from previous state
    removeUserMenu();
  } else {
    // Hide old buttons and render burger menu
    authBtn.classList.add("hidden");
    logoutBtn?.classList.add("hidden");
    renderUserMenu(authBtn.parentElement);
  }
}

async function isAuthenticated() {
  try {
    const r = await fetch("/me", { credentials: "include" });
    return r.ok;
  } catch {
    return false;
  }
}

function removeUserMenu() {
  const existing = document.getElementById("user-menu-wrap");
  if (existing) existing.remove();
}

function renderUserMenu(container) {
  if (!container) return;
  removeUserMenu();

  const wrap = document.createElement("div");
  wrap.id = "user-menu-wrap";
  wrap.className = "relative ml-4";

  wrap.innerHTML = `
  <style>
    .menu {
      position: relative;
      cursor: pointer;
      width: 30px;
      height: 22px;
    }
    .menu .line {
      position: absolute;
      left: 0;
      width: 100%;
      height: 3px;
      background: #ffffff;
      transform-origin: center;
      transition: transform 0.2s ease, opacity 0.2s ease, visibility 0.2s ease;
    }
    .menu .line:nth-child(1) { top: 0; }
    .menu .line:nth-child(2) { top: 50%; transform: translateY(-50%); }
    .menu .line:nth-child(3) { bottom: 0; }
    .menu.open .line:nth-child(2) {
      transform: translateX(50%);
      opacity: 0;
      visibility: hidden;
    }
    .menu.open .line:nth-child(1) {
      transform: translateY(9px) rotate(45deg);
    }
    .menu.open .line:nth-child(3) {
      transform: translateY(-9px) rotate(-45deg);
    }
  </style>

  <button id="user-menu-trigger"
    class="menu inline-flex items-center justify-center w-10 h-10 rounded-md focus:outline-none"
    aria-haspopup="true" aria-expanded="false" aria-controls="user-menu">
    <div class="line"></div>
    <div class="line"></div>
    <div class="line"></div>
  </button>

  <div id="user-menu"
    class="absolute right-0 mt-2 w-44 rounded-md bg-neutral-900 ring-1 ring-white/10 shadow-lg hidden"
    role="menu" aria-labelledby="user-menu-trigger">
    <a href="/profile" class="block px-4 py-2 hover:bg-white/10" role="menuitem">Profile</a>
    <button id="logout-menu" class="w-full text-left block px-4 py-2 hover:bg-white/10" role="menuitem">
      Log out
    </button>
  </div>
`;


  container.appendChild(wrap);

  const trigger = wrap.querySelector("#user-menu-trigger");
  const menu    = wrap.querySelector("#user-menu");
  const logout  = wrap.querySelector("#logout-menu");

  // Toggle menu
  trigger.addEventListener("click", () => {
    menu.classList.toggle("hidden");
    trigger.classList.toggle("open"); // animate burger ↔ X
    trigger.setAttribute("aria-expanded", menu.classList.contains("hidden") ? "false" : "true");
  });

  // Close on outside click / ESC
  document.addEventListener("click", (e) => {
    if (!wrap.contains(e.target)) {
      menu.classList.add("hidden");
      trigger.classList.remove("open");
      trigger.setAttribute("aria-expanded", "false");
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      menu.classList.add("hidden");
      trigger.classList.remove("open");
      trigger.setAttribute("aria-expanded", "false");
    }
  });

  // Logout action
  logout.addEventListener("click", async () => {
    try { await fetch("/logout", { method: "POST", credentials: "include" }); }
    catch {}
    initHeaderAuth();
  });
}

  // =====================
  // VM launch — EVENT DELEGATION (works for clones)
  // =====================

  async function runVM(os_type) {
    try {
      const res = await fetch("api/run-script", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
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

  // 1) Clicks on any .vm-btn with data-os
  track.addEventListener("click", (e) => {
    const btn = e.target.closest(".vm-btn[data-os]");
    if (!btn) return;
    const os = btn.getAttribute("data-os");
    if (os) runVM(os);
  });

  // 2) Handle custom image: enable its button when a file is picked.
  //    Use delegation so it also works on clones (the original is enough, but this is safe).
  document.addEventListener("change", (e) => {
    const input = e.target.closest("input[type='file'][data-custom]");
    if (!input) return;
    const panel = input.closest("article");
    const launchBtn = panel?.querySelector(".vm-btn[data-os='custom']");
    if (launchBtn) launchBtn.disabled = !input.files?.length;
  });

  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".vm-btn[data-os='custom']");
    if (!btn) return;
    // You can grab the nearest file input in the same slide/panel
    const panel = btn.closest("article");
    const fileInput = panel?.querySelector("input[type='file'][data-custom]");
    if (!fileInput?.files?.length) return;
    // If you need to upload the file, add your upload flow here.
    runVM("custom");
  });
});
