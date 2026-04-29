# Mario Kart Tournament

A self-hosted tournament management system for 12-team, 6-round Mario Kart events.
Runs entirely on a Raspberry Pi — no internet connection required.

---

## Server Setup

### Dependencies

```bash
pip install fastapi uvicorn[standard] pydantic python-multipart
```

### Database directory

The app stores its database at `db/mariokart.db`. Create the directory before first run:

```bash
mkdir -p db
```

### Starting the server

```bash
python3 -m uvicorn app:app --host 0.0.0.0 --port 8000
```

The server is then reachable from any device on the same network:

- **Public view** — `http://<pi-hostname>:8000/`
- **Admin panel** — `http://<pi-hostname>:8000/admin`

Replace `<pi-hostname>` with your Pi's hostname or IP address (e.g. `mariokart.local` if mDNS is configured).

### Autostart on boot (optional)

Create `/etc/systemd/system/mariokart.service`:

```ini
[Unit]
Description=Mario Kart Tournament Server
After=network.target

[Service]
User=pi
WorkingDirectory=/home/pi/mariokart_tourney/rosterBracket
ExecStart=python3 -m uvicorn app:app --host 0.0.0.0 --port 8000
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Then enable it:

```bash
sudo systemctl enable mariokart
sudo systemctl start mariokart
```

### Crash / restart recovery

If the server is killed mid-tournament it will automatically reload the last incomplete tournament from the database on the next startup. No manual intervention needed.

---

## Admin Usage

### Credentials

| Username | Password |
|----------|----------|
| `admin`  | `password` |

Log in at `http://<pi-hostname>:8000/admin/login`.

---

### Running a tournament

#### 1. Register teams (Teams tab)

Add all 12 teams before starting. Each team has two players. Names must be unique across the whole roster. Teams can be edited any time before the tournament starts — the roster locks once Round 1 begins.

> **Test script** — `test/populate_users.py` will register all 12 default teams automatically:
> ```bash
> python3 test/populate_users.py
> ```

#### 2. Assign cup groups (Tournament tab)

Drag and drop the 12 teams into **Group A** and **Group B** (6 teams each). These become the two cups for Round 1. The Start button enables once both groups have exactly 6 teams.

Click **Start Tournament** to lock the roster and begin Round 1.

#### 3. Enter race results (Results tab)

Select **Round**, **Cup**, and **Race** from the dropdowns and click **Load**.

Enter the finishing position (1–12) for each player, then click **Submit Race**. You can submit each race individually as it finishes — you don't need to wait until all four races in a cup are done.

To correct a previously submitted race, load it again, update the placements, and click **Correct Race**.

#### 4. Rounds advance automatically

Once all 4 races in both cups of a round are submitted, the server scores the results and opens the next round. Cups for rounds 2–6 are seeded by score:

| Round | Cup 1 | Cup 2 |
|-------|-------|-------|
| 2, 4, 6 | Elite (top 6) | Standard (bottom 6) |
| 3, 5 | Standard (bottom 6) | Elite (top 6) |

#### 5. Tournament ends automatically

After Round 6 results are submitted the tournament is marked complete. The Tournament tab shows the final podium. Click **Reset for New Tournament** to clear state and start fresh.

---

### Public view

`http://<pi-hostname>:8000/` — no login required. Shows the live leaderboard, current cup status, and a projected seeding for the next round. Refreshes automatically every 15 seconds.

---

## TODO

- Add team name (separate from the two player names)
- Add statistics on individual player performance (admin only)
- Beerio Kart page
