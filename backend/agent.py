"""
Director's Lab — Core AI Agent
Gemini 2.5 Flash (fully async) for scene generation.
Imagen 3 via Vertex AI for storyboard visuals.
Lyria via Vertex AI REST for per-panel ambient music.
Veo via Vertex AI long-running REST for climax panel video.
All blocking I/O runs in a thread-pool executor — never blocks the event loop.
"""

import os
import json
import uuid
import base64
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Union

from google import genai
from google.genai import types
import vertexai
from vertexai.preview.vision_models import ImageGenerationModel
from google.cloud import storage, firestore

from beat_map import BeatMap

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Client initialization
# ---------------------------------------------------------------------------

def _init_gemini() -> genai.Client:
    key = os.getenv("GEMINI_API_KEY")
    if key:
        return genai.Client(api_key=key)
    # Fall back to Vertex AI Application Default Credentials
    return genai.Client(
        vertexai=True,
        project=os.getenv("GOOGLE_CLOUD_PROJECT"),
        location=os.getenv("GOOGLE_CLOUD_REGION", "us-central1"),
    )


def _init_vertexai():
    vertexai.init(
        project=os.getenv("GOOGLE_CLOUD_PROJECT"),
        location=os.getenv("GOOGLE_CLOUD_REGION", "us-central1"),
    )


gemini_client: Optional[genai.Client] = None
gcs_client: Optional[storage.Client] = None
firestore_client: Optional[firestore.Client] = None

GEMINI_MODEL         = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_IMAGE_MODEL   = "gemini-2.0-flash-preview-image-generation"   # native interleaved
IMAGEN_MODEL         = "imagen-3.0-generate-001"                      # fallback
GCS_BUCKET           = os.getenv("GCS_BUCKET_NAME", "")
FIRESTORE_COLLECTION = os.getenv("FIRESTORE_COLLECTION", "scenes")
GEMINI_TIMEOUT_SECS  = float(os.getenv("GEMINI_TIMEOUT_SECS", "45"))   # under Firebase 60s proxy limit
IMAGE_TIMEOUT_SECS   = float(os.getenv("IMAGE_TIMEOUT_SECS",  "45"))   # Imagen 3 typically 5-15s
AUDIO_TIMEOUT_SECS   = float(os.getenv("AUDIO_TIMEOUT_SECS",  "90"))   # background only
VIDEO_TIMEOUT_SECS   = float(os.getenv("VIDEO_TIMEOUT_SECS",  "360"))  # background only


def initialize_clients():
    global gemini_client, gcs_client, firestore_client
    gemini_client    = _init_gemini()
    _init_vertexai()
    gcs_client       = storage.Client()
    firestore_client = firestore.Client()
    logger.info("All clients initialized.")


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

CLARIFY_PROMPT = """\
You are a visionary film director. A writer just pitched you this scene:

"{scene_prompt}"

Ask ONE sharp, insightful clarifying question about the emotional core or visual tone. \
Be terse, cinematic, specific. Max 20 words. No preamble — just the question.\
"""

SCENE_GENERATION_PROMPT = """\
You are a visionary film director. You receive a scene pitch and produce ONE cinematic output frame —
the single defining moment of the scene, rendered as text narration + a visual + a video clip.

ORIGINAL PITCH: {scene_prompt}
DIRECTOR'S CLARIFICATION Q: {clarifying_question}
WRITER'S ANSWER: {clarification}
{image_context}

First establish the character(s) with a brief appearance description, then define the KEY MOMENT of this scene.
Respond with ONLY valid JSON — no markdown fences, no commentary:

{{
  "scene_summary": "2–3 sentence cinematic synopsis of the full scene arc",
  "beat_map": {{
    "tension":  <int 0–100>,
    "longing":  <int 0–100>,
    "resolve":  <int 0–100>
  }},
  "character_sheet": [
    {{
      "name": "CHARACTER NAME",
      "appearance": "Precise, repeatable visual description — hair, eyes, clothing, distinguishing features"
    }}
  ],
  "panels": [
    {{
      "panel_number": 1,
      "visual_description": "3–4 sentence description of EXACTLY what we see in the key frame — setting, character pose, lighting, atmosphere",
      "dialogue": "The character's most important line in this moment, or [SILENCE]",
      "direction_note": "One sentence — precise performance note for the actor",
      "camera_angle": "Specific shot (e.g. 'Extreme close-up, Dutch tilt, slow rack focus to background')",
      "image_prompt": "Photorealistic storyboard prompt embedding exact character appearance — cinematic lighting, 16:9, film grain, anamorphic lens",
      "audio_mood": "5–10 words describing the ambient musical feel (e.g. 'Low cello drones, rising dissonance, held breath')",
      "video_prompt": "15–20 word motion description for a 15-second Veo clip (e.g. 'Slow push-in on her face, hands trembling, wind stirs her hair, she turns to face camera')",
      "voice_gender": "male or female — must match the speaking character from character_sheet"
    }}
  ]
}}

Requirements:
- Exactly 1 panel — the defining emotional climax of the scene
- image_prompt MUST embed the character appearance from character_sheet verbatim for visual consistency
- video_prompt MUST embed the character appearance too — Veo needs it to stay consistent
- Beat map reflects the emotional peak of this moment (tension should be high at climax)
- audio_mood will be used for a Lyria ambient score — make it evocative
- video_prompt will be voiced by the character (TTS) — dialogue must be speakable, not stage direction
"""

