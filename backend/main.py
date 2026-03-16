"""
Director's Lab — FastAPI backend
"""

import os
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()  # no-op on Cloud Run where vars are injected; picks up .env locally

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CORS — restrict to known origins in production
# Set CORS_ORIGINS=https://your-project.web.app on Cloud Run.
# Leave unset locally (defaults to Vite dev server).
# With Firebase Hosting rewrites, browsers never send cross-origin requests
# so this is mainly a safety net for direct API access.
# ---------------------------------------------------------------------------

_raw_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173")
CORS_ORIGINS  = [o.strip() for o in _raw_origins.split(",") if o.strip()]


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    agent.initialize_clients()
    yield


app = FastAPI(title="Director's Lab API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type", "Authorization"],
)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ClarifyRequest(BaseModel):
    scene_prompt: str = Field(..., min_length=1, max_length=1000)


class ClarifyResponse(BaseModel):
    scene_id: str
    question: str


class GenerateRequest(BaseModel):
    scene_id:              str
    scene_prompt:          str = Field(..., min_length=1, max_length=1000)
    clarifying_question:   str = Field(..., min_length=1, max_length=500)
    clarification:         str = Field(..., min_length=1, max_length=500)
    # Optional multimodal reference image (base64-encoded)
    reference_image:       str | None = None
    reference_image_mime:  str = "image/jpeg"


class PreviewRevisionRequest(BaseModel):
    revision_note: str = Field(..., min_length=1, max_length=500)


class ProposedPanel(BaseModel):
    panel_number:   int
    change_type:    str   # "revise" | "add_element"
    reason:         str
    change_summary: str


class PreviewRevisionResponse(BaseModel):
    scene_id:             str
    revision_note:        str
    current_beat_map:     "BeatMapModel"
    proposed_beat_map:    "BeatMapModel"
    beat_map_rationale:   str
    proposed_panels:      list[ProposedPanel]


class ReviseRequest(BaseModel):
    revision_note:      str                     = Field(..., min_length=1, max_length=500)
    approved_panels:    list[int]               = Field(..., min_length=1)
    dialogue_overrides: dict[int, str] | None   = None
    timestamps:         dict[int, float] | None = None


class CharacterEntry(BaseModel):
    name:       str
    appearance: str

class Panel(BaseModel):
    panel_number:       int
    visual_description: str
    dialogue:           str
    direction_note:     str
    camera_angle:       str
    image_prompt:       str
    audio_mood:         str | None = None
    video_prompt:       str | None = None
    image_url:          str | None = None
    audio_url:          str | None = None
    video_url:          str | None = None


class BeatMapModel(BaseModel):
    tension: int
    longing: int
    resolve: int


class SceneResponse(BaseModel):
    scene_id:            str
    scene_prompt:        str
    clarifying_question: str
    clarification:       str
    scene_summary:       str
    beat_map:            BeatMapModel
    character_sheet:     list[CharacterEntry] = []
    panels:              list[Panel]
    created_at:          str
    updated_at:          str
    affected_panels:     list[int] = []
    last_revision_note:  str = ""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "service": "directors-lab"}


@app.post("/api/scene/clarify", response_model=ClarifyResponse)
async def clarify(req: ClarifyRequest):
    """Step 1 — ask a clarifying question about the scene pitch."""
    try:
        return await agent.ask_clarifying_question(req.scene_prompt.strip())
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Gemini timed out. Please try again.")
    except Exception as exc:
        logger.exception("clarify failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/scene/generate", response_model=SceneResponse)
async def generate(req: GenerateRequest, background_tasks: BackgroundTasks):
    """Step 2 — generate scene fast (Gemini + Imagen), kick off Veo in background."""
    try:
        data = await agent.generate_scene(
            scene_id=req.scene_id,
            scene_prompt=req.scene_prompt.strip(),
            clarifying_question=req.clarifying_question.strip(),
            clarification=req.clarification.strip(),
            reference_image=req.reference_image,
            reference_image_mime=req.reference_image_mime,
        )
        background_tasks.add_task(agent.generate_video_for_scene, data["scene_id"])
        return data
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Generation timed out. Please try again.")
    except Exception as exc:
        logger.exception("generate failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/scene/{scene_id}/preview-revision", response_model=PreviewRevisionResponse)
async def preview_revision(scene_id: str, req: PreviewRevisionRequest):
    """HITL step 1 — agent proposes changes, no images generated."""
    try:
        return await agent.preview_revision(
            scene_id=scene_id,
            revision_note=req.revision_note.strip(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Preview timed out. Please try again.")
    except Exception as exc:
        logger.exception("preview_revision failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/scene/{scene_id}/revise", response_model=SceneResponse)
async def revise(scene_id: str, req: ReviseRequest, background_tasks: BackgroundTasks):
    """HITL step 2 — regenerates images fast, kicks off Veo in background."""
    try:
        data = await agent.revise_scene(
            scene_id=scene_id,
            revision_note=req.revision_note.strip(),
            approved_panels=req.approved_panels,
            dialogue_overrides=req.dialogue_overrides,
            timestamps=req.timestamps,
        )
        background_tasks.add_task(
            agent.revise_video_for_scene,
            scene_id,
            req.approved_panels,
            req.timestamps,
        )
        return data
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Revision timed out. Please try again.")
    except Exception as exc:
        logger.exception("revise failed")
        raise HTTPException(status_code=500, detail=str(exc))


class FinalizeRequest(BaseModel):
    suite_num:   int   = Field(..., ge=1, le=4)
    polish_note: str   = Field(..., min_length=1, max_length=500)


@app.post("/api/scene/{scene_id}/finalize", response_model=SceneResponse)
async def finalize(scene_id: str, req: FinalizeRequest, background_tasks: BackgroundTasks):
    """Pick & Finalize — regenerates image fast, kicks off Veo in background."""
    try:
        data = await agent.finalize_scene(
            scene_id=scene_id,
            suite_num=req.suite_num,
            polish_note=req.polish_note.strip(),
        )
        # Pass the polished panel from Firestore for the background video task
        polished_panel = next(
            (p for p in data["panels"] if p["panel_number"] == req.suite_num), None
        )
        if polished_panel:
            background_tasks.add_task(
                agent.finalize_video_for_scene,
                scene_id,
                req.suite_num,
                polished_panel,
            )
        return data
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Finalize timed out. Please try again.")
    except Exception as exc:
        logger.exception("finalize failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/scene/{scene_id}", response_model=SceneResponse)
async def get_scene(scene_id: str):
    """Retrieve a previously generated scene."""
    scene = await agent.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    return scene
