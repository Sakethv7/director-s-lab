# API Routes

All routes defined in `backend/main.py`. AI logic in `backend/agent.py`.

## Endpoints

### `GET /health`
Health check — returns `{ status: "ok" }`.

### `POST /api/scene/clarify`
**Input:** `{ scene_prompt, ref_image_b64?, ref_image_mime? }`
**Output:** `{ scene_id, question }`

Gemini asks one cinematic clarifying question. Optionally accepts a reference image (base64) for multimodal context.

### `POST /api/scene/generate`
**Input:** `{ scene_id, clarification, scene_prompt, ref_image_b64?, ref_image_mime? }`
**Output:** `SceneResponse`

Full parallel generation: Gemini text → Imagen 3 × 4 → Lyria × 4 → Gemini TTS × 4 → Veo 3.1 × 1 → ffmpeg merge.

### `POST /api/scene/{scene_id}/preview-revision`
**Input:** `{ revision_note }`
**Output:** `PreviewRevisionResponse`

Gemini proposes changes — **text only, no Imagen calls**. Used for the HITL preview step.

### `POST /api/scene/{scene_id}/revise`
**Input:** `{ revision_note, approved_panels: [1, 2, ...] }`
**Output:** `SceneResponse`

Re-generates only the approved panels with new Gemini content + Imagen images. Untouched panels keep their URLs.

### `GET /api/scene/{scene_id}`
**Output:** `SceneResponse`

Retrieve a previously generated scene from Firestore.

## Data Models

### SceneResponse
```json
{
  "scene_id": "uuid",
  "scene_prompt": "...",
  "clarifying_question": "...",
  "clarification": "...",
  "scene_summary": "...",
  "beat_map": { "tension": 0-100, "longing": 0-100, "resolve": 0-100 },
  "panels": [ Panel ],
  "created_at": "iso",
  "updated_at": "iso"
}
```

### Panel
```json
{
  "panel_number": 1,
  "visual_description": "...",
  "dialogue": "...",
  "direction_note": "...",
  "camera_angle": "...",
  "image_prompt": "...",
  "audio_mood": "...",
  "video_prompt": "...",
  "voice_gender": "male|female",
  "image_url": "https://storage.googleapis.com/...",
  "audio_url": "https://storage.googleapis.com/...",
  "video_url": "https://storage.googleapis.com/..."
}
```

## Related Notes

- [[Architecture]]
- [[State Machine]]
