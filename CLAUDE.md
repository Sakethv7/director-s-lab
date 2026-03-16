# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Director's Lab

Multimodal AI directing agent built for the **Gemini Live Agent Challenge (Creative Storyteller category)**.

---

## Commands

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8080   # dev server

# Run tests
pip install -r requirements-dev.txt
pytest                                  # all tests (asyncio_mode=auto via pytest.ini)
pytest tests/test_agent.py::test_name  # single test
```

### Frontend
```bash
cd frontend
npm install
npm run dev       # http://localhost:5173 — Vite proxies /api/** to :8080
npm run build     # production build → dist/
npm run lint      # ESLint
```

---

## Stack

| Layer      | Technology                                          |
|------------|-----------------------------------------------------|
| Backend    | FastAPI (Python 3.12), Uvicorn                      |
| AI — Text  | Google Gemini 2.5 Flash (`gemini-2.5-flash`) via `google-genai` SDK |
| AI — Image | Imagen 3 (`imagen-3.0-generate-001`) via Vertex AI  |
| AI — Audio | Lyria (`lyria-002`) via Vertex AI REST API          |
| AI — Video | Veo 3.1 (`veo-3.1-fast-generate-preview`) via Vertex AI LRO REST API |
| Database   | Firestore (`scenes` collection)                     |
| Storage    | Cloud Storage (images/audio/video, publicly readable) |
| Frontend   | React 18 + Vite, plain CSS (no Tailwind, no CSS-in-JS) |
| Deploy     | Cloud Run (backend) + Firebase Hosting (frontend)   |

---

## Folder Structure

```
directors-lab/
├── CLAUDE.md                    ← this file
├── .gitignore
├── firebase.json                ← Firebase Hosting + Firestore config
├── firestore.rules              ← backend writes only; public reads
├── backend/
│   ├── main.py                  ← FastAPI routes
│   ├── agent.py                 ← all AI logic (Gemini + Imagen + GCS + Firestore)
│   ├── beat_map.py              ← BeatMap dataclass (tension/longing/resolve)
│   ├── requirements.txt
│   ├── Dockerfile               ← Cloud Run target, port 8080
│   └── .env.example
└── frontend/
    ├── index.html
    ├── vite.config.js           ← /api proxied to localhost:8080 in dev
    ├── package.json
    ├── .env.example             ← VITE_API_URL for production
    └── src/
        ├── main.jsx
        ├── App.jsx              ← state machine + all API calls
        ├── index.css            ← single CSS file, CSS variables for theming
        └── components/
            ├── StoryboardPanel.jsx
            ├── BeatMap.jsx
            ├── DirectorNote.jsx
            ├── QuickCuts.jsx
            └── RevisionPreview.jsx  ← HITL revision overlay
```

---

## API Routes

```
GET  /health
POST /api/scene/clarify                        → { scene_id, question }
POST /api/scene/generate                       → SceneResponse
POST /api/scene/{scene_id}/preview-revision    → PreviewRevisionResponse  (no image gen)
POST /api/scene/{scene_id}/revise              → SceneResponse  (images for approved panels only)
GET  /api/scene/{scene_id}                     → SceneResponse
```

---

## Core Data Models

### SceneResponse
```python
{
  scene_id, scene_prompt, clarifying_question, clarification,
  scene_summary, beat_map, panels, created_at, updated_at
}
```

### BeatMap
```python
{ tension: int(0–100), longing: int(0–100), resolve: int(0–100) }
```

### Panel
```python
{
  panel_number, visual_description, dialogue, direction_note,
  camera_angle, image_prompt, audio_mood, video_prompt,
  image_url, audio_url, video_url
}
```
- `image_url` — Imagen 3 PNG, all 4 panels
- `audio_url` — Lyria WAV ambient score, all 4 panels (empty string on failure)
- `video_url` — Veo 3.1 MP4 clip, panel 4 only (empty string on failure)

### PreviewRevisionResponse
```python
{
  scene_id, revision_note,
  current_beat_map, proposed_beat_map, beat_map_rationale,
  proposed_panels: [{ panel_number, change_type, reason, change_summary }]
}
```

---

## User Flow (State Machine)

```
IDLE
  └─(pitch scene)──► CLARIFYING   ← Gemini asks one question
                        └─(answer)──► GENERATING   ← Gemini + Imagen 3 x4 (parallel)
                                          └──────────► SCENE

SCENE
  └─(write note / quick cut)──► PREVIEWING_REVISION   ← Gemini proposes, NO images
                                       └──────────────► REVIEW_REVISION
                                                          ├─(cancel)──► SCENE
                                                          └─(approve panels)──► REVISING
                                                                                    └──► SCENE
