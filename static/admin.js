'use strict';

// ── Shared state ─────────────────────────────────────────────────────────────

let _statusData = null;
let _statusInterval = null;

// ── Tab system ───────────────────────────────────────────────────────────────

document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => activateTab(btn.dataset.tab));
});

function activateTab(name) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('.tab-panel').forEach(p => { p.hidden = p.id !== 'tab-' + name; });

  clearInterval(_statusInterval);
  if (name === 'status') {
    refreshStatus();
    _statusInterval = setInterval(refreshStatus, 15000);
  } else if (name === 'tourney') {
    loadTourneyTab();
  } else if (name === 'results') {
    loadResultsTab();
  } else if (name === 'teams') {
    loadTeamsTab();
  }
}

// Kick off the status tab on load
refreshStatus();
_statusInterval = setInterval(refreshStatus, 15000);

// ── Helpers ──────────────────────────────────────────────────────────────────

function cupClass(label) {
  if (label === 'Elite Cup')    return 'elite';
  if (label === 'Standard Cup') return 'standard';
  return 'random';
}

function buildCupCard(cup) {
  const cls = cupClass(cup.label);
  const done = typeof cup.races_done === 'number' ? cup.races_done : 0;
  const prog = done === 0 ? 'Not yet started' : done === 4 ? '✓ Complete' : `${done} / 4 races done`;
  const teams = (cup.teams || []).map(t => `<li>${t}</li>`).join('');
  return `<div class="cup-card ${cls}">
    <div class="cup-label">${cup.label}</div>
    <div class="cup-progress">${prog}</div>
    <ul>${teams}</ul>
  </div>`;
}

function showMsg(containerId, msg, type) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = `<div class="${type || 'info'}-msg">${msg}</div>`;
}

// ── Status tab ───────────────────────────────────────────────────────────────

async function refreshStatus() {
  let data;
  try {
    const r = await fetch('/tournament/status');
    if (!r.ok) return;
    data = await r.json();
  } catch (_) { return; }
  _statusData = data;

  // State banner
  const banner = document.getElementById('admin-state-banner');
  if (banner) {
    banner.className = 'state-banner ' + data.state.replace('_', '-');
    if (data.state === 'not_started')   banner.textContent = 'Tournament not started yet';
    else if (data.state === 'complete') banner.textContent = '🏁 Tournament Complete!';
    else banner.textContent = `Round ${data.current_round} of ${data.total_rounds}`;
  }

  // Leaderboard
  const tbody = document.getElementById('admin-lb-body');
  if (tbody) {
    const PODIUM = ['podium-gold','podium-silver','podium-bronze'];
    const medals = ['🥇','🥈','🥉'];
    tbody.innerHTML = (data.leaderboard || []).map((e, i) => {
      const medal = i < 3 ? medals[i] + ' ' : '';
      return `<tr class="${i < 3 ? PODIUM[i] : ''}">
        <td class="rank-cell">${medal}${e.rank}</td>
        <td>${e.team}</td>
        <td class="score-cell">${e.score}</td>
      </tr>`;
    }).join('') || '<tr><td colspan="3" class="muted">No results yet</td></tr>';
  }

  // Round label
  const rl = document.getElementById('admin-round-label');
  if (rl) rl.textContent = data.current_round || '—';

  // Cup cards
  if (data.active_cups && data.active_cups.length >= 2) {
    const c1 = document.getElementById('admin-cup-card-1');
    const c2 = document.getElementById('admin-cup-card-2');
    if (c1) c1.outerHTML = buildCupCard(data.active_cups[0]).replace('<div ', '<div id="admin-cup-card-1" ');
    if (c2) c2.outerHTML = buildCupCard(data.active_cups[1]).replace('<div ', '<div id="admin-cup-card-2" ');
  }

  // Projection
  const nextSec = document.getElementById('admin-next-up-section');
  if (nextSec) {
    const proj = data.next_round_projection;
    nextSec.hidden = !proj;
    if (proj) {
      const nl = document.getElementById('admin-next-round-label');
      if (nl) nl.textContent = proj.round_number;
      const nc1 = document.getElementById('admin-next-cup-1');
      const nc2 = document.getElementById('admin-next-cup-2');
      if (nc1) nc1.outerHTML = buildCupCard(proj.cups[0]).replace('<div ', '<div id="admin-next-cup-1" ');
      if (nc2) nc2.outerHTML = buildCupCard(proj.cups[1]).replace('<div ', '<div id="admin-next-cup-2" ');
    }
  }
}

