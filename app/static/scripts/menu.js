export function setupMenu() {
  const menuBtn   = document.getElementById('menu-button');
  const menuPanel = document.getElementById('menu-panel');

  menuBtn.addEventListener('click', e => {
    e.stopPropagation();
    menuPanel.classList.toggle('hidden');
  });
}