PREVIEW_REVISION_PROMPT = """\
You are a film director analyzing how a storyboard should change.

SCENE SUMMARY: {scene_summary}
CURRENT BEAT MAP: tension={tension}, longing={longing}, resolve={resolve}
PANEL SUMMARIES:
{panels_summary}
DIRECTOR'S REVISION NOTE: "{revision_note}"

Propose the beat map update and which panels need to change — WITHOUT writing new panel content yet.
This is a PREVIEW for the human director to approve before any images are generated.

Respond with ONLY valid JSON:

{{
  "proposed_beat_map": {{
    "tension": <int 0–100>,
    "longing": <int 0–100>,
    "resolve": <int 0–100>
  }},
  "beat_map_rationale": "One sentence — why these scores change",
  "proposed_panels": [
    {{
      "panel_number": <int>,
      "change_type": "revise" | "add_element",
      "reason": "Why this panel needs to change",
      "change_summary": "Concrete description of what will change"
    }}
  ]
}}

Rules:
- Only include panels that genuinely need to change for this revision
- change_type is "add_element" when adding something new; "revise" when modifying existing content
"""


FINALIZE_PROMPT = """You are a film director applying a final polish note to one specific scene beat.

CHARACTER SHEET: {character_sheet}
SCENE SUMMARY: {scene_summary}
BEAT MAP: tension={tension}, longing={longing}, resolve={resolve}

CURRENT BEAT (Panel {suite_num}):
  Visual: {visual_description}
  Dialogue: {dialogue}
  Direction: {direction_note}
  Camera: {camera_angle}
  Current image_prompt: {image_prompt}
  Current audio_mood: {audio_mood}
  Current video_prompt: {video_prompt}

DIRECTOR'S FINAL POLISH NOTE: "{polish_note}"

Apply the polish note as a subtle refinement. Keep character consistency.
Respond with ONLY valid JSON — no markdown, no commentary:

{{
  "visual_description": "...",
  "dialogue": "...",
  "direction_note": "...",
  "camera_angle": "...",
  "image_prompt": "Photorealistic Imagen prompt — MUST embed character appearance from CHARACTER SHEET inline",
  "audio_mood": "...",
  "video_prompt": "Motion description for Veo — MUST embed character appearance inline",
  "voice_gender": "male or female — matches the speaking character"
}}
"""

REVISION_PROMPT = """\
You are revising a cinematic storyboard based on a director's note.

SCENE SUMMARY: {scene_summary}
CURRENT BEAT MAP: tension={tension}, longing={longing}, resolve={resolve}
CURRENT PANELS (JSON): {panels_json}
DIRECTOR'S REVISION NOTE: "{revision_note}"
PANELS TO REVISE (human-approved): {approved_panels}

Revise ONLY the approved panels listed above. Update the beat map to match.
Respond with ONLY valid JSON:

{{
  "beat_map": {{
    "tension": <int 0–100>,
    "longing": <int 0–100>,
    "resolve": <int 0–100>
  }},
  "revised_panels": [
    {{
      "panel_number": <int>,
      "visual_description": "...",
      "dialogue": "...",
      "direction_note": "...",
      "camera_angle": "...",
      "image_prompt": "...",
      "audio_mood": "...",
      "video_prompt": "...",
      "voice_gender": "male or female — matches the speaking character"
    }}
  ]
}}
"""


# ---------------------------------------------------------------------------
# Helpers — all async, non-blocking
# ---------------------------------------------------------------------------

def _parse_json_response(text: str) -> dict:
    """
    Strip optional markdown fences and parse JSON from model output.

    Handles all real-world Gemini output variants:
      • Raw JSON                 {"key": "val"}
      • ```json\\n{...}\\n```    (with language tag)
      • ```\\n{...}\\n```        (no language tag)
      • Trailing prose after the closing fence (Gemini sometimes adds commentary)
    """
    text = text.strip()
    if text.startswith("```"):
        # Drop the opening fence line (e.g. "```json" or "```")
        first_newline = text.find("\n")
        if first_newline == -1:
            raise ValueError("Fenced block contains no content")
        text = text[first_newline + 1:]
        # Drop everything from the LAST closing fence onward — handles trailing text
        last_fence = text.rfind("```")
        if last_fence != -1:
            text = text[:last_fence]
    return json.loads(text.strip())


async def _call_gemini_json(contents, temperature: float, max_tokens: int) -> str:
    """Async Gemini call returning JSON. contents can be str or list of Parts."""
    response = await asyncio.wait_for(
        gemini_client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
                response_mime_type="application/json",
            ),
        ),
        timeout=GEMINI_TIMEOUT_SECS,
    )
    return response.text


async def _call_gemini_text(contents: str, temperature: float, max_tokens: int) -> str:
    """Async Gemini call returning plain text (e.g. clarifying question).
    gemini-2.5-flash uses thinking tokens internally — we pass a generous
    max_output_tokens so the model has room to both think and respond."""
    response = await asyncio.wait_for(
        gemini_client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
        ),
        timeout=GEMINI_TIMEOUT_SECS,
    )
    return response.text.strip()