// ── Results tab ───────────────────────────────────────────────────────────────

async function loadResultsTab() {
  const status = _statusData || await fetch('/tournament/status').then(r => r.json());
  _statusData = status;

  const roundSel = document.getElementById('round-select');
  if (!roundSel) return;
  roundSel.innerHTML = '';

  if (!status.current_round) {
    document.getElementById('results-form-area').innerHTML =
      '<p class="muted" style="padding:1rem">No tournament in progress.</p>';
    return;
  }

  for (let i = 1; i <= status.current_round; i++) {
    const opt = document.createElement('option');
    opt.value = i;
    opt.textContent = `Round ${i}`;
    roundSel.appendChild(opt);
  }
  roundSel.value = status.current_round;

  document.getElementById('load-results-btn').onclick = () => {
    const rn = parseInt(roundSel.value);
    const cn = parseInt(document.getElementById('cup-select').value);
    loadCupResultsForm(rn, cn);
  };

  loadCupResultsForm(status.current_round, 1);
}

async function loadCupResultsForm(rn, cn) {
  const area = document.getElementById('results-form-area');
  area.innerHTML = '<p class="muted" style="padding:1rem">Loading…</p>';

  // Fetch existing results from DB
  let existing = { races: [] };
  try {
    const r = await fetch(`/rounds/${rn}/cups/${cn}/results`);
    if (r.ok) existing = await r.json();
  } catch (_) {}

  // Determine which players belong to this cup
  let cupTeams = [];
  const status = _statusData;
  if (status && status.current_round === rn && status.active_cups) {
    const cupData = status.active_cups.find(c => c.cup_number === cn);
    if (cupData) cupTeams = cupData.teams;
  }

  // Fall back: derive from existing results if available
  let players = [];
  if (existing.races.length > 0 && existing.races[0].results) {
    const seen = {};
    existing.races[0].results.forEach(r => {
      if (!seen[r.player_name]) { seen[r.player_name] = r.player1 + ' & ' + r.player2; }
    });
    players = existing.races[0].results.map(r => r.player_name);
  } else if (cupTeams.length > 0) {
    players = cupTeams.flatMap(t => t.split(' & '));
  }

  const isCorrection = existing.races.length > 0;
  const btnLabel = isCorrection ? 'Correct Results' : 'Submit Results';
  const method = isCorrection ? 'PATCH' : 'POST';

  // Build 4 race fieldsets
  let racesHtml = '';
  for (let ri = 0; ri < 4; ri++) {
    const existingRace = existing.races[ri] || null;
    const placementMap = {};
    if (existingRace) {
      existingRace.results.forEach(r => { placementMap[r.player_name] = r.place; });
    }

    const rows = players.map((p, pi) => {
      const place = placementMap[p] || '';
      return `<tr>
        <td>${p}</td>
        <td><input type="number" min="1" max="12" value="${place}"
             data-race="${ri}" data-player="${p}" class="place-input" required></td>
      </tr>`;
    }).join('');

    racesHtml += `
      <fieldset class="race-fieldset">
        <legend>Race ${ri + 1}</legend>
        <table class="race-table">
          <thead><tr><th>Player</th><th>Place</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </fieldset>`;
  }

  area.innerHTML = `
    <div class="card" style="margin-top:0">
      <h2>Round ${rn} · Cup ${cn} Results</h2>
      <div id="results-msg"></div>
      ${racesHtml}
      <button class="btn" id="submit-results-btn">${btnLabel}</button>
    </div>`;

  document.getElementById('submit-results-btn').onclick = () =>
    submitCupResults(rn, cn, players, method);
}

async function submitCupResults(rn, cn, players, method) {
  const btn = document.getElementById('submit-results-btn');
  btn.disabled = true;
  btn.textContent = 'Saving…';

  // Build payload
  const races = [];
  for (let ri = 0; ri < 4; ri++) {
    const placements = players.map(p => {
      const inp = document.querySelector(`.place-input[data-race="${ri}"][data-player="${p}"]`);
      return { player_name: p, place: parseInt(inp ? inp.value : 0) };
    });
    races.push({ placements });
  }

  try {
    const r = await fetch(`/rounds/${rn}/cups/${cn}/results`, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ races }),
    });
    const data = await r.json();
    if (r.ok) {
      showMsg('results-msg', '✓ Results saved successfully.', 'success');
      btn.textContent = 'Correct Results';
      btn.disabled = false;
      refreshStatus();
    } else {
      showMsg('results-msg', `Error: ${data.detail || JSON.stringify(data)}`, 'error');
      btn.textContent = method === 'PATCH' ? 'Correct Results' : 'Submit Results';
      btn.disabled = false;
    }
  } catch (e) {
    showMsg('results-msg', `Network error: ${e.message}`, 'error');
    btn.disabled = false;
    btn.textContent = method === 'PATCH' ? 'Correct Results' : 'Submit Results';
  }
}

