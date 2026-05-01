(function () {
  'use strict';

  const REFRESH_MS = 15000;
  const PODIUM = ['podium-gold', 'podium-silver', 'podium-bronze'];

  // ── Helpers ──────────────────────────────────────────────────────────────

  function cupClass(label) {
    if (label === 'Elite Cup')    return 'elite';
    if (label === 'Standard Cup') return 'standard';
    return 'random';
  }

  function buildCupCard(cup) {
    const cls = cupClass(cup.label);
    const status = cup.completed ? '<div class="cup-progress">✓ Complete</div>' : '';
    const teams = (cup.teams || []).map(t => `<li>${t}</li>`).join('');
    return `
      <div class="cup-card ${cls}">
        <div class="cup-label">${cup.label}</div>
        ${status}
        <ul>${teams}</ul>
      </div>`;
  }

  // ── Render functions ──────────────────────────────────────────────────────

  function renderBanner(data, bannerId) {
    const el = document.getElementById(bannerId || 'state-banner');
    if (!el) return;
    el.className = 'state-banner ' + data.state.replace('_', '-');
    if (data.state === 'not_started') {
      el.textContent = 'Tournament not started yet';
    } else if (data.state === 'complete') {
      el.textContent = '🏁 Tournament Complete!';
    } else {
      el.textContent = `Round ${data.current_round} of ${data.total_rounds}`;
    }
  }

  function renderLeaderboard(entries, tbodyId) {
    const tbody = document.getElementById(tbodyId || 'lb-body');
    if (!tbody) return;
    if (!entries || entries.length === 0) {
      tbody.innerHTML = '<tr><td colspan="3" class="muted">No results yet</td></tr>';
      return;
    }
    tbody.innerHTML = entries.map((e, i) => {
      const medal = i < 3 ? ['🥇','🥈','🥉'][i] + ' ' : '';
      const cls = i < 3 ? PODIUM[i] : '';
      return `<tr class="${cls}">
        <td class="rank-cell">${medal}${e.rank}</td>
        <td>${e.team}</td>
        <td class="score-cell">${e.score}</td>
      </tr>`;
    }).join('');
  }

  // ── Public page render ────────────────────────────────────────────────────

  async function refresh() {
    let data;
    try {
      const resp = await fetch('/tournament/status');
      if (!resp.ok) return;
      data = await resp.json();
    } catch (_) { return; }

    renderBanner(data, 'state-banner');
    renderLeaderboard(data.leaderboard, 'lb-body');

    const rlEl = document.getElementById('round-label');
    if (rlEl) rlEl.textContent = data.current_round || '—';

    if (data.active_cups && data.active_cups.length >= 2) {
      const c1 = document.getElementById('cup-card-1');
      const c2 = document.getElementById('cup-card-2');
      if (c1) c1.outerHTML = buildCupCard(data.active_cups[0]).replace('<div ', '<div id="cup-card-1" ');
      if (c2) c2.outerHTML = buildCupCard(data.active_cups[1]).replace('<div ', '<div id="cup-card-2" ');
    }
  }

  refresh();
  setInterval(refresh, REFRESH_MS);

  // Expose for admin.js reuse
  window._mkRender = { renderBanner, renderLeaderboard, buildCupCard, cupClass };
})();