async def _no_media() -> str:
    """Placeholder coroutine for panels that don't get video."""
    return ""


async def _generate_image_gemini_native(image_prompt: str, scene_id: str, panel_num: int) -> str:
    """
    Generate a panel image using Gemini 2.0 Flash native image generation
    (interleaved output model). Returns GCS public URL, or empty string on failure.
    """
    loop = asyncio.get_running_loop()
    try:
        response = await asyncio.wait_for(
            gemini_client.aio.models.generate_content(
                model=GEMINI_IMAGE_MODEL,
                contents=f"Generate a cinematic, photorealistic 16:9 storyboard frame. {image_prompt}",
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    temperature=0.9,
                ),
            ),
            timeout=IMAGE_TIMEOUT_SECS,
        )

        # Extract image bytes from the first IMAGE part
        for part in (response.candidates or [{}])[0].content.parts:
            inline = getattr(part, "inline_data", None)
            if inline and getattr(inline, "data", None):
                image_bytes = inline.data
                mime        = getattr(inline, "mime_type", "image/png")
                ext         = "jpg" if "jpeg" in mime else "png"

                def _upload():
                    blob_name = f"panels/{scene_id}/panel_{panel_num}.{ext}"
                    blob = gcs_client.bucket(GCS_BUCKET).blob(blob_name)
                    blob.upload_from_string(image_bytes, content_type=mime)
                    return f"https://storage.googleapis.com/{GCS_BUCKET}/{blob_name}"

                return await loop.run_in_executor(None, _upload)

        raise ValueError("Gemini image model returned no inline image data")

    except Exception as exc:
        logger.warning(
            "Gemini native image failed for panel %s (%s) — falling back to Imagen 3",
            panel_num, exc,
        )
        return ""  # caller will fall back to Imagen 3


async def _generate_image(image_prompt: str, scene_id: str, panel_num: int, delay: float = 0) -> str:
    """
    Generate one panel image. Tries Gemini 2.0 Flash native image generation first
    (true interleaved output), falls back to Imagen 3 if unavailable.
    Runs GCS upload in a thread-pool executor.
    """
    loop = asyncio.get_running_loop()

    def _gen_and_upload() -> str:
        model  = ImageGenerationModel.from_pretrained(IMAGEN_MODEL)
        result = model.generate_images(
            prompt=image_prompt,
            number_of_images=1,
            aspect_ratio="16:9",
            safety_filter_level="block_some",
            person_generation="allow_adult",
        )
        if not result.images:
            raise ValueError("Imagen returned no images")

        image_bytes = result.images[0]._image_bytes
        blob_name   = f"panels/{scene_id}/panel_{panel_num}.png"
        blob        = gcs_client.bucket(GCS_BUCKET).blob(blob_name)
        blob.upload_from_string(image_bytes, content_type="image/png")

        # Deterministic public URL — works when bucket has allUsers:objectViewer IAM
        return f"https://storage.googleapis.com/{GCS_BUCKET}/{blob_name}"

    if delay:
        await asyncio.sleep(delay)

    # Try Gemini native interleaved image generation first
    native_url = await _generate_image_gemini_native(image_prompt, scene_id, panel_num)
    if native_url:
        return native_url

    # Fallback: Imagen 3
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, _gen_and_upload),
            timeout=IMAGE_TIMEOUT_SECS,
        )
    except Exception as exc:
        logger.error("Image generation failed for panel %s: %s", panel_num, exc, exc_info=True)
        return f"https://placehold.co/1280x720/1a1a1a/c9a84c?text=Panel+{panel_num}"


async def _generate_audio_bytes(audio_mood: str, panel_num: int) -> bytes:
    """
    Generate ambient panel music with Lyria via Vertex AI REST API.
    Returns raw WAV bytes. Returns empty bytes on any error.
    """
    project  = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_REGION", "us-central1")
    loop     = asyncio.get_running_loop()

    def _gen() -> bytes:
        import google.auth
        import google.auth.transport.requests
        import httpx

        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        creds.refresh(google.auth.transport.requests.Request())

        url = (
            f"https://{location}-aiplatform.googleapis.com/v1/"
            f"projects/{project}/locations/{location}/"
            f"publishers/google/models/lyria-002:predict"
        )
        payload = {
            "instances":  [{"prompt": audio_mood}],
            "parameters": {"sampleCount": 1},
        }
        resp = httpx.post(
            url,
            headers={"Authorization": f"Bearer {creds.token}"},
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()

        predictions = resp.json().get("predictions", [])
        if not predictions:
            raise ValueError("Lyria returned no predictions")

        return base64.b64decode(predictions[0]["bytesBase64Encoded"])

    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, _gen),
            timeout=AUDIO_TIMEOUT_SECS,
        )
    except Exception as exc:
        logger.warning("Audio generation failed for panel %s: %s", panel_num, exc)
        return b""  # graceful fallback


