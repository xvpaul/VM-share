// index.js
import { setupAuth } from './auth.js';
import { setupMenu } from './menu.js';
import { setupVM } from './vm.js';

document.addEventListener('DOMContentLoaded', () => {
  const { updateAuthUI } = setupAuth();
  setupMenu();
  setupVM();
  updateAuthUI();
});

