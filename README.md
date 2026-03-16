# 🎬 Director's Lab

> **Multimodal AI Directing Agent** — pitch a scene in text, voice, or image and watch a full cinematic storyboard come to life: Gemini-written panels, AI-generated stills, ambient score, character dialogue voiced by gender-matched AI voices, and a 15-second cinematic clip with merged audio.

Built for the **Gemini Live Agent Challenge · Creative Storyteller category**.

---

## ✨ What It Does

You're the writer. Gemini is the director.

1. **Pitch your scene** — type it, speak it, or drop a reference image
2. **Answer one question** — the director asks a single clarifying question to nail the emotional core
3. **The director takes over** — Gemini writes the 4-beat arc, Imagen 3 paints each frame, Lyria composes the ambient score, Gemini TTS voices every line, Veo 3.1 renders the final cinematic clip
4. **Stay in control** — write a director's note or hit a Quick Cut to revise; approve only the panels you want re-generated (HITL loop, no surprise Imagen costs)

---

## 🎥 Demo

| Step | What happens |
|------|--------------|
| 🎙 **Voice / 📷 Image / ⌨ Text** | Three input modalities tracked through the whole flow |
| 🤔 **Clarifying question** | Gemini asks one cinematic question to focus the emotional arc |
| 🎨 **Storyboard** | 4 panels (Establish → Escalate → Tension → Resolve) with Imagen 3 stills |
| 🎵 **Ambient score** | Lyria WAV per panel, mood-matched to the scene |
| 🗣 **Voiced dialogue** | Gemini TTS with gender-matched voices (Charon ♂ / Aoede ♀) |
| 🎬 **15s cinematic clip** | Veo 3.1 clip freeze-extended to 15 s, score + voice merged via ffmpeg |
| ✏️ **HITL revision loop** | Preview Gemini's proposed edits before any Imagen generation fires |

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Browser (React 18)                   │
│   Text / Voice (Web Speech API) / Image → pitch textarea    │
│   State machine: IDLE → CLARIFYING → GENERATING → SCENE     │
│   HITL overlay: PREVIEWING_REVISION → REVIEW → REVISING     │
└──────────────────────┬──────────────────────────────────────┘
                       │ /api/** (Vite proxy in dev,
                       │  Firebase Hosting rewrite in prod)
┌──────────────────────▼──────────────────────────────────────┐
│                  FastAPI backend (Cloud Run)                 │
│                                                             │
│  /api/scene/clarify          → Gemini 2.5 Flash             │
│  /api/scene/generate         → Gemini + Imagen + Lyria +    │
│                                 Gemini TTS + Veo 3.1 + ffmpeg │
│  /api/scene/{id}/preview-revision → Gemini (text only)      │
│  /api/scene/{id}/revise      → Gemini + Imagen (approved    │
│                                 panels only)                │
└───────┬──────────┬──────────┬──────────┬────────────────────┘
        │          │          │          │
   Firestore    Cloud      Vertex AI   Cloud
   (scenes)    Storage    (Imagen 3,   Run
               (PNG/WAV/   Lyria,      (host)
                MP4)       Veo 3.1)
```

---

## 🧠 AI Stack

| Capability | Model | API |
|------------|-------|-----|
| Scene writing, clarification, revision | Gemini 2.5 Flash (`gemini-2.5-flash`) | Google AI Studio / Vertex AI |
| Storyboard images | Imagen 3 (`imagen-3.0-generate-001`) | Vertex AI |
| Ambient music score | Lyria (`lyria-002`) | Vertex AI REST |
| Character voice (TTS) | Gemini TTS (`gemini-2.5-flash-preview-tts`) | Google AI Studio |
| Cinematic video clip | Veo 3.1 (`veo-3.1-fast-generate-preview`) | Vertex AI LRO REST |
| Video + audio merge | ffmpeg (`tpad` freeze-extend to 15 s) | Local subprocess |

---

## 🗂 Project Structure

```
directors-lab/
├── README.md
├── CLAUDE.md                    ← Claude Code guidance
├── .gitignore
├── firebase.json                ← Hosting + Firestore config
├── firestore.rules
├── backend/
│   ├── main.py                  ← FastAPI routes (thin wrappers)
│   ├── agent.py                 ← All AI logic
│   ├── beat_map.py              ← BeatMap dataclass
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
└── frontend/
    ├── index.html
    ├── vite.config.js
    ├── package.json
    └── src/
        ├── App.jsx              ← State machine + all API calls
        ├── index.css            ← Single CSS file, CSS variables
        └── components/
            ├── ProductionBeat.jsx
            ├── BeatMap.jsx
            ├── DirectorNote.jsx
            ├── QuickCuts.jsx
            └── RevisionPreview.jsx
```

---

## 🚀 Quick Start (Local Dev)

### Prerequisites
- Python 3.12+
- Node.js 18+
- A Google Cloud project with Vertex AI API enabled
- A Gemini API key from [AI Studio](https://aistudio.google.com/apikey)

### 1 — Clone

```bash
git clone https://github.com/Sakethv7/director-s-lab.git
cd director-s-lab
```

### 2 — Backend

```bash
cd backend
cp .env.example .env          # fill in your keys
pip install -r requirements.txt
uvicorn main:app --reload --port 8080
```

### 3 — Frontend (separate terminal)

```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

Vite proxies `/api/**` → `localhost:8080` automatically — no env vars needed.

---

## ⚙️ Environment Variables

### `backend/.env`

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | Yes | Gemini 2.5 Flash + TTS (AI Studio key) |
| `GEMINI_MODEL` | Yes | `gemini-2.5-flash` |
| `GOOGLE_CLOUD_PROJECT` | Yes | GCP project ID (for Vertex AI) |
| `GOOGLE_CLOUD_REGION` | Yes | `us-central1` |
| `GOOGLE_APPLICATION_CREDENTIALS` | Optional | Path to service account JSON (if not using `gcloud` ADC) |
| `GCS_BUCKET_NAME` | Yes | Cloud Storage bucket for media files |
| `FIRESTORE_COLLECTION` | Yes | Firestore collection name (e.g. `scenes`) |
| `CORS_ORIGINS` | Production only | Comma-separated Firebase Hosting URLs |

### Google Cloud Auth

Vertex AI uses **Application Default Credentials**, not an API key.

```bash
# Option A — gcloud (recommended)
gcloud auth application-default login

# Option B — service account JSON key
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```

**Required IAM roles:** `Vertex AI User` · `Cloud Datastore User` · `Storage Object Admin`

---

## ☁️ Deploy to GCP

### Backend → Cloud Run

```bash
gcloud run deploy directors-lab-api \
  --source backend/ \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars "GEMINI_API_KEY=<key>,GOOGLE_CLOUD_PROJECT=<proj>,GCS_BUCKET_NAME=<bucket>,FIRESTORE_COLLECTION=scenes,CORS_ORIGINS=https://<project>.web.app"
```

No local Docker needed — Cloud Build handles the container.

### Frontend → Firebase Hosting

```bash
firebase use --add          # link your GCP project
cd frontend && npm run build
cd .. && firebase deploy --only hosting
```

Firebase Hosting rewrites `/api/**` → Cloud Run. **No `VITE_API_URL` needed.**

---

## 🗃 GCS Bucket Setup

```bash
gsutil mb -p $PROJECT -l us-central1 gs://$BUCKET
gsutil uniformbucketlevelaccess set on gs://$BUCKET
gsutil iam ch allUsers:objectViewer gs://$BUCKET
```

Media is stored at deterministic public URLs:
- Images: `https://storage.googleapis.com/{BUCKET}/panels/{scene_id}/panel_{n}.png`
- Audio:  `https://storage.googleapis.com/{BUCKET}/audio/{scene_id}/panel_{n}.wav`
- Video:  `https://storage.googleapis.com/{BUCKET}/video/{scene_id}/panel_{n}.mp4`

---

## 🎨 Design System

Dark cinematic aesthetic. All styles in `src/index.css` using CSS custom properties:

| Variable | Value | Use |
|----------|-------|-----|
| `--bg-base` | `#0d0d0d` | Page background |
| `--bg-panel` | `#1a1a1a` | Cards |
| `--gold` | `#c9a84c` | Primary accent / logo |
| `--tension-color` | `#e63946` | Beat map tension |
| `--longing-color` | `#9b59b6` | Beat map longing |
| `--resolve-color` | `#2ecc71` | Beat map resolve |
| `--font-mono` | Courier New | Labels, badges |

Film-grain overlay via a fixed `body::before` SVG noise filter.

---

## 🔄 HITL Revision Loop

The human stays in control of every Imagen 3 generation:

```
Director's Note / Quick Cut
        ↓
POST /preview-revision   (Gemini text only — fast, no image costs)
        ↓
RevisionPreview modal shows:
  • Beat map delta (old vs new bars + numeric diff)
  • Per-panel change_type badge (↻ revise / + add element)
  • Toggle each panel on/off
        ↓
Human clicks "Apply N Panels →"
        ↓
POST /revise  { approved_panels: [...] }
  → only approved panels get new Gemini content + Imagen images
  → untouched panels keep their original content and URLs
```

---

## 🛡 Security Notes

- **Never commit `.env`** — it is gitignored; only `.env.example` (with placeholders) is tracked
- **Service account JSON files** are excluded by `.gitignore` pattern matching GCP Console download names
- On Cloud Run, set secrets via `--set-env-vars` — no JSON key file in the container
- `CORS_ORIGINS` must be set on Cloud Run for production

---

## 📝 Conventions

- No new files unless necessary — prefer editing existing ones
- All AI logic lives in `backend/agent.py`; `main.py` is thin wrappers
- All CSS in `src/index.css` — no Tailwind, no CSS-in-JS
- State machine lives entirely in `App.jsx`; components receive callbacks, never call the API
- All Gemini calls use `client.aio.models.generate_content()` with `asyncio.wait_for` timeouts
- All blocking I/O runs in `loop.run_in_executor()` — never blocks the async event loop
- `approved_panels` is always human-supplied — the backend never silently decides what to regenerate

---

## 📄 License

MIT — see [LICENSE](LICENSE) for details.

---

<div align="center">
  <sub>Built with ❤️ for the Gemini Live Agent Challenge · Creative Storyteller</sub>
</div>