async def _generate_video_bytes(video_prompt: str, panel_num: int, delay: float = 0) -> bytes:
    """
    Generate a short video clip with Veo 3.1 via Vertex AI long-running REST API.
    Returns raw MP4 bytes. Falls back to empty bytes on any error.
    """
    import time as _time

    project  = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_REGION", "us-central1")
    loop     = asyncio.get_running_loop()

    def _gen() -> bytes:
        import google.auth
        import google.auth.transport.requests
        import httpx

        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        req_adapter = google.auth.transport.requests.Request()
        creds.refresh(req_adapter)

        def _headers():
            if not creds.valid:
                creds.refresh(req_adapter)
            return {
                "Authorization": f"Bearer {creds.token}",
                "Content-Type":  "application/json",
            }

        # 1 — Submit long-running operation
        predict_url = (
            f"https://{location}-aiplatform.googleapis.com/v1/"
            f"projects/{project}/locations/{location}/"
            f"publishers/google/models/veo-3.1-fast-generate-preview:predictLongRunning"
        )
        payload = {
            "instances":  [{"prompt": video_prompt}],
            "parameters": {
                "aspectRatio":     "16:9",
                "sampleCount":     1,
                "durationSeconds": 8,
            },
        }
        start_resp = httpx.post(
            predict_url, headers=_headers(), json=payload, timeout=30
        )
        start_resp.raise_for_status()
        operation_name = start_resp.json()["name"]

        # 2 — Poll until done using fetchPredictOperation (Veo-specific endpoint)
        fetch_url = (
            f"https://{location}-aiplatform.googleapis.com/v1/"
            f"projects/{project}/locations/{location}/"
            f"publishers/google/models/veo-3.1-fast-generate-preview:fetchPredictOperation"
        )
        op = {}
        for _ in range(60):
            _time.sleep(5)
            poll_resp = httpx.post(
                fetch_url,
                headers=_headers(),
                json={"operationName": operation_name},
                timeout=30,
            )
            poll_resp.raise_for_status()
            op = poll_resp.json()
            if op.get("done"):
                break
        else:
            raise TimeoutError("Veo operation did not complete in time")

        if "error" in op:
            raise ValueError(f"Veo returned error: {op['error']}")

        # 3 — Extract video bytes (response uses "videos" not "predictions")
        videos = op.get("response", {}).get("videos", [])
        if not videos:
            raise ValueError("Veo returned no videos")

        return base64.b64decode(videos[0]["bytesBase64Encoded"])

    try:
        if delay:
            await asyncio.sleep(delay)
        return await asyncio.wait_for(
            loop.run_in_executor(None, _gen),
            timeout=VIDEO_TIMEOUT_SECS,
        )
    except Exception as exc:
        logger.warning("Video generation failed for panel %s: %s", panel_num, exc)
        return b""  # graceful fallback


def _clean_dialogue(text: str) -> str:
    """Strip stage directions, character prefixes, and formatting from dialogue."""
    import re
    if not text:
        return ""
    # Strip [CHARACTER NAME, stage direction] prefix
    text = re.sub(r"^\[.*?\]\s*", "", text).strip()
    # Strip "CharacterName:" or "CharacterName (note):" prefix
    text = re.sub(r"^[A-Z][A-Za-z\s\-']+(\s*\(.*?\))?\s*:\s*", "", text).strip()
    # Strip inline parenthetical stage directions like (softly) or (pauses)
    text = re.sub(r"\(.*?\)", " ", text).strip()
    # Strip asterisk emphasis *word*
    text = re.sub(r"\*([^*]+)\*", r"\1", text).strip()
    # Strip wrapping quotation marks
    text = text.strip('"\'\u201c\u201d\u2018\u2019')
    # Collapse multiple spaces
    text = re.sub(r" {2,}", " ", text).strip()
    return text


async def _tts_bytes(dialogue: str, voice_gender: str = "female") -> bytes:
    """
    Convert character dialogue to speech using Gemini native TTS.
    Selects expressive cinematic voices by gender:
      female → Kore (expressive, emotive)
      male   → Fenrir (expressive, resonant)
    Returns WAV bytes (24 kHz LINEAR16 mono), or empty bytes on failure.
    """
    import io
    import wave

    clean = _clean_dialogue(dialogue)
    if not clean or clean.upper() == "[SILENCE]":
        return b""

    # Expressive cinematic voices — more natural than Charon/Aoede
    voice_name = "Fenrir" if voice_gender.lower() == "male" else "Kore"
    logger.info("TTS: voice=%s gender=%s for: %s", voice_name, voice_gender, clean[:60])

    # System instruction gives the TTS model acting direction
    acting_style = (
        "You are delivering a pivotal line of dialogue in a cinematic film. "
        "Speak with genuine emotional depth and natural human pacing — "
        "slight pauses, subtle breath, real weight behind each word. "
        "Never sound robotic or flat. Match the emotional register of the line."
    )

    try:
        response = await asyncio.wait_for(
            gemini_client.aio.models.generate_content(
                model="gemini-2.5-flash-preview-tts",
                contents=clean[:500],
                config=types.GenerateContentConfig(
                    system_instruction=acting_style,
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=voice_name,
                            )
                        )
                    ),
                ),
            ),
            timeout=30,
        )

        for part in (response.candidates or [{}])[0].content.parts:
            inline = getattr(part, "inline_data", None)
            if inline and getattr(inline, "data", None):
                pcm_bytes = inline.data
                # Wrap raw LINEAR16 PCM in a WAV container so ffmpeg can read it
                buf = io.BytesIO()
                with wave.open(buf, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)    # 16-bit
                    wf.setframerate(24000)
                    wf.writeframes(pcm_bytes)
                logger.info("Gemini TTS: %d PCM bytes synthesised", len(pcm_bytes))
                return buf.getvalue()

        raise ValueError("Gemini TTS returned no audio parts")

    except Exception as exc:
        logger.warning("Gemini TTS failed: %s", exc)
        return b""


