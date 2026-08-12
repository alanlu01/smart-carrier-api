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

## Zeabur

Zeabur has not been connected yet. When ready:

1. Create a Project and deploy this GitHub Repository as a service.
2. Add `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `ROBOT_API_TOKEN`, and `CORS_ORIGINS`.
3. Expose the service port; the Docker command automatically binds to Zeabur's `$PORT`.
4. Set the resulting HTTPS URL as the web Repository variable `VITE_API_BASE_URL`.

Never expose `SUPABASE_SERVICE_ROLE_KEY` or `ROBOT_API_TOKEN` in the web Repository.
