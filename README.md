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
CORS_ORIGINS=https://alanlu01.github.io
API_DOMAIN=:80
```

Single-quote password and token values so Compose treats special characters literally. Never commit `.env`, the wallet, database credentials, or robot token.

### Build and migrate

```bash
docker compose -f compose.oracle.yml build api
docker compose -f compose.oracle.yml run --rm api python -m app.migrations
```

The idempotent migration creates locations, tasks, robots, power slots, robot events, indexes, and A1/F1/E1/S1 seed locations.

### Apply measured map locations

Measure each service point with the robot Repository's RViz location calibrator. Preview the
result inside the API container before changing Oracle:

```bash
docker compose -f compose.oracle.yml run --rm api \
  python -m app.location_calibration A1 -0.45 -0.35 0.0 --name '門口'
```

After the robot-side map validator reports `PASS`, apply the same pose explicitly:

```bash
docker compose -f compose.oracle.yml run --rm api \
  python -m app.location_calibration A1 -0.45 -0.35 0.0 --name '門口' --apply
```

The command refuses to change a location that has pending or in-progress tasks. Repeat for
A1, E1, F1, and S1, then verify `/api/v1/locations` before enabling real task claims.

The robot map is the source of truth. The current cloud mapping is:

| Code | Name | x | y | yaw |
| --- | --- | ---: | ---: | ---: |
| A1 | 門口 | -0.45 | -0.35 | 0.0 |
| E1 | 廚房 | -1.5 | 5.0 | 0.0 |
| F1 | 廁所 | -4.0 | 1.5 | 3.14 |
| S1 | 客廳TV | 0.4 | 0.0 | 0.0 |

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
