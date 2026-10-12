# Smart Carrier API

FastAPI service connecting the GitHub Pages client, Oracle Autonomous AI Database, and the ROS2 robot.

## Architecture

```text
GitHub Pages → Caddy HTTPS → FastAPI → Oracle Autonomous AI Database
                                      ↑
                                  ROS2 robot
```

The API uses the official `python-oracledb` Thin driver with an mTLS instance wallet. Oracle Instant Client is not required.

## Local development

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload
```

- Liveness: `GET http://127.0.0.1:8000/health`
- Database readiness: `GET http://127.0.0.1:8000/ready`
- OpenAPI UI: `http://127.0.0.1:8000/docs`

Database access is lazy, so `/health` and unit tests do not require Oracle credentials. `/ready` performs `SELECT 1 FROM dual` and returns 503 when the database is unavailable.

Live robot state is available to the web client at `GET /api/v1/robots/R1`.
Authenticated robot integrations use the task `claim`, `progress`, `result`, and
`release` endpoints. Terminal requests include a UUID `event_id`, so retries are
idempotent. Progress exposes the expected slot, an incorrectly changed slot, and
the physical-action deadline without marking arrival as completion.

## Oracle Cloud VM

Production runs as two Docker Compose services:

- `api`: non-root FastAPI process on the private Docker network
- `caddy`: public reverse proxy on ports 80 and 443

### Wallet

Download an instance wallet from Oracle Autonomous AI Database and extract it outside the Repository:

```text
/home/ubuntu/smart-carrier-secrets/oracle-wallet
```

The Thin driver requires `tnsnames.ora` and `ewallet.pem`. Keep the whole wallet directory private. The container runs as UID/GID 10001, so assign ownership without making the wallet world-readable:

```bash
sudo chown -R 10001:10001 /home/ubuntu/smart-carrier-secrets/oracle-wallet
sudo find /home/ubuntu/smart-carrier-secrets/oracle-wallet -type d -exec chmod 700 {} \;
sudo find /home/ubuntu/smart-carrier-secrets/oracle-wallet -type f -exec chmod 600 {} \;
```

List the available TNS aliases:

```bash
sudo grep -E '^[[:alnum:]_]+[[:space:]]*=' \
  /home/ubuntu/smart-carrier-secrets/oracle-wallet/tnsnames.ora
```

Use the `_low` alias for this small API instance, normally `carrierdb_low`.

### Environment

```bash
cp .env.example .env
nano .env
```

Production example:

```dotenv
APP_ENV=production
ORACLE_USER=ADMIN
ORACLE_PASSWORD='database-password'
ORACLE_DSN=carrierdb_low
ORACLE_WALLET_DIR=/opt/oracle/wallet
ORACLE_WALLET_PASSWORD='wallet-download-password'
ORACLE_POOL_MAX=4
ORACLE_WALLET_HOST_PATH=/home/ubuntu/smart-carrier-secrets/oracle-wallet
ROBOT_API_TOKEN='long-random-token'
ADMIN_PASSWORD_HASH='scrypt$...'
ADMIN_SESSION_SECRET='separate-long-random-secret'
ADMIN_SESSION_TTL_SECONDS=1800
CORS_ORIGINS=https://alanlu01.github.io
API_DOMAIN=:80
```

Single-quote password and token values so Compose treats special characters literally. Never commit `.env`, the wallet, database credentials, or robot token.

Generate the administrator password hash on a trusted machine, then place only the resulting
`scrypt$...` value in `ADMIN_PASSWORD_HASH`:

```bash
python -c "from app.security import hash_admin_password; print(hash_admin_password('your-password'))"
```

The admin login returns a short-lived signed session. Failed login attempts are accepted four
times; the fifth failure starts an exponentially increasing 30–300 second cooldown.

### Build and migrate

```bash
docker compose -f compose.oracle.yml build api
docker compose -f compose.oracle.yml run --rm api python -m app.migrations
```

The idempotent migration creates locations, tasks, robots, power slots, robot events, indexes,
and A1/E1/F1/C1/L1/B1 seed locations. Existing S1 records are retained for task history but disabled for
new orders and task claims.

### Apply measured map locations

Measure each service point with the robot Repository's RViz location calibrator. Preview the
result inside the API container before changing Oracle:

```bash
docker compose -f compose.oracle.yml run --rm api \
  python -m app.location_calibration A1 7.8 -6.6 0.0 --name '右樓梯口'
```

After the robot-side map validator reports `PASS`, apply the same pose explicitly:

```bash
docker compose -f compose.oracle.yml run --rm api \
  python -m app.location_calibration A1 7.8 -6.6 0.0 --name '右樓梯口' --apply
```