// ── Tournament Status tab ─────────────────────────────────────────────────────

async function loadTourneyTab() {
  const area = document.getElementById('tourney-tab-content');
  if (!area) return;
  area.innerHTML = '<p class="muted" style="padding:1rem">Loading…</p>';

  const [teamsResp, statusResp] = await Promise.all([
    fetch('/teams').then(r => r.json()),
    fetch('/tournament/status').then(r => r.json()),
  ]);
  _statusData = statusResp;

  if (statusResp.state === 'complete') {
    renderTourneyComplete(area, statusResp);
  } else if (statusResp.state === 'in_progress') {
    renderTourneyInProgress(area, statusResp);
  } else {
    renderTourneySetup(area, teamsResp.teams);
  }
}

function renderTourneyComplete(area, status) {
  const medals = ['🥇', '🥈', '🥉'];
  const podium = status.leaderboard.slice(0, 3).map((e, i) =>
    `<div class="podium-entry podium-${['gold','silver','bronze'][i]}">
      <span class="podium-medal">${medals[i]}</span>
      <span class="podium-name">${e.team}</span>
      <span class="podium-score">${e.score} pts</span>
    </div>`
  ).join('');

  const lbRows = status.leaderboard.map((e, i) =>
    `<tr class="${i < 3 ? ['podium-gold','podium-silver','podium-bronze'][i] : ''}">
      <td class="rank-cell">${i < 3 ? medals[i]+' ' : ''}${e.rank}</td>
      <td>${e.team}</td><td class="score-cell">${e.score}</td>
    </tr>`
  ).join('');

  area.innerHTML = `
    <div class="card">
      <div class="state-banner complete" style="margin:0 0 1.5rem">🏁 Tournament Complete!</div>
      <div class="podium-row">${podium}</div>
    </div>
    <div class="card">
      <h2>Final Standings</h2>
      <table class="lb-table">
        <thead><tr><th>#</th><th>Team</th><th>Score</th></tr></thead>
        <tbody>${lbRows}</tbody>
      </table>
    </div>
    <div class="card" style="text-align:center">
      <p class="muted" style="margin-bottom:1rem">Ready to run another tournament?</p>
      <button class="btn btn-primary" onclick="resetTournament()">Reset for New Tournament</button>
      <div id="reset-msg" style="margin-top:0.75rem"></div>
    </div>`;
}

function renderTourneyInProgress(area, status) {
  area.innerHTML = `
    <div class="card">
      <div class="state-banner in-progress" style="margin:0 0 1rem">
        Round ${status.current_round} of ${status.total_rounds} in progress
      </div>
      <div class="info-banner" style="margin-bottom:1rem">
        🔒 Tournament is in progress. Cup group assignment and start controls are locked.
      </div>
      <h2 style="margin-bottom:0.75rem">Current Cup Groups</h2>
      <div class="cup-grid">
        ${(status.active_cups || []).map(cup => buildCupCard(cup)).join('')}
      </div>
    </div>
    <div class="card" style="opacity:0.5">
      <h2>Start Tournament</h2>
      <p class="muted">Tournament is already in progress.</p>
      <button class="btn" disabled>Start Tournament</button>
    </div>`;
}

