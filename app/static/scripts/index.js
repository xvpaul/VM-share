import { setupAuth } from './auth.js';
import { setupMenu } from './menu.js';
import { setupVM } from './vm.js';

const { updateAuthUI } = setupAuth();
setupMenu();
setupVM();
updateAuthUI();