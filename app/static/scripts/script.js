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