```

**Key principle:** Image generation (Imagen 3) never fires until the human explicitly approves the specific panels in the HITL preview step.

---

## HITL Revision Loop (implemented)

1. Human types a note (e.g. "make it darker") or clicks a Quick Cut button
2. `POST /preview-revision` → Gemini returns **proposed beat map delta + per-panel rationale** (text only, fast, no Imagen calls)
3. `RevisionPreview.jsx` modal shows:
   - Old vs new beat map bars with numeric delta
   - Each proposed panel as a toggle row with `change_type` badge (`↻ revise` / `+ add element`), reason, and change summary
   - Human can uncheck any panel to exclude it
4. Human clicks "Apply N Panels →"
5. `POST /revise` with `approved_panels: [...]` → only those panels get new content + Imagen images
6. Untouched panels keep their original content and image URL unchanged

---

## Design System

All CSS lives in `src/index.css` using CSS custom properties:

| Variable             | Value         | Use                       |
|----------------------|---------------|---------------------------|
| `--bg-base`          | `#0d0d0d`     | Page background           |
| `--bg-panel`         | `#1a1a1a`     | Cards                     |
| `--gold`             | `#c9a84c`     | Primary accent / logo     |
| `--tension-color`    | `#e63946`     | Beat map tension bar      |
| `--longing-color`    | `#9b59b6`     | Beat map longing bar      |
| `--resolve-color`    | `#2ecc71`     | Beat map resolve bar      |
| `--font-mono`        | Courier New   | Labels, badges, panel IDs |

Film grain overlay is applied via a fixed `body::before` SVG noise filter (z-index 9999, pointer-events none).

---

## Authentication Model

### Gemini 2.5 Flash
Uses an **AI Studio API key** (`GEMINI_API_KEY`). Set this in `backend/.env`.
If left blank, the `google-genai` client falls back to Vertex AI ADC (same credentials as below).

### Vertex AI (Imagen 3, Firestore, Cloud Storage)
**Vertex AI does not use an API key.** It authenticates via **Google Cloud Application Default Credentials (ADC)**.

| Environment       | How to authenticate                                      |
|-------------------|----------------------------------------------------------|
| Local dev         | `gcloud auth application-default login` (simplest)      |
| Local dev (no gcloud) | Set `GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa.json` in `.env` |
| Cloud Run         | Attached service account — no key needed, automatic      |

**Required service account roles:**
- `Vertex AI User` — Imagen 3 image generation
- `Cloud Datastore User` — Firestore read/write
- `Storage Object Admin` — GCS upload + public URL

---

## Environment Variables

### Backend (`backend/.env`)
```
GEMINI_API_KEY=                        # AI Studio key for Gemini 2.5 Flash
GEMINI_MODEL=gemini-2.5-flash

# Required for Vertex AI (Imagen 3), Firestore, Cloud Storage
GOOGLE_CLOUD_PROJECT=
GOOGLE_CLOUD_REGION=us-central1

# Optional — path to service account JSON (if not using gcloud ADC)
GOOGLE_APPLICATION_CREDENTIALS=

FIRESTORE_COLLECTION=scenes
GCS_BUCKET_NAME=

# Production only — set on Cloud Run to your Firebase Hosting URLs
# Comma-separated. Leave unset locally (defaults to http://localhost:5173).
CORS_ORIGINS=https://<project>.web.app,https://<project>.firebaseapp.com
```

### Frontend
No `.env.local` file needed for normal dev or production.
- **Dev:** Vite proxy handles `/api/**` → `localhost:8080`.
- **Production:** Firebase Hosting rewrites handle `/api/**` → Cloud Run; `VITE_API_URL` stays empty.
- **Only set `VITE_API_URL`** if bypassing Firebase Hosting entirely (e.g. direct API testing against Cloud Run).

---

## GCS Bucket Setup (required before first deploy)

The backend constructs deterministic public URLs without calling `blob.make_public()`.
This requires **uniform bucket-level access** with a public IAM binding:

```bash
# Create the bucket
gsutil mb -p $PROJECT -l us-central1 gs://$BUCKET_NAME

# Enable uniform bucket-level access
gsutil uniformbucketlevelaccess set on gs://$BUCKET_NAME

# Make all objects publicly readable
gsutil iam ch allUsers:objectViewer gs://$BUCKET_NAME
```

Media files will then be accessible at:
- Images: `https://storage.googleapis.com/{BUCKET_NAME}/panels/{scene_id}/panel_{n}.png`
- Audio:  `https://storage.googleapis.com/{BUCKET_NAME}/audio/{scene_id}/panel_{n}.wav`
- Video:  `https://storage.googleapis.com/{BUCKET_NAME}/video/{scene_id}/panel_{n}.mp4`

---

## Local Development