async def _generate_video_with_audio(
    video_prompt: str,
    audio_mood: str,
    dialogue: str,
    scene_id: str,
    panel_num: int,
    delay: float = 0,
    voice_gender: str = "female",
) -> str:
    """
    Generate Veo video + Lyria ambient + TTS dialogue voice in parallel, then
    merge into one 15 s MP4 with ffmpeg:
      - Dialogue voice at full volume (gender-matched), starts 0.5 s in
      - Lyria ambient score at 40% volume underneath
      - Veo 8 s clip freeze-extended to 15 s
    Falls back gracefully at each layer — silent video if everything fails.
    """
    import subprocess
    import tempfile

    loop = asyncio.get_running_loop()

    if delay:
        await asyncio.sleep(delay)

    # All three generations in parallel — _tts_bytes is now a native coroutine
    video_bytes, ambient_bytes, voice_bytes = await asyncio.gather(
        _generate_video_bytes(video_prompt, panel_num),
        _generate_audio_bytes(audio_mood, panel_num),
        _tts_bytes(dialogue, voice_gender),
    )

    if not video_bytes:
        return ""  # video failed — nothing to show

    def _merge_and_upload() -> str:
        TARGET_SECS = 8    # Veo produces 8 s clips — no extension needed

        with tempfile.TemporaryDirectory() as tmpdir:
            video_path   = os.path.join(tmpdir, "video.mp4")
            ambient_path = os.path.join(tmpdir, "ambient.wav")
            voice_path   = os.path.join(tmpdir, "voice.wav")   # WAV from Gemini TTS
            merged_path  = os.path.join(tmpdir, "merged.mp4")

            with open(video_path, "wb") as f:
                f.write(video_bytes)

            final_bytes = video_bytes   # fallback: original silent 8 s clip
            has_ambient = bool(ambient_bytes)
            has_voice   = bool(voice_bytes)

            if has_ambient:
                with open(ambient_path, "wb") as f:
                    f.write(ambient_bytes)
            if has_voice:
                with open(voice_path, "wb") as f:
                    f.write(voice_bytes)

            # Run ffmpeg to mux audio into the 8 s Veo clip
            video_filter = "[0:v]copy[vout]"

            inputs       = ["-i", video_path]
            filter_parts = [video_filter]
            mix_labels   = []
            idx          = 1   # next input stream index

            if has_ambient:
                inputs += ["-i", ambient_path]
                # Lower ambient under dialogue so voice punches through clearly
                amb_vol = 0.18 if has_voice else 0.45
                filter_parts.append(f"[{idx}:a]volume={amb_vol}[amb]")
                mix_labels.append("[amb]")
                idx += 1

            if has_voice:
                inputs += ["-i", voice_path]
                # TTS voice: no delay (immediate impact), boosted volume
                filter_parts.append(f"[{idx}:a]volume=4.0[tts]")
                mix_labels.append("[tts]")

            if mix_labels:
                n = len(mix_labels)
                if n > 1:
                    filter_parts.append(
                        f"{''.join(mix_labels)}amix=inputs={n}:duration=longest:normalize=0[aout]"
                    )
                else:
                    filter_parts.append(f"{mix_labels[0]}anull[aout]")

                cmd = (
                    ["ffmpeg", "-y"]
                    + inputs
                    + [
                        "-filter_complex", ";".join(filter_parts),
                        "-map", "[vout]",
                        "-map", "[aout]",
                        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                        "-c:a", "aac", "-b:a", "128k",
                        "-t", str(TARGET_SECS),
                        "-movflags", "+faststart",
                        merged_path,
                    ]
                )
            else:
                # No audio — just extend video
                cmd = (
                    ["ffmpeg", "-y"]
                    + inputs
                    + [
                        "-filter_complex", video_filter,
                        "-map", "[vout]",
                        "-an",
                        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                        "-t", str(TARGET_SECS),
                        "-movflags", "+faststart",
                        merged_path,
                    ]
                )

            result = subprocess.run(cmd, capture_output=True, timeout=120)
            if result.returncode == 0:
                with open(merged_path, "rb") as f:
                    final_bytes = f.read()
                logger.info(
                    "Panel %s: %ds video merged (ambient=%s voice=%s)",
                    panel_num, TARGET_SECS, has_ambient, has_voice,
                )
            else:
                logger.warning(
                    "ffmpeg merge failed for panel %s: %s",
                    panel_num,
                    result.stderr.decode(errors="replace")[-600:],
                )

            blob_name = f"video/{scene_id}/panel_{panel_num}.mp4"
            blob = gcs_client.bucket(GCS_BUCKET).blob(blob_name)
            blob.upload_from_string(final_bytes, content_type="video/mp4")
            return f"https://storage.googleapis.com/{GCS_BUCKET}/{blob_name}"

    try:
        return await loop.run_in_executor(None, _merge_and_upload)
    except Exception as exc:
        logger.warning("Merge/upload failed for panel %s: %s", panel_num, exc)
        return ""


