# Smart Carrier API

FastAPI cloud service connecting the GitHub Pages client, Supabase PostgreSQL, and ROS2 robot.

## Local development

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload
```

- Health check: `GET http://127.0.0.1:8000/health`
- OpenAPI UI: `http://127.0.0.1:8000/docs`

Apply `migrations/001_robot_state.sql` in the Supabase SQL Editor after the existing locations/tasks migration.

## Oracle Cloud VM

Production runs as two Docker Compose services:

- `api`: FastAPI on the private Docker network only
- `caddy`: public reverse proxy on ports 80 and 443

### First deployment by public IP

On a new Ubuntu VM, install Docker from Docker's official APT repository:

```bash
git clone https://github.com/alanlu01/smart-carrier-api.git
cd smart-carrier-api
chmod +x deploy/oracle/install-docker-ubuntu.sh
./deploy/oracle/install-docker-ubuntu.sh
```

Sign out and reconnect by SSH once so that Docker group membership takes effect. Then deploy:

```bash
cp .env.example .env
nano .env
docker compose -f compose.oracle.yml up -d --build
docker compose -f compose.oracle.yml ps
curl http://127.0.0.1/health
```

Keep `API_DOMAIN=:80` until a domain name points to the VM. The public health check is then:

```bash
curl http://VM_PUBLIC_IP/health
```

### Enable HTTPS

Create a DNS `A` record such as `api.example.com` pointing to the VM public IP. Then edit `.env`:

```dotenv
APP_ENV=production
API_DOMAIN=api.example.com
CORS_ORIGINS=https://alanlu01.github.io
```

Apply the change:

```bash
docker compose -f compose.oracle.yml up -d
curl https://api.example.com/health
```

Caddy obtains and renews the TLS certificate automatically. OCI ingress rules must allow TCP 80 and TCP/UDP 443. Do not expose port 8000 in OCI or Ubuntu's firewall.

Finally, set the web Repository variable `VITE_API_BASE_URL` to the HTTPS API URL and rebuild GitHub Pages.

### Operations

```bash
# Logs
docker compose -f compose.oracle.yml logs -f --tail=200

# Pull and deploy a new version
git pull --ff-only
docker compose -f compose.oracle.yml up -d --build

# Restart
docker compose -f compose.oracle.yml restart

# Stop without deleting Caddy certificate data
docker compose -f compose.oracle.yml down
```

Never commit `.env`. Never expose `SUPABASE_SERVICE_ROLE_KEY` or `ROBOT_API_TOKEN` to the web Repository.