function renderTourneySetup(area, teams) {
  if (!teams || teams.length === 0) {
    area.innerHTML = `
      <div class="card">
        <div class="info-banner">No teams registered yet. Go to the Teams tab to add teams.</div>
      </div>`;
    return;
  }

  const teamsPerCup = 6;
  const groupA = teams.slice(0, teamsPerCup);
  const groupB = teams.slice(teamsPerCup);

  function chipHtml(t) {
    return `<div class="team-chip" draggable="true" data-id="${t.team_id}">${t.player1} &amp; ${t.player2}</div>`;
  }

  area.innerHTML = `
    <div class="card">
      <h2>Assign Cup Groups — Round 1</h2>
      <p class="muted" style="margin-bottom:1rem">
        Drag teams between Group A and Group B. Each group must have exactly ${teamsPerCup} teams.
      </p>
      <div class="group-assignment">
        <div class="drop-group" id="group-a">
          <div class="group-header">
            Group A
            <span class="group-count" id="count-a">${groupA.length}/${teamsPerCup}</span>
          </div>
          <div class="team-list" id="group-a-list">
            ${groupA.map(chipHtml).join('')}
          </div>
        </div>
        <div class="drop-group" id="group-b">
          <div class="group-header">
            Group B
            <span class="group-count" id="count-b">${groupB.length}/${teamsPerCup}</span>
          </div>
          <div class="team-list" id="group-b-list">
            ${groupB.map(chipHtml).join('')}
          </div>
        </div>
      </div>
    </div>
    <div class="card">
      <h2>Start Tournament</h2>
      <p class="muted" style="margin-bottom:1rem">
        Once groups are set (${teamsPerCup} teams each), lock them in and begin Round 1.
      </p>
      <div id="start-tourney-msg" style="margin-bottom:0.75rem"></div>
      <button class="btn btn-primary" id="start-tourney-btn" onclick="startTournament()"
              ${teams.length < teamsPerCup * 2 ? 'disabled' : ''}>
        Start Tournament
      </button>
      ${teams.length < teamsPerCup * 2
        ? `<p class="muted" style="margin-top:0.5rem;font-size:0.85rem">
             Need ${teamsPerCup * 2} teams — currently have ${teams.length}.
           </p>`
        : ''}
    </div>`;

  initDragDrop(teamsPerCup);
  validateGroupCounts(teamsPerCup);
}

function initDragDrop(teamsPerCup) {
  let draggedId = null;

  document.querySelectorAll('.team-chip').forEach(chip => {
    chip.addEventListener('dragstart', e => {
      draggedId = chip.dataset.id;
      chip.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
    });
    chip.addEventListener('dragend', () => {
      chip.classList.remove('dragging');
      draggedId = null;
    });
  });

  document.querySelectorAll('.team-list').forEach(zone => {
    zone.addEventListener('dragover', e => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      zone.classList.add('drag-over');
    });
    zone.addEventListener('dragleave', e => {
      if (!zone.contains(e.relatedTarget)) zone.classList.remove('drag-over');
    });
    zone.addEventListener('drop', e => {
      e.preventDefault();
      zone.classList.remove('drag-over');
      const chip = document.querySelector(`.team-chip[data-id="${draggedId}"]`);
      if (chip && chip.parentElement !== zone) {
        zone.appendChild(chip);
        validateGroupCounts(teamsPerCup);
      }
    });
  });
}

function validateGroupCounts(teamsPerCup) {
  const aCount = document.querySelectorAll('#group-a-list .team-chip').length;
  const bCount = document.querySelectorAll('#group-b-list .team-chip').length;
  const countA = document.getElementById('count-a');
  const countB = document.getElementById('count-b');
  const btn = document.getElementById('start-tourney-btn');
  if (countA) countA.textContent = `${aCount}/${teamsPerCup}`;
  if (countB) countB.textContent = `${bCount}/${teamsPerCup}`;
  if (countA) countA.className = 'group-count' + (aCount === teamsPerCup ? ' ok' : ' bad');
  if (countB) countB.className = 'group-count' + (bCount === teamsPerCup ? ' ok' : ' bad');
  if (btn) btn.disabled = !(aCount === teamsPerCup && bCount === teamsPerCup);
}

async function startTournament() {
  const btn = document.getElementById('start-tourney-btn');
  btn.disabled = true;
  btn.textContent = 'Starting…';

  const groupA = [...document.querySelectorAll('#group-a-list .team-chip')].map(c => parseInt(c.dataset.id));
  const groupB = [...document.querySelectorAll('#group-b-list .team-chip')].map(c => parseInt(c.dataset.id));

  try {
    const r = await fetch('/tournament/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ group_a: groupA, group_b: groupB }),
    });
    const data = await r.json();
    if (r.ok) {
      showMsg('start-tourney-msg', '✓ Tournament started! Round 1 is live.', 'success');
      setTimeout(() => loadTourneyTab(), 800);
    } else {
      showMsg('start-tourney-msg', `Error: ${data.detail || JSON.stringify(data)}`, 'error');
      btn.disabled = false;
      btn.textContent = 'Start Tournament';
    }
  } catch (e) {
    showMsg('start-tourney-msg', `Network error: ${e.message}`, 'error');
    btn.disabled = false;
    btn.textContent = 'Start Tournament';
  }
}