```bash
# ── One-time: Google Cloud auth ───────────────────────────────────────────
# Option A — gcloud ADC (recommended, no JSON key needed)
gcloud auth application-default login

# Option B — service account JSON key (if gcloud is not installed)
# Set GOOGLE_APPLICATION_CREDENTIALS in backend/.env (see below)

# ── Backend ───────────────────────────────────────────────────────────────
cd backend

# IMPORTANT: .env.example has the template; python-dotenv loads .env (not .env.example)
cp .env.example .env      # ← this step is required; uvicorn will NOT read .env.example

pip install -r requirements.txt
uvicorn main:app --reload --port 8080

# ── Frontend (separate terminal) ──────────────────────────────────────────
cd frontend
npm install
npm run dev               # http://localhost:5173 — Vite proxies /api/** to :8080
# No .env.local needed for local dev.
```

---

## Deployment

### One-time setup
```bash
# Link Firebase project
firebase use --add   # select your GCP project

# Set up GCS bucket (see GCS Bucket Setup section above)
```

### Deploy backend (Cloud Run)
```bash
gcloud run deploy directors-lab-api \
  --source backend/ \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars "GEMINI_API_KEY=<key>,GOOGLE_CLOUD_PROJECT=<proj>,GCS_BUCKET_NAME=<bucket>,FIRESTORE_COLLECTION=scenes,CORS_ORIGINS=https://<project>.web.app"
```

The Cloud Run service name **must match** `serviceId` in `firebase.json` (`directors-lab-api`).

### Deploy frontend (Firebase Hosting)
```bash
cd frontend
npm run build            # no VITE_API_URL needed — uses relative URLs
cd ..
firebase deploy --only hosting
```

Firebase Hosting rewrites `/api/**` to Cloud Run automatically.
**No VITE_API_URL env var is needed.** Do not set it for production builds.

---

## Conventions

- **No new files unless necessary.** Prefer editing existing files.
- **Backend AI logic stays in `agent.py`.** Routes in `main.py` are thin wrappers.
- **All CSS in `src/index.css`.** No CSS modules, no Tailwind, no styled-components.
- **State machine lives entirely in `App.jsx`.** Components receive callbacks, never call the API directly.
- **All Gemini calls use `client.aio.models.generate_content()`** — never the sync variant. All calls have `asyncio.wait_for` timeouts.
- **All blocking I/O (Firestore, GCS, Imagen) runs in `loop.run_in_executor()`** — never blocks the async event loop.
- **`approved_panels` is always human-supplied.** The backend never silently decides which panels to regenerate after the preview step.
- Images are stored at `gs://{GCS_BUCKET_NAME}/panels/{scene_id}/panel_{n}.png` with deterministic public URLs.

---

## Deployment: No Local Docker Required

`gcloud run deploy --source backend/` uses **Google Cloud Build** to build and push the container image automatically — no local Docker installation needed. This is the Google-native path and is already what this project uses.

To use Cloud Build, the service account needs the `Cloud Build Editor` + `Artifact Registry Writer` roles (added automatically by `gcloud` if you run `gcloud services enable cloudbuild.googleapis.com`).

---

## Data Persistence Model

Every scene (prompt, clarifications, Gemini output, panel image URLs) is stored permanently in Firestore under the `scenes` collection with no TTL or cleanup.

**Current state:** All scenes persist indefinitely. Good for hackathon demos (users can share/reload a scene by `scene_id`). Not suitable for production without cleanup.

**To add a TTL:** Enable Firestore TTL policy on a `expires_at` field, then set it on write:
```python
"expires_at": datetime.utcnow() + timedelta(days=7)
```
Then configure the TTL policy in the Firebase console: Firestore → TTL → collection `scenes`, field `expires_at`.

**If you want to forget:** Just don't write to Firestore (remove the `save_scene` calls in `agent.py`). The `GET /api/scene/{id}` route would stop working, but the rest of the flow is stateless.

---

## Known Limitations / Future Work

- Voice input uses the browser Web Speech API (Chrome only). Could be upgraded to Gemini Live API for real-time streaming audio.
- No authentication — Firestore rules allow public reads. Lock down with Firebase Auth before production.
- Imagen 3 requires a Google Cloud project with the Vertex AI API and `imagen-3.0-generate-001` allowlisted.
- GCS bucket must have uniform bucket-level access and the service account must have `Storage Object Creator` role.
- The `GEMINI_MODEL` env var should be updated when newer Gemini 2.5 Flash preview IDs are released.

## Security Notes

- **Never commit real credentials to `.env.example`**. Fill in values in `backend/.env` (gitignored).
  The `.gitignore` pattern `*-[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]*.json`
  covers GCP Console service account download naming (`project-hexhash.json`).
- On Cloud Run, set env vars via `--set-env-vars` flag — no JSON key file needed (ADC is automatic).
- The `backend/.dockerignore` excludes `*.json` so no credential files can be baked into the image.
- `CORS_ORIGINS` must be set on Cloud Run for production (see Deployment section).
