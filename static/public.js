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

  function progressText(done, total) {
    if (done === 0)     return 'Not yet started';
    if (done === total) return '✓ Complete';
    return `${done} / ${total} races done`;
  }

  function buildCupCard(cup) {
    const cls = cupClass(cup.label);
    const teams = cup.teams.map(t => `<li>${t}</li>`).join('');
    const prog = progressText(cup.races_done, 4);
    return `
      <div class="cup-card ${cls}">
        <div class="cup-label">${cup.label}</div>
        <div class="cup-progress">${prog}</div>
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

  function renderCups(cups, roundNum, gridId, card1Id, card2Id) {
    const grid = document.getElementById(gridId || 'cup-grid');
    if (!grid || !cups || cups.length === 0) return;

    const c1 = document.getElementById(card1Id || 'cup-card-1');
    const c2 = document.getElementById(card2Id || 'cup-card-2');
    if (c1) c1.outerHTML = buildCupCard(cups[0]).replace('<div ', `<div id="${card1Id || 'cup-card-1'}" `);
    if (c2) c2.outerHTML = buildCupCard(cups[1]).replace('<div ', `<div id="${card2Id || 'cup-card-2'}" `);

    const rl = document.getElementById(roundNum === 'admin-round-label' ? 'admin-round-label' : 'round-label');
    if (rl) rl.textContent = roundNum;
  }

  function renderProjection(proj, sectionId, cup1Id, cup2Id, labelId) {
    const section = document.getElementById(sectionId || 'next-up-section');
    if (!section) return;

    if (!proj) {
      section.hidden = true;
      return;
    }
    section.hidden = false;

    const nlabel = document.getElementById(labelId || 'next-round-label');
    if (nlabel) nlabel.textContent = proj.round_number;

    const nc1 = document.getElementById(cup1Id || 'next-cup-1');
    const nc2 = document.getElementById(cup2Id || 'next-cup-2');
    if (nc1) nc1.outerHTML = buildCupCard(proj.cups[0]).replace('<div ', `<div id="${cup1Id || 'next-cup-1'}" `);
    if (nc2) nc2.outerHTML = buildCupCard(proj.cups[1]).replace('<div ', `<div id="${cup2Id || 'next-cup-2'}" `);
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

    renderProjection(data.next_round_projection, 'next-up-section',
                     'next-cup-1', 'next-cup-2', 'next-round-label');
  }

  refresh();
  setInterval(refresh, REFRESH_MS);

  // Expose for admin.js reuse
  window._mkRender = { renderBanner, renderLeaderboard, buildCupCard, renderProjection, progressText, cupClass };
})();
