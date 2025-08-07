// Open and close auth modal
document.getElementById("auth-btn")?.addEventListener("click", () => {
  document.getElementById("auth-modal").classList.remove("hidden");
});
document.getElementById("close-auth")?.addEventListener("click", () => {
  document.getElementById("auth-modal").classList.add("hidden");
});

// Tab switching logic
const tabLogin = document.getElementById("tab-login");
const tabSignup = document.getElementById("tab-signup");
const loginForm = document.getElementById("login-form");
const signupForm = document.getElementById("signup-form");

tabLogin?.addEventListener("click", () => {
  loginForm.classList.remove("hidden");
  signupForm.classList.add("hidden");

  tabLogin.classList.add("text-white", "border-b-2", "border-white");
  tabLogin.classList.remove("text-white/60");

  tabSignup.classList.remove("border-b-2", "border-white", "text-white");
  tabSignup.classList.add("text-white/60");
});

tabSignup?.addEventListener("click", () => {
  signupForm.classList.remove("hidden");
  loginForm.classList.add("hidden");

  tabSignup.classList.add("text-white", "border-b-2", "border-white");
  tabSignup.classList.remove("text-white/60");

  tabLogin.classList.remove("border-b-2", "border-white", "text-white");
  tabLogin.classList.add("text-white/60");
});


const alpineBtn = document.getElementById("alpine-btn");
const debianBtn = document.getElementById("debian-btn");

async function runVM(os_type) {
  try {
    const token = localStorage.getItem("access_token");
    if (!token) {
      alert("You must be logged in to launch a VM.");
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

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "VM launch failed");
    }

    const data = await res.json();
    if (data.redirect) {
      window.location.href = data.redirect;
    } else {
      alert("VM started but no redirect URL received.");
    }

  } catch (err) {
    console.error("Error launching VM:", err);
    alert("Error launching VM: " + err.message);
  }
}

alpineBtn.addEventListener("click", () => runVM("alpine"));
debianBtn.addEventListener("click", () => runVM("bodhi"));
