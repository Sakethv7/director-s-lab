# Architecture

## System Overview

```
Browser (React 18)
  ↓  /api/** (Vite proxy dev / Firebase Hosting rewrite prod)
FastAPI (Cloud Run, port 8080)
  ├── Gemini 2.5 Flash  — scene writing, clarification, revision
  ├── Imagen 3          — storyboard frames (4 panels)
  ├── Lyria             — ambient WAV score per panel
  ├── Gemini TTS        — character dialogue (gender-matched voice)
  ├── Veo 2             — 8s cinematic clip → extended to 15s via ffmpeg tpad
  ├── Firestore         — scene persistence (scenes collection)
  └── Cloud Storage     — PNG / WAV / MP4 public URLs
```

## AI Models

| Capability | Model | Notes |
|---|---|---|
| Text generation | `gemini-2.5-flash` | Scene writing, HITL preview, revision |
| Image generation | `imagen-3.0-generate-001` | 4 storyboard frames per scene |
| Music | `lyria-002` | Ambient WAV, mood-matched |
| Voice TTS | `gemini-2.5-flash-preview-tts` | Charon ♂ / Aoede ♀ gender-matched |
| Video | `veo-2.0-generate-001` | 8s clip + ffmpeg freeze-extend to 15s |

## Data Flow

1. User pitches scene (text / voice / image)
2. `POST /api/scene/clarify` → Gemini asks one cinematic question
3. User answers → `POST /api/scene/generate`
4. Backend runs in parallel:
   - Gemini writes 4-beat arc (JSON)
   - Imagen 3 × 4 panels (parallel)
   - Lyria × 4 panels (parallel)
   - Gemini TTS × 4 panels
   - Veo 2 × 1 clip (panel 4)
   - ffmpeg merges video + ambient + TTS → 15s MP4
5. All media uploaded to GCS → deterministic public URLs
6. Scene saved to Firestore → returned to frontend

## Related Notes

- [[State Machine]]
- [[API Routes]]
