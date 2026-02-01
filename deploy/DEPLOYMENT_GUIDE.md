# MusicBuddy Deployment Guide

## Quick Comparison

| Platform | Free Tier | Best For | Uptime |
|----------|-----------|----------|--------|
| **Render** | 750 hrs/month | Beginners | 99.9% |
| **Fly.io** | 3 VMs free | Low latency | 99.99% |
| **Oracle Cloud** | Always free | Production | 99.9% |
| **PythonAnywhere** | Limited | Quick test | 99% |
| **Koyeb** | Nano instance | Easy setup | 99.9% |

---

## Option 1: Render (Recommended for Beginners)

Render offers free background workers - perfect for Telegram bots.

### Steps:
1. Sign up at https://render.com
2. Create a new "Background Worker"
3. Connect your GitHub repo
4. Configure:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python run_bot.py`
5. Add Environment Variables:
   ```
   TELEGRAM_BOT_TOKEN=your_token
   GROQ_API_KEY=your_groq_key
   PLATFORM=youtube_music
   ```
6. Deploy!

### render.yaml (add to repo root):
```yaml
services:
  - type: worker
    name: musicbuddy-bot
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: python run_bot.py
    envVars:
      - key: TELEGRAM_BOT_TOKEN
        sync: false
      - key: GROQ_API_KEY
        sync: false
      - key: PLATFORM
        value: youtube_music
```

---

## Option 2: Fly.io (Best Performance)

Fly.io offers excellent global performance with edge deployment.

### Steps:
1. Install flyctl: `curl -L https://fly.io/install.sh | sh`
2. Sign up: `fly auth signup`
3. Create `fly.toml`:

```toml
app = "musicbuddy-bot"
primary_region = "iad"

[build]
  builder = "paketobuildpacks/builder:base"

[env]
  PLATFORM = "youtube_music"

[[services]]
  internal_port = 8080
  protocol = "tcp"

[processes]
  app = "python run_bot.py"
```

4. Create `Procfile`:
```
worker: python run_bot.py
```

5. Deploy:
```bash
fly launch
fly secrets set TELEGRAM_BOT_TOKEN=your_token
fly secrets set GROQ_API_KEY=your_groq_key
fly deploy
```

---

## Option 3: Oracle Cloud Free Tier (Best for Production)

Oracle offers **always free** VMs - 2 AMD instances or 4 ARM instances.

### Steps:
1. Sign up at https://cloud.oracle.com (requires credit card for verification only)
2. Create a Compute Instance:
   - Shape: VM.Standard.E2.1.Micro (always free)
   - Image: Ubuntu 22.04
   - Download SSH key

3. Connect and setup:
```bash
ssh -i your_key.pem ubuntu@your_instance_ip

# Install Python
sudo apt update && sudo apt install -y python3-pip python3-venv

# Clone your repo
git clone https://github.com/yourusername/Spotify_AI_Agent.git
cd Spotify_AI_Agent

# Setup environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create .env file
cat > .env << EOF
TELEGRAM_BOT_TOKEN=your_token
GROQ_API_KEY=your_groq_key
PLATFORM=youtube_music
EOF

# Run with systemd (see musicbot.service)
sudo cp deploy/musicbot.service /etc/systemd/system/
# Edit the service file with correct paths
sudo nano /etc/systemd/system/musicbot.service
sudo systemctl daemon-reload
sudo systemctl enable musicbot
sudo systemctl start musicbot
```

---

## Option 4: Koyeb (Easy & Fast)

Koyeb offers a generous free tier with simple deployment.

### Steps:
1. Sign up at https://koyeb.com
2. Create new App > GitHub
3. Configure:
   - **Builder**: Buildpack
   - **Run command**: `python run_bot.py`
4. Add environment variables
5. Deploy!

---

## Option 5: PythonAnywhere (Quick Testing)

Good for testing, limited free tier.

### Steps:
1. Sign up at https://pythonanywhere.com
2. Open a Bash console
3. Clone repo: `git clone https://github.com/yourusername/Spotify_AI_Agent.git`
4. Setup virtualenv and install requirements
5. Use "Always-on tasks" (paid feature) or scheduled tasks

---

## Option 6: Self-Hosted (VPS/Raspberry Pi)

For full control, use any VPS or even a Raspberry Pi at home.

### Using Docker:

Create `Dockerfile`:
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "run_bot.py"]
```

Create `docker-compose.yml`:
```yaml
version: '3.8'
services:
  musicbuddy:
    build: .
    restart: always
    env_file:
      - .env
    volumes:
      - ./data:/app/data
```

Run:
```bash
docker-compose up -d
```

---

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | From @BotFather |
| `GROQ_API_KEY` | Recommended | Free LLM API from groq.com |
| `GEMINI_API_KEY` | Alternative | From Google AI Studio |
| `PLATFORM` | No | `youtube_music` or `spotify` |
| `DATA_DIR` | No | Where to store memory/data |

---

## Troubleshooting

### Bot not responding
- Check logs: `journalctl -u musicbot -f` (systemd) or `fly logs` (Fly.io)
- Verify TELEGRAM_BOT_TOKEN is correct

### Memory/context not persisting
- Ensure DATA_DIR is set to a persistent volume
- On Render: use persistent disk
- On Fly.io: use volumes

### LLM not working
- Verify GROQ_API_KEY or GEMINI_API_KEY is set
- Bot works without LLM but with limited conversation

---

## Recommended Setup

For a **mini startup**, I recommend:

1. **Development**: Run locally with `python run_bot.py`
2. **Staging**: Deploy to Render (free tier)
3. **Production**: Oracle Cloud Free Tier (always free, reliable)

This gives you a completely **$0/month** infrastructure with production-grade reliability.
