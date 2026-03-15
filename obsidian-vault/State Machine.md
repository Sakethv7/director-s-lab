# State Machine

All state lives in `frontend/src/App.jsx`.

## States

```
IDLE
  └─(pitch scene)──► CLARIFYING
                        └─(answer)──► GENERATING
                                          └──► SCENE

SCENE
  └─(director note / quick cut)──► PREVIEWING_REVISION
                                         └──► REVIEW_REVISION
                                                ├─(cancel)──► SCENE
                                                └─(approve)──► REVISING
                                                                   └──► SCENE
  └─(Polish This Scene →)──► SELECTING
                                  └─(submit note)──► FINALIZING
                                                         └──► FINAL
```

## Key Principle

> Image generation (Imagen 3) **never fires** until the human explicitly approves the specific panels in the HITL preview step.

## State Descriptions

| State | Description |
|---|---|
| `idle` | Landing screen — pitch input |
| `clarifying` | Gemini asked one question, waiting for user answer |
| `generating` | Parallel AI generation in progress (Gemini + Imagen + Lyria + TTS + Veo) |
| `scene` | Full storyboard visible, revision tools active |
| `previewing_revision` | Fetching Gemini's revision proposal (text only, no Imagen) |
| `review_revision` | HITL overlay — user toggles which panels to approve |
| `revising` | Re-generating only the approved panels |
| `selecting` | User picked a beat for final polish |
| `finalizing` | Polish being applied |
| `final` | Final polished beat visible |

## Related Notes

- [[Architecture]]
- [[API Routes]]
