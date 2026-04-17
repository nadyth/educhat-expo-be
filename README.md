# Edu Chat BE

## Setup

```bash
uv sync
```

Create a `.env` file (see `.env.example` for required variables).

## Running

```bash
uv run serve
```

Server starts at `http://localhost:8000`.

### Tunneling (public URL)

To expose your local server on a live domain accessible from anywhere, set `TUNNEL=true` in your `.env`:

```bash
TUNNEL=true uv run serve
```

This requires `cloudflared`. Install it with:

**macOS:**
```bash
brew install cloudflared
```

**Linux:**
```bash
# Debian/Ubuntu
curl -fsSL https://pkg.cloudflare.com/cloudflared-stable-linux-amd64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb && rm cloudflared.deb

# Or via apt
sudo mkdir -p --mode=0755 /usr/share/keyrings
curl -fsSL https://pkg.cloudflare.com/cloudflared/gpg.key | sudo tee /usr/share/keyrings/cloudflared.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/cloudflared.gpg] https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/cloudflared.list >/dev/null
sudo apt update && sudo apt install cloudflared
```

**Windows:**
```powershell
winget install Cloudflare.cloudflared
```

No Cloudflare account needed — the free quick tunnel gives you a random `*.trycloudflare.com` URL printed on startup.

## Debug Endpoints

When `DEBUG=true` is set in `.env`:

- `GET /auth/gen-token` — Returns access & refresh tokens for a test user (`test@local.dev`)
- `GET /auth/gen-google-auth` — Starts Google OAuth flow to obtain an ID token for testing `/auth/login`