async def _save_scene(scene_id: str, data: dict) -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: firestore_client.collection(FIRESTORE_COLLECTION).document(scene_id).set(data),
    )


async def _load_scene(scene_id: str) -> Optional[dict]:
    loop = asyncio.get_running_loop()
    def _do():
        doc = firestore_client.collection(FIRESTORE_COLLECTION).document(scene_id).get()
        return doc.to_dict() if doc.exists else None
    return await loop.run_in_executor(None, _do)


async def _update_scene(scene_id: str, updates: dict) -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: firestore_client.collection(FIRESTORE_COLLECTION).document(scene_id).update(updates),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def ask_clarifying_question(scene_prompt: str) -> dict:
    """Step 1 — returns {"scene_id": str, "question": str}."""
    question = await _call_gemini_text(
        CLARIFY_PROMPT.format(scene_prompt=scene_prompt),
        temperature=0.8,
        max_tokens=1024,
    )
    return {"scene_id": str(uuid.uuid4()), "question": question}


async def generate_scene(
    scene_id: str,
    scene_prompt: str,
    clarifying_question: str,
    clarification: str,
    reference_image: Optional[str] = None,
    reference_image_mime: str = "image/jpeg",
) -> dict:
    """
    Step 2 — generate single-frame scene: beat map + 1 panel (the key moment).
    Parallel: 1 × Gemini/Imagen image  +  1 × Veo+Lyria+TTS merged video.
    reference_image: base64-encoded image for multimodal visual context.
    """
    image_context = (
        "\nVISUAL REFERENCE: A reference image has been provided above. "
        "Use its mood, colour palette, and visual style to shape the storyboard.\n"
        if reference_image else ""
    )

    prompt_text = SCENE_GENERATION_PROMPT.format(
        scene_prompt=scene_prompt,
        clarifying_question=clarifying_question,
        clarification=clarification,
        image_context=image_context,
    )

    # Build multimodal content if a reference image was supplied
    if reference_image:
        contents = [
            types.Part(
                inline_data=types.Blob(
                    data=base64.b64decode(reference_image),
                    mime_type=reference_image_mime,
                )
            ),
            types.Part(text=prompt_text),
        ]
    else:
        contents = prompt_text

    raw_text = await _call_gemini_json(contents, temperature=0.9, max_tokens=4096)
    raw        = _parse_json_response(raw_text)
    beat_map   = BeatMap.from_dict(raw["beat_map"])
    panels_raw = raw.get("panels", [])

    # Single panel — generate image fast; video runs as background task
    p = panels_raw[0]
    image_url = await _generate_image(p["image_prompt"], scene_id, p["panel_number"])

    panels = [
        {
            **p,
            "image_url": image_url,
            "audio_url": "",   # audio is baked into the video
            "video_url": "",   # filled in by generate_video_for_scene background task
        }
        for p in panels_raw
    ]

    scene_data = {
        "scene_id":            scene_id,
        "scene_prompt":        scene_prompt,
        "clarifying_question": clarifying_question,
        "clarification":       clarification,
        "scene_summary":       raw.get("scene_summary", ""),
        "beat_map":            beat_map.to_dict(),
        "panels":              panels,
        "video_status":        "pending",
        "created_at":          datetime.now(timezone.utc).isoformat(),
        "updated_at":          datetime.now(timezone.utc).isoformat(),
    }
    await _save_scene(scene_id, scene_data)
    return scene_data


async def generate_video_for_scene(scene_id: str) -> None:
    """Background task: run Veo + merge and update Firestore when done."""
    try:
        scene_data = await _load_scene(scene_id)
        if not scene_data:
            logger.warning("generate_video_for_scene: scene %s not found", scene_id)
            return
        p = scene_data["panels"][0]
        video_url = await _generate_video_with_audio(
            p.get("video_prompt", p["image_prompt"]),
            p.get("audio_mood", "cinematic ambient score"),
            p.get("dialogue", ""),
            scene_id,
            p["panel_number"],
            voice_gender=p.get("voice_gender", "female"),
        )
        panels = scene_data["panels"]
        panels[0]["video_url"] = video_url or ""
        await _update_scene(scene_id, {
            "panels":       panels,
            "video_status": "ready" if video_url else "failed",
            "updated_at":   datetime.now(timezone.utc).isoformat(),
        })
        logger.info("generate_video_for_scene: done for %s (url=%s)", scene_id, bool(video_url))
    except Exception as exc:
        logger.exception("generate_video_for_scene failed for %s: %s", scene_id, exc)
        try:
            await _update_scene(scene_id, {"video_status": "failed"})
        except Exception:
            pass


