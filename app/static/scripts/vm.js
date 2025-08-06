export function setupVM() {
  const wrap         = document.getElementById('toggle-wrap');
  const revealBtn    = document.getElementById('reveal-btn');
  const choiceCtr    = document.getElementById('vm-choice');
  const alpineBtn    = document.getElementById('alpine-btn');
  const ubuntuBtn    = document.getElementById('ubuntu-btn');

  revealBtn.addEventListener('mouseenter', () => {
    revealBtn.classList.add('hidden');
    choiceCtr.classList.remove('hidden');
  });

  wrap.addEventListener('mouseleave', () => {
    choiceCtr.classList.add('hidden');
    revealBtn.classList.remove('hidden');
  });

  alpineBtn.addEventListener('click', async () => {
    const token = localStorage.getItem('token');
    if (!token) {
      alert('You must log in first.');
      return;
    }

    try {
      const resp = await fetch('/api/run-script', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({})
      });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      if (data.redirect) {
        setTimeout(() => window.location.href = data.redirect, 300);
      }
    } catch (err) {
      console.error(err);
      alert('Error running script: ' + err.message);
    }
  });

  ubuntuBtn.addEventListener('click', () => {
    alert('Ubuntu VM is not implemented yet.');
  });
}
