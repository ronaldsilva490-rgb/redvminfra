# REDIA

REDIA is a standalone WhatsApp AI runtime. It is designed for a separate VM, with:

- WhatsApp connection through Baileys.
- Local SQLite storage for config, conversations, summaries and long-term memory.
- RED Systems proxy as the main Ollama-compatible AI backend.
- Image analysis and audio transcription as required parts of the message pipeline.
- Edge TTS only, with a configurable probability for sending replies as voice notes.
- A local dashboard for configuration and model experiments.

## Start

```bash
cp .env.example .env
npm install
npm start
```

Dashboard:

```text
http://localhost:3099
```

Docker:

```bash
docker compose up -d --build
```

## Model roles

The first version separates model roles instead of using one model for everything:

- `chat.default_model`: human conversation.
- `chat.vision_model`: image analysis.
- `learning.model`: JSON summaries, facts, profiles and vibe.
- `proactive.model`: decisions about when the AI should participate.

The dashboard exposes these fields so we can benchmark `gemma4`, `gemini flash`, `gpt-oss`, `qwen3-coder-next`, vision models and future models without changing code.