async def preview_revision(scene_id: str, revision_note: str) -> dict:
    """HITL step 1 — propose changes (text only, no Imagen/Lyria/Veo). Fast."""
    scene_data = await _load_scene(scene_id)
    if not scene_data:
        raise ValueError(f"Scene {scene_id} not found")

    beat           = scene_data["beat_map"]
    panels_summary = "\n".join(
        f"  Panel {p['panel_number']}: {p.get('visual_description', '')[:120]} | "
        f"Dialogue: {p.get('dialogue', '[SILENCE]')[:60]}"
        for p in scene_data["panels"]
    )

    raw_text = await _call_gemini_json(
        PREVIEW_REVISION_PROMPT.format(
            scene_summary=scene_data["scene_summary"],
            tension=beat["tension"],
            longing=beat["longing"],
            resolve=beat["resolve"],
            panels_summary=panels_summary,
            revision_note=revision_note,
        ),
        temperature=0.7,
        max_tokens=4096,
    )
    raw = _parse_json_response(raw_text)

    return {
        "scene_id":           scene_id,
        "revision_note":      revision_note,
        "current_beat_map":   beat,
        "proposed_beat_map":  raw.get("proposed_beat_map", beat),
        "beat_map_rationale": raw.get("beat_map_rationale", ""),
        "proposed_panels":    raw.get("proposed_panels", []),
    }


async def revise_scene(
    scene_id: str,
    revision_note: str,
    approved_panels: list[int],
    dialogue_overrides: dict | None = None,
    timestamps: dict | None = None,
) -> dict:
    """HITL step 2 — regenerate content + images + audio for human-approved panels only."""
    scene_data = await _load_scene(scene_id)
    if not scene_data:
        raise ValueError(f"Scene {scene_id} not found")

    beat        = scene_data["beat_map"]
    panels_json = json.dumps(
        [
            {k: v for k, v in p.items() if k not in ("image_url", "audio_url", "video_url")}
            for p in scene_data["panels"]
        ],
        indent=2,
    )

    # Enrich revision note with any user-edited dialogues
    enriched_note = revision_note
    if dialogue_overrides:
        overrides_str = "; ".join(
            f"Panel {k}: dialogue changed to '{v}'"
            for k, v in dialogue_overrides.items()
        )
        enriched_note = f"{revision_note} [Dialogue edits: {overrides_str}]"

    raw_text = await _call_gemini_json(
        REVISION_PROMPT.format(
            scene_summary=scene_data["scene_summary"],
            tension=beat["tension"],
            longing=beat["longing"],
            resolve=beat["resolve"],
            panels_json=panels_json,
            revision_note=enriched_note,
            approved_panels=approved_panels,
        ),
        temperature=0.85,
        max_tokens=8192,
    )
    raw = _parse_json_response(raw_text)

    new_beat_map       = BeatMap.from_dict(raw["beat_map"])
    revised_panels_raw = [
        p for p in raw.get("revised_panels", [])
        if p["panel_number"] in approved_panels  # safety guard
    ]

    # Regenerate image fast; video runs as background task
    image_tasks = [
        _generate_image(p["image_prompt"], scene_id, p["panel_number"])
        for p in revised_panels_raw
    ]
    image_urls = list(await asyncio.gather(*image_tasks))

    panel_to_image = {p["panel_number"]: url for p, url in zip(revised_panels_raw, image_urls)}
    panel_to_audio = {p["panel_number"]: ""  for p in revised_panels_raw}   # baked into video
    panel_to_video = {p["panel_number"]: ""  for p in revised_panels_raw}   # filled by background
    revised_by_num = {p["panel_number"]: p for p in revised_panels_raw}

    _dialogue_map = {int(k): v for k, v in (dialogue_overrides or {}).items()}

    updated_panels = []
    for panel in scene_data["panels"]:
        pn = panel["panel_number"]
        if pn in revised_by_num:
            updated_panels.append({
                **revised_by_num[pn],
                "image_url": panel_to_image.get(pn, panel.get("image_url", "")),
                "audio_url": panel_to_audio.get(pn, panel.get("audio_url", "")),
                "video_url": panel_to_video.get(pn, panel.get("video_url", "")),
            })
        else:
            # Apply dialogue-only override for untouched panels
            if pn in _dialogue_map:
                updated_panels.append({**panel, "dialogue": _dialogue_map[pn]})
            else:
                updated_panels.append(panel)

    updates = {
        "beat_map":           new_beat_map.to_dict(),
        "panels":             updated_panels,
        "affected_panels":    approved_panels,
        "last_revision_note": revision_note,
        "video_status":       "pending",
        "updated_at":         datetime.now(timezone.utc).isoformat(),
    }
    await _update_scene(scene_id, updates)
    return {**scene_data, **updates}