async function resetTournament() {
  try {
    const r = await fetch('/tournament/new', { method: 'POST' });
    if (r.ok) {
      showMsg('reset-msg', '✓ Reset complete. Go to Teams tab to register new teams.', 'success');
      setTimeout(() => loadTourneyTab(), 1000);
    } else {
      const data = await r.json();
      showMsg('reset-msg', `Error: ${data.detail}`, 'error');
    }
  } catch (e) {
    showMsg('reset-msg', `Network error: ${e.message}`, 'error');
  }
}

// ── Teams tab ─────────────────────────────────────────────────────────────────

async function loadTeamsTab() {
  const [teamsResp, statusResp] = await Promise.all([
    fetch('/teams').then(r => r.json()),
    fetch('/tournament/status').then(r => r.json()),
  ]);

  const locked = statusResp.state !== 'not_started';
  const lockBanner = document.getElementById('teams-lock-banner');
  if (lockBanner) lockBanner.hidden = !locked;

  renderTeamsTable(teamsResp.teams, locked);
  renderAddTeamForm(locked);
}

function renderTeamsTable(teams, locked) {
  const area = document.getElementById('teams-table-area');
  if (!area) return;
  if (!teams || teams.length === 0) {
    area.innerHTML = '<p class="muted" style="padding:1rem">No teams registered yet.</p>';
    return;
  }

  const disAttr = locked ? 'disabled' : '';
  const rows = teams.map(t => `
    <tr id="team-row-${t.team_id}">
      <td>${t.team_id}</td>
      <td><input type="text" value="${t.player1}" data-field="p1" data-id="${t.team_id}" ${disAttr}></td>
      <td><input type="text" value="${t.player2}" data-field="p2" data-id="${t.team_id}" ${disAttr}></td>
      <td>
        <button class="btn btn-sm btn-ghost" onclick="saveTeam(${t.team_id})" ${disAttr}>Save</button>
      </td>
      <td id="team-msg-${t.team_id}" style="font-size:0.8rem"></td>
    </tr>`).join('');

  area.innerHTML = `
    <div id="teams-msg" style="margin-bottom:0.5rem"></div>
    <table class="teams-table card" style="margin-bottom:1rem">
      <thead><tr><th>#</th><th>Player 1</th><th>Player 2</th><th></th><th></th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

async function saveTeam(id) {
  const p1 = document.querySelector(`input[data-id="${id}"][data-field="p1"]`);
  const p2 = document.querySelector(`input[data-id="${id}"][data-field="p2"]`);
  const msgEl = document.getElementById(`team-msg-${id}`);

  const body = {};
  if (p1) body.player1_name = p1.value.trim();
  if (p2) body.player2_name = p2.value.trim();

  try {
    const r = await fetch(`/teams/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await r.json();
    if (r.ok) {
      if (msgEl) { msgEl.textContent = '✓ Saved'; msgEl.style.color = '#27ae60'; }
    } else {
      if (msgEl) { msgEl.textContent = data.detail || 'Error'; msgEl.style.color = '#e94560'; }
    }
  } catch (e) {
    if (msgEl) { msgEl.textContent = 'Network error'; msgEl.style.color = '#e94560'; }
  }
}

function renderAddTeamForm(locked) {
  const area = document.getElementById('add-team-area');
  if (!area) return;
  if (locked) { area.innerHTML = ''; return; }

  area.innerHTML = `
    <div class="card">
      <h2>Add Team</h2>
      <div id="add-team-msg"></div>
      <div style="display:grid;grid-template-columns:1fr 1fr auto;gap:0.75rem;align-items:end">
        <label>
          <strong>Player 1</strong>
          <input type="text" id="new-p1" placeholder="Player 1 name">
        </label>
        <label>
          <strong>Player 2</strong>
          <input type="text" id="new-p2" placeholder="Player 2 name">
        </label>
        <button class="btn" onclick="addTeam()">Add Team</button>
      </div>
    </div>`;
}

async function addTeam() {
  const p1 = document.getElementById('new-p1').value.trim();
  const p2 = document.getElementById('new-p2').value.trim();

  try {
    const r = await fetch('/teams', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ player1_name: p1, player2_name: p2 }),
    });
    const data = await r.json();
    if (r.ok) {
      showMsg('add-team-msg', `✓ Team "${p1} & ${p2}" added (ID: ${data.team_id}).`, 'success');
      document.getElementById('new-p1').value = '';
      document.getElementById('new-p2').value = '';
      loadTeamsTab();
    } else {
      showMsg('add-team-msg', `Error: ${data.detail || JSON.stringify(data)}`, 'error');
    }
  } catch (e) {
    showMsg('add-team-msg', `Network error: ${e.message}`, 'error');
  }
}
