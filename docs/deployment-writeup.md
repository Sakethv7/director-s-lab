# Director's Lab — Deployment Writeup

**Project:** Director's Lab — Multimodal AI cinematic directing agent
**GCP Project:** `gemini-live-agent-challenge-26`
**Deployed by:** Adithya
**Date:** March 2026

---

## What the Project Does

Director's Lab is a full-stack AI web app where users pitch a film scene and the system generates a 4-panel storyboard using:
- **Gemini 2.5 Flash** — scene writing, clarification, revision logic
- **Imagen 3** — generates panel images
- **Lyria** — generates ambient audio per panel
- **Veo 2** — generates a video clip for the final panel
- **Firestore** — stores every generated scene permanently
- **Cloud Storage** — hosts the generated images, audio, and video files

The frontend is a React app. The backend is a Python FastAPI server.

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + Vite, hosted on Firebase Hosting |
| Backend | FastAPI (Python 3.12), deployed on Cloud Run |
| AI | Gemini 2.5 Flash, Imagen 3, Lyria, Veo 2 via Vertex AI |
| Database | Firestore (`scenes` collection) |
| File Storage | Google Cloud Storage (`gemini-hackathon-2026-bucket`) |

---

## Pre-Deployment Setup

### 1. Installed Required CLIs
- **Google Cloud SDK** — downloaded and installed the Windows installer from cloud.google.com. This provides `gcloud` and `gsutil`.
- **Firebase CLI** — already installed via `npm install -g firebase-tools` (v8.20.0).
- **Node.js** (v24) and **Python 3.12.2** (via pyenv) were already on the machine.

### 2. Authenticated
Logged into both CLIs with the Google account (`adityapraneeth@gmail.com`) that owns the GCP project:
```bash
gcloud auth login
gcloud config set project gemini-live-agent-challenge-26
gcloud auth application-default login
firebase login
```

### 3. Linked Firebase to the GCP Project
The GCP project wasn't linked to Firebase yet. This was done by:
1. Going to console.firebase.google.com
2. Clicking "Add project" and selecting the existing GCP project `gemini-live-agent-challenge-26`
3. Then running: `firebase use gemini-live-agent-challenge-26` from the project directory

### 4. Installed Local Dependencies
Frontend and backend packages were installed locally for development:
```bash
# Frontend
cd frontend && npm install

# Backend
python -m pip install -r backend/requirements.txt
```

---

## Environment Configuration

Copied `backend/.env.example` to `backend/.env` and filled in:

| Variable | Value |
|---|---|
| `GEMINI_API_KEY` | Left blank — falls back to Vertex AI ADC automatically |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to service account JSON key (downloaded from GCP Console) |
| `GOOGLE_CLOUD_PROJECT` | `gemini-live-agent-challenge-26` |
| `GOOGLE_CLOUD_REGION` | `us-central1` |
| `GCS_BUCKET_NAME` | `gemini-hackathon-2026-bucket` |
| `FIRESTORE_COLLECTION` | `scenes` |
| `CORS_ORIGINS` | Firebase Hosting URLs |

**Note on `GEMINI_API_KEY`:** The code checks if this is set and uses it for Gemini 2.5 Flash. If blank, it automatically falls back to Vertex AI Application Default Credentials using the service account — so no AI Studio key was needed.

---

## Cloud Storage Bucket Setup

The GCS bucket `gemini-hackathon-2026-bucket` was already created. We configured it for public access so generated media files are accessible via direct URLs:

```bash
gsutil uniformbucketlevelaccess set on gs://gemini-hackathon-2026-bucket
gsutil iam ch allUsers:objectViewer gs://gemini-hackathon-2026-bucket
```

This allows the backend to construct deterministic public URLs for images/audio/video without needing signed URLs.

---

## Backend Deployment (Cloud Run)

Deployed using `gcloud run deploy --source` which triggers Google Cloud Build to build the Docker container automatically — no local Docker installation needed.

An `env-vars.yaml` file was used instead of `--set-env-vars` to avoid shell escaping issues with the comma-separated CORS URLs:

```yaml
# backend/env-vars.yaml
GEMINI_API_KEY: ""
GEMINI_MODEL: "gemini-2.5-flash"
GOOGLE_CLOUD_PROJECT: "gemini-live-agent-challenge-26"
GOOGLE_CLOUD_REGION: "us-central1"
GCS_BUCKET_NAME: "gemini-hackathon-2026-bucket"
FIRESTORE_COLLECTION: "scenes"
CORS_ORIGINS: "https://gemini-live-agent-challenge-26.web.app,https://gemini-live-agent-challenge-26.firebaseapp.com"
```

Deploy command:
```bash
gcloud run deploy directors-lab-api \
  --source "d:\Data Engineering\director-s-lab\backend" \
  --region us-central1 \
  --allow-unauthenticated \
  --env-vars-file "d:\Data Engineering\director-s-lab\backend\env-vars.yaml"
```

**Result:** Backend live at `https://directors-lab-api-58357886766.us-central1.run.app`

---

## Frontend Deployment (Firebase Hosting)

```bash
cd frontend
npm run build
cd ..
firebase deploy --only hosting
```

Firebase Hosting automatically rewrites `/api/**` requests to the Cloud Run backend via the rewrite rules in `firebase.json` — no `VITE_API_URL` environment variable needed.

**Result:** Frontend live at `https://gemini-live-agent-challenge-26.web.app`

---

## Issues Encountered & How They Were Fixed

| Issue | Fix |
|---|---|
| `gsutil` not found in PowerShell | Switched to Google Cloud SDK Shell where all tools are on PATH |
| `firebase use` error — "must be run from a Firebase project directory" | Ran the command from the project root directory instead |
| Firebase `projects:list` showed no projects | The GCP project wasn't linked to Firebase — added it via Firebase Console |
| `--set-env-vars` failed due to comma in CORS URLs | Switched to `--env-vars-file` with a YAML file to avoid shell escaping issues |
| GCS bucket already existed | Not an error — bucket was pre-created, just needed public access configured |

---

## Service Account Roles Required

The service account attached to Cloud Run needs these IAM roles:
- `Vertex AI User` — for Imagen 3, Lyria, Veo 2
- `Cloud Datastore User` — for Firestore read/write
- `Storage Object Admin` — for GCS upload and public URL access

---

## Final URLs

| Service | URL |
|---|---|
| Frontend | https://gemini-live-agent-challenge-26.web.app |
| Backend (Cloud Run) | https://directors-lab-api-58357886766.us-central1.run.app |
| Health check | https://directors-lab-api-58357886766.us-central1.run.app/health |