The command refuses to change a location that has pending or in-progress tasks. Repeat for
each existing location, then verify `/api/v1/locations` before enabling real task claims.
New locations are created by the seed migration above; the calibration command only updates
locations that already exist. Run the migration when no pending or in-progress tasks use the
affected locations, since its seed statements replace their coordinates.

The robot map is the source of truth. The current cloud mapping is:

| Code | Name | x | y | yaw |
| --- | --- | ---: | ---: | ---: |
| A1 | 右樓梯口 | 7.8 | -6.6 | 0.0 |
| E1 | 左樓梯口 | 7.2 | 5.7 | 0.0 |
| F1 | 電機工程學系 | -3.0 | 5.0 | 0.0 |
| C1 | CYCU EE | 2.0 | 5.18 | 0.0 |
| L1 | 座位燈 | 1.4 | -5.3 | 0.0 |
| B1 | 座位 | 6.6 | -0.3 | 0.0 |

All six service points use floor `3F`. No new headings were supplied with these coordinates,
so yaw remains `0.0` radians.

### Start by public IP

Keep `API_DOMAIN=:80` until a domain points to the VM:

```bash
docker compose -f compose.oracle.yml up -d
docker compose -f compose.oracle.yml ps
curl http://127.0.0.1/health
curl http://127.0.0.1/ready
curl http://VM_PUBLIC_IP/health
```

OCI ingress rules must allow TCP 80. Do not expose port 8000.

### Enable HTTPS

Create a DNS `A` record such as `api.example.com` pointing to the reserved VM public IP. Then edit `.env`:

```dotenv
API_DOMAIN=api.example.com
```

Apply the change:

```bash
docker compose -f compose.oracle.yml up -d
curl https://api.example.com/ready
```

Caddy obtains and renews the TLS certificate automatically. OCI ingress rules must allow TCP 80, TCP 443, and optionally UDP 443 for HTTP/3.

Finally, set the web Repository variable `VITE_API_BASE_URL` to the HTTPS API URL and rebuild GitHub Pages.

### Operations

```bash
# Logs
docker compose -f compose.oracle.yml logs -f --tail=200

# Pull and deploy a new version
git pull --ff-only
docker compose -f compose.oracle.yml up -d --build

# Re-run idempotent migrations after an update
docker compose -f compose.oracle.yml run --rm api python -m app.migrations

# Restart
docker compose -f compose.oracle.yml restart

# Stop without deleting Caddy certificate data
docker compose -f compose.oracle.yml down
```

`docker compose down` preserves named volumes unless `--volumes` is explicitly supplied.

### Queue and physical-action contract

Each order has `quantity=1`. A robot must send a heartbeat before claiming.
Claims lock the robot row in Oracle and retain at most three `in_progress` orders,
including orders awaiting cancellation or result synchronization. New claims expose
`progress_state=queued_on_robot`. `claimed_task_ids` contains every retained order;
`current_task_id` is set only when a task has started its execution stages. A second
order cannot enter an execution stage until the first reaches a terminal state.
The bridge supplies projected inventory after its existing slot reservations.
Each bridge claim includes a durable `claim_request_id`; retrying the same request
returns the original assignment instead of claiming another order. On startup and
after reconnecting, the bridge reads `GET /api/v1/robots/{robot_id}/tasks` to recover
an assignment whose original HTTP response was lost.

`arrived`, `waiting_action`, `verifying_action`, and `result_pending` are not terminal.
Only the robot result endpoint changes an executing order to `done`, `failed`, or
`cancelled`. Progress persists `warning`, `expected_slot`, `changed_slot`,
`changed_slots`, and the UTC `action_deadline`. Active cancellations always wait for
a robot acknowledgement, including while the heartbeat is offline.

The regular admin force-cancel endpoint remains a safe stop request for active tasks.
Only after an operator physically confirms that the robot stopped may the admin client
call `POST /api/v1/admin/orders/{task_id}/force-finalize` with
`{"reason":"...","operator_confirmed_stopped":true}`. This explicit recovery path
terminally cancels an orphaned task and clears stale physical-action fields.

Slot availability uses both `enabled` and `sensor_ok`. `empty` has charge 0,
`full` has charge 100, and `low`, `unknown`, or `disabled` have null charge.
A `ready` slot with an unknown charge cannot satisfy a positive minimum charge.

### Verify Oracle queue behavior without moving a robot

After deployment and migration, run the optional integration check in an environment
with the API dependencies and `httpx` installed:

```bash
python scripts/verify_oracle_queue.py
```

It creates five uniquely named disposable `qa_*` tables in the configured Oracle
schema, runs FastAPI requests against those tables, and drops them in `finally`.
It checks four concurrent claims, capacity three, FIFO refill, persistent queue
reads, one executing task, result retries, wrong-slot warnings, and safe cancellation.
It never creates production orders or sends robot commands. DDL permissions are required.
This is an Oracle/API integration check; physical bridge restart and INA3221 validation
must still be performed with the actual robot online.