async def revise_video_for_scene(scene_id: str, revised_panel_nums: list, timestamps: dict = None) -> None:
    """Background task: regenerate Veo video for revised panels and update Firestore."""
    try:
        scene_data = await _load_scene(scene_id)
        if not scene_data:
            return

        def _video_prompt_with_ts(p):
            base = p.get("video_prompt", p["image_prompt"])
            ts = (timestamps or {}).get(p["panel_number"])
            if ts is not None:
                m, s = divmod(int(ts), 60)
                base = f"{base} [Focus on the moment at approximately {m}m{s:02d}s of the previous clip.]"
            return base

        panels_to_regen = [p for p in scene_data["panels"] if p["panel_number"] in revised_panel_nums]
        av_tasks = [
            _generate_video_with_audio(
                _video_prompt_with_ts(p),
                p.get("audio_mood", "cinematic ambient score"),
                p.get("dialogue", ""),
                scene_id,
                p["panel_number"],
                delay=i * 8,
                voice_gender=p.get("voice_gender", "female"),
            )
            for i, p in enumerate(panels_to_regen)
        ]
        video_urls = list(await asyncio.gather(*av_tasks))
        panel_to_video = {p["panel_number"]: url for p, url in zip(panels_to_regen, video_urls)}

        updated_panels = [
            {**p, "video_url": panel_to_video[p["panel_number"]]} if p["panel_number"] in panel_to_video else p
            for p in scene_data["panels"]
        ]
        await _update_scene(scene_id, {
            "panels":       updated_panels,
            "video_status": "ready",
            "updated_at":   datetime.now(timezone.utc).isoformat(),
        })
        logger.info("revise_video_for_scene: done for %s panels=%s", scene_id, revised_panel_nums)
    except Exception as exc:
        logger.exception("revise_video_for_scene failed for %s: %s", scene_id, exc)
        try:
            await _update_scene(scene_id, {"video_status": "failed"})
        except Exception:
            pass


async def get_scene(scene_id: str) -> Optional[dict]:
    return await _load_scene(scene_id)

async def finalize_scene(scene_id: str, suite_num: int, polish_note: str) -> dict:
    """Apply a final polish note to one specific panel/beat and regenerate its media."""
    scene_data = await _load_scene(scene_id)
    if not scene_data:
        raise ValueError(f"Scene {scene_id} not found")

    panel = next((p for p in scene_data["panels"] if p["panel_number"] == suite_num), None)
    if not panel:
        raise ValueError(f"Panel {suite_num} not found in scene {scene_id}")

    beat            = scene_data["beat_map"]
    character_sheet = scene_data.get("character_sheet", [])
    cs_str          = json.dumps(character_sheet, indent=2) if character_sheet else "None specified"

    raw_text = await _call_gemini_json(
        FINALIZE_PROMPT.format(
            character_sheet=cs_str,
            scene_summary=scene_data["scene_summary"],
            tension=beat["tension"],
            longing=beat["longing"],
            resolve=beat["resolve"],
            suite_num=suite_num,
            visual_description=panel.get("visual_description", ""),
            dialogue=panel.get("dialogue", ""),
            direction_note=panel.get("direction_note", ""),
            camera_angle=panel.get("camera_angle", ""),
            image_prompt=panel.get("image_prompt", ""),
            audio_mood=panel.get("audio_mood", ""),
            video_prompt=panel.get("video_prompt", ""),
            polish_note=polish_note,
        ),
        temperature=0.75,
        max_tokens=2048,
    )
    refined = _parse_json_response(raw_text)

    # Merge refined fields back into panel
    polished_panel = {**panel, **refined}

    # Regenerate image fast; video runs as background task
    image_url = await _generate_image(polished_panel["image_prompt"], scene_id, suite_num)

    polished_panel["image_url"] = image_url
    polished_panel["audio_url"] = ""   # baked into video
    polished_panel["video_url"] = ""   # filled by background task

    # Update Firestore
    updated_panels = [
        polished_panel if p["panel_number"] == suite_num else p
        for p in scene_data["panels"]
    ]
    updates = {
        "panels":             updated_panels,
        "affected_panels":    [suite_num],
        "last_revision_note": f"FINAL POLISH: {polish_note}",
        "video_status":       "pending",
        "updated_at":         datetime.now(timezone.utc).isoformat(),
    }
    await _update_scene(scene_id, updates)
    return {**scene_data, **updates}


async def finalize_video_for_scene(scene_id: str, suite_num: int, polished_panel: dict) -> None:
    """Background task: generate Veo video for the finalized panel and update Firestore."""
    try:
        video_url = await _generate_video_with_audio(
            polished_panel.get("video_prompt", polished_panel["image_prompt"]),
            polished_panel.get("audio_mood", "cinematic ambient score"),
            polished_panel.get("dialogue", ""),
            scene_id,
            suite_num,
            voice_gender=polished_panel.get("voice_gender", "female"),
        )
        scene_data = await _load_scene(scene_id)
        if not scene_data:
            return
        updated_panels = [
            {**p, "video_url": video_url or ""} if p["panel_number"] == suite_num else p
            for p in scene_data["panels"]
        ]
        await _update_scene(scene_id, {
            "panels":       updated_panels,
            "video_status": "ready" if video_url else "failed",
            "updated_at":   datetime.now(timezone.utc).isoformat(),
        })
        logger.info("finalize_video_for_scene: done for %s panel=%s", scene_id, suite_num)
    except Exception as exc:
        logger.exception("finalize_video_for_scene failed for %s: %s", scene_id, exc)
        try:
            await _update_scene(scene_id, {"video_status": "failed"})
        except Exception:
            pass
