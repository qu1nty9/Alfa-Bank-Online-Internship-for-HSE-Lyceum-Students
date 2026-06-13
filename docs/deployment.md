# Deployment

This project can be shared in two ways:

1. Temporary local tunnel for a short demo.
2. Hosted Docker deployment for a stable public URL.

## Temporary Tunnel

Run the API locally:

```bash
PYTHONPATH=.:src uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Expose it with Cloudflare Tunnel:

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

Open the generated `trycloudflare.com` URL and append `/ui`.

Notes:

- The URL works only while both local processes are running.
- Account-less Cloudflare quick tunnels are best for short demos, not production.
- If the local DNS resolver blocks Cloudflare edge discovery, use the hosted deployment path below.

## Render Deployment

The repository includes:

- `Dockerfile` for reproducible container builds.
- `render.yaml` for Render Blueprint setup.
- `/health` endpoint for deployment health checks.
- `/ui` for the demo interface.

Steps:

1. Push the latest code to GitHub.
2. Open Render Dashboard.
3. Create a new Blueprint or Web Service from the GitHub repository.
4. Keep Docker runtime enabled.
5. Use `/health` as the health check path.
6. Open the generated `onrender.com` URL and append `/ui`.

Default deployment mode is bank-safe:

- external LLM calls disabled;
- offline template gateway enabled;
- uploaded files retained for a short demo window;
- no secrets required.
