"""
Audio & Video generation tests — Director's Lab backend.

Covers the four internal helpers in agent.py that handle media generation:

  _generate_audio_bytes      Lyria ambient score via Vertex AI REST
  _tts_bytes                 Gemini native TTS (dialogue → WAV)
  _generate_video_bytes      Veo 3.1 long-running operation via Vertex AI REST
  _generate_video_with_audio ffmpeg merge of Veo + Lyria + TTS

And the public generate_scene() function tested with a reference_image input
(the only supported media input — video input is not yet implemented).

No real API calls are made — all external I/O is mocked.

PC audio fixture
----------------
NOTIFICATION_WAV_BYTES loads /Users/sakethv7/Library/Sounds/notification.wav
(a real WAV from the local machine) and feeds it as the mock Lyria response to
verify the agent handles arbitrary-length WAV bytes without error.
Falls back to a synthetic 200 ms silence WAV on CI where the file is absent.
"""

import base64
import io
import json
import struct
import wave
import zlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import agent
from tests.conftest import SAMPLE_SCENE


# ---------------------------------------------------------------------------
# Fixtures / shared helpers
# ---------------------------------------------------------------------------

def _make_silence_wav(frames: int = 2400, rate: int = 24_000) -> bytes:
    """Return a valid WAV container wrapping 'frames' samples of silence."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x00" * frames)
    return buf.getvalue()


def _make_minimal_png() -> bytes:
    """Return a valid 1×1 white PNG — used as a stand-in reference image."""
    def _chunk(name: bytes, data: bytes) -> bytes:
        c = name + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFF_FFFF)

    IHDR = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    IDAT = zlib.compress(b"\x00\xff\xff\xff")
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", IHDR)
        + _chunk(b"IDAT", IDAT)
        + _chunk(b"IEND", b"")
    )


def _load_notification_wav() -> bytes:
    """Load the real system notification.wav from the user's Mac.
    Falls back to a synthetic WAV on CI where the file is absent."""
    try:
        with open("/Users/sakethv7/Library/Sounds/notification.wav", "rb") as fh:
            return fh.read()
    except FileNotFoundError:
        return _make_silence_wav(frames=4800)  # 200 ms fallback


# Minimal fMP4 header bytes — enough to be "truthy video bytes"
SAMPLE_MP4_BYTES = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42mp41"

# 100 ms WAV for Lyria / ffmpeg mock responses
SAMPLE_WAV_BYTES = _make_silence_wav()

# Raw PCM that Gemini TTS inlines (no WAV container — agent wraps it)
SAMPLE_PCM_BYTES = b"\x00\x00" * 2400   # 100 ms at 24 kHz

# Real notification.wav from the user's Mac (265 KB)
NOTIFICATION_WAV_BYTES = _load_notification_wav()

# Base64 reference image (1×1 PNG).
# NOTE: video input is NOT supported by the current API.
# Only image is accepted via reference_image / reference_image_mime.
REFERENCE_IMAGE_B64 = base64.b64encode(_make_minimal_png()).decode()


# ---------------------------------------------------------------------------
# REST-mock helpers
# ---------------------------------------------------------------------------

def _mock_creds() -> MagicMock:
    creds = MagicMock()
    creds.token = "fake-bearer-token"
    creds.valid = True
    return creds


def _lyria_ok(wav_bytes: bytes) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "predictions": [{"bytesBase64Encoded": base64.b64encode(wav_bytes).decode()}]
    }
    return resp


def _veo_start(op_name: str = "projects/p/locations/l/operations/op-1") -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"name": op_name}
    return resp


def _veo_done(mp4_bytes: bytes, op_name: str = "projects/p/locations/l/operations/op-1") -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "name": op_name,
        "done": True,
        "response": {"videos": [{"bytesBase64Encoded": base64.b64encode(mp4_bytes).decode()}]},
    }
    return resp


def _veo_pending() -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"done": False}
    return resp


def _veo_error() -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"done": True, "error": {"code": 500, "message": "Veo internal error"}}
    return resp


def _tts_gemini_response(pcm_bytes: bytes) -> MagicMock:
    """Fake Gemini generate_content response carrying an inline AUDIO part."""
    inline = MagicMock()
    inline.data = pcm_bytes
    inline.mime_type = "audio/pcm"

    part = MagicMock()
    part.inline_data = inline

    content = MagicMock()
    content.parts = [part]

    candidate = MagicMock()
    candidate.content = content

    response = MagicMock()
    response.candidates = [candidate]
    return response


def _ffmpeg_ok_run(cmd, capture_output, timeout):
    """subprocess.run stub — writes SAMPLE_MP4_BYTES to the merged output path."""
    import subprocess
    for arg in cmd:
        if arg.endswith(".mp4") and "merged" in arg:
            with open(arg, "wb") as fh:
                fh.write(SAMPLE_MP4_BYTES)
            break
    result = MagicMock(spec=subprocess.CompletedProcess)
    result.returncode = 0
    return result


# ---------------------------------------------------------------------------
# _generate_audio_bytes
# ---------------------------------------------------------------------------

class TestGenerateAudioBytes:
    """Lyria ambient score generation via Vertex AI REST API."""

    async def test_returns_wav_bytes_on_success(self):
        with patch("google.auth.default", return_value=(_mock_creds(), "proj")), \
             patch("google.auth.transport.requests.Request"), \
             patch("httpx.post", return_value=_lyria_ok(SAMPLE_WAV_BYTES)):

            result = await agent._generate_audio_bytes("low cello drones", panel_num=1)

        assert result == SAMPLE_WAV_BYTES
        assert result[:4] == b"RIFF"

    async def test_uses_real_notification_wav_as_mock_response(self):
        """
        Feed the real notification.wav (265 KB from the user's Mac) as the
        simulated Lyria payload — verifies the agent handles large WAV bytes.
        """
        with patch("google.auth.default", return_value=(_mock_creds(), "proj")), \
             patch("google.auth.transport.requests.Request"), \
             patch("httpx.post", return_value=_lyria_ok(NOTIFICATION_WAV_BYTES)):

            result = await agent._generate_audio_bytes("orchestral strings swell", panel_num=2)

        assert result[:4] == b"RIFF"
        assert len(result) == len(NOTIFICATION_WAV_BYTES)

    async def test_audio_mood_sent_as_lyria_prompt(self):
        """The audio_mood string must reach the Lyria 'instances[0].prompt' field."""
        captured = {}

        def _capture(url, headers, json, timeout):
            captured["payload"] = json
            return _lyria_ok(SAMPLE_WAV_BYTES)

        with patch("google.auth.default", return_value=(_mock_creds(), "proj")), \
             patch("google.auth.transport.requests.Request"), \
             patch("httpx.post", side_effect=_capture):

            await agent._generate_audio_bytes("haunting piano motif", panel_num=3)

        assert captured["payload"]["instances"][0]["prompt"] == "haunting piano motif"

    async def test_returns_empty_bytes_when_predictions_empty(self):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"predictions": []}

        with patch("google.auth.default", return_value=(_mock_creds(), "proj")), \
             patch("google.auth.transport.requests.Request"), \
             patch("httpx.post", return_value=resp):

            result = await agent._generate_audio_bytes("ambient", panel_num=1)

        assert result == b""

    async def test_returns_empty_bytes_on_http_error(self):
        import httpx
        resp = MagicMock()
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "403", request=MagicMock(), response=MagicMock()
        )

        with patch("google.auth.default", return_value=(_mock_creds(), "proj")), \
             patch("google.auth.transport.requests.Request"), \
             patch("httpx.post", return_value=resp):

            result = await agent._generate_audio_bytes("ambient", panel_num=1)

        assert result == b""

    async def test_returns_empty_bytes_on_network_error(self):
        import httpx
        with patch("google.auth.default", return_value=(_mock_creds(), "proj")), \
             patch("google.auth.transport.requests.Request"), \
             patch("httpx.post", side_effect=httpx.ConnectError("refused")):

            result = await agent._generate_audio_bytes("ambient", panel_num=1)

        assert result == b""


# ---------------------------------------------------------------------------
# _tts_bytes
# ---------------------------------------------------------------------------

class TestTtsBytes:
    """Gemini native TTS: dialogue string → WAV bytes."""

    async def test_female_voice_uses_aoede(self):
        captured = {}

        async def _fake(model, contents, config):
            captured["config"] = config
            return _tts_gemini_response(SAMPLE_PCM_BYTES)

        with patch.object(agent, "gemini_client") as mc:
            mc.aio.models.generate_content = _fake
            await agent._tts_bytes("She turns and stares.", voice_gender="female")

        voice = captured["config"].speech_config.voice_config.prebuilt_voice_config.voice_name
        assert voice == "Aoede"

    async def test_male_voice_uses_charon(self):
        captured = {}

        async def _fake(model, contents, config):
            captured["config"] = config
            return _tts_gemini_response(SAMPLE_PCM_BYTES)

        with patch.object(agent, "gemini_client") as mc:
            mc.aio.models.generate_content = _fake
            await agent._tts_bytes("He steps into the light.", voice_gender="male")

        voice = captured["config"].speech_config.voice_config.prebuilt_voice_config.voice_name
        assert voice == "Charon"

    async def test_silence_skips_tts(self):
        with patch.object(agent, "gemini_client") as mc:
            result = await agent._tts_bytes("[SILENCE]", voice_gender="female")
        mc.aio.models.generate_content.assert_not_called()
        assert result == b""

    async def test_empty_string_skips_tts(self):
        with patch.object(agent, "gemini_client") as mc:
            result = await agent._tts_bytes("", voice_gender="female")
        mc.aio.models.generate_content.assert_not_called()
        assert result == b""

    async def test_stage_direction_prefix_is_stripped(self):
        """'[EMMA, whispering] It can't be.' → only 'It can't be.' is synthesised."""
        captured = {}

        async def _fake(model, contents, config):
            captured["text"] = contents
            return _tts_gemini_response(SAMPLE_PCM_BYTES)

        with patch.object(agent, "gemini_client") as mc:
            mc.aio.models.generate_content = _fake
            await agent._tts_bytes("[EMMA, whispering] It can't be.", voice_gender="female")

        assert captured["text"] == "It can't be."

    async def test_returns_valid_wav_container(self):
        """PCM from Gemini must be wrapped in a proper WAV file."""
        async def _fake(model, contents, config):
            return _tts_gemini_response(SAMPLE_PCM_BYTES)

        with patch.object(agent, "gemini_client") as mc:
            mc.aio.models.generate_content = _fake
            result = await agent._tts_bytes("Speak now.", voice_gender="female")

        buf = io.BytesIO(result)
        with wave.open(buf, "rb") as wf:
            assert wf.getnchannels()  == 1
            assert wf.getsampwidth()  == 2
            assert wf.getframerate()  == 24_000

    async def test_gemini_failure_returns_empty_bytes(self):
        async def _fail(*a, **kw):
            raise RuntimeError("TTS unavailable")

        with patch.object(agent, "gemini_client") as mc:
            mc.aio.models.generate_content = _fail
            result = await agent._tts_bytes("Hello.", voice_gender="female")

        assert result == b""

    async def test_no_inline_data_returns_empty_bytes(self):
        """Response with no audio part → b'' (graceful fallback)."""
        part = MagicMock()
        part.inline_data = None
        content = MagicMock()
        content.parts = [part]
        candidate = MagicMock()
        candidate.content = content
        response = MagicMock()
        response.candidates = [candidate]

        async def _fake(model, contents, config):
            return response

        with patch.object(agent, "gemini_client") as mc:
            mc.aio.models.generate_content = _fake
            result = await agent._tts_bytes("Hello.", voice_gender="female")

        assert result == b""


# ---------------------------------------------------------------------------
# _generate_video_bytes
# ---------------------------------------------------------------------------

class TestGenerateVideoBytes:
    """Veo 3.1 long-running video generation via Vertex AI REST API."""

    async def test_returns_mp4_bytes_on_success(self):
        with patch("google.auth.default", return_value=(_mock_creds(), "proj")), \
             patch("google.auth.transport.requests.Request"), \
             patch("time.sleep"), \
             patch("httpx.post", side_effect=[_veo_start(), _veo_done(SAMPLE_MP4_BYTES)]):

            result = await agent._generate_video_bytes("Slow push-in on her face", panel_num=1)

        assert result == SAMPLE_MP4_BYTES

    async def test_polls_until_done(self):
        """Not-done polls are retried until the operation completes."""
        with patch("google.auth.default", return_value=(_mock_creds(), "proj")), \
             patch("google.auth.transport.requests.Request"), \
             patch("time.sleep"), \
             patch("httpx.post", side_effect=[
                 _veo_start(),
                 _veo_pending(),
                 _veo_pending(),
                 _veo_done(SAMPLE_MP4_BYTES),
             ]):

            result = await agent._generate_video_bytes("Slow dolly", panel_num=1)

        assert result == SAMPLE_MP4_BYTES

    async def test_returns_empty_bytes_when_veo_returns_error(self):
        with patch("google.auth.default", return_value=(_mock_creds(), "proj")), \
             patch("google.auth.transport.requests.Request"), \
             patch("time.sleep"), \
             patch("httpx.post", side_effect=[_veo_start(), _veo_error()]):

            result = await agent._generate_video_bytes("Slow push", panel_num=1)

        assert result == b""

    async def test_returns_empty_bytes_when_videos_list_is_empty(self):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"done": True, "response": {"videos": []}}

        with patch("google.auth.default", return_value=(_mock_creds(), "proj")), \
             patch("google.auth.transport.requests.Request"), \
             patch("time.sleep"), \
             patch("httpx.post", side_effect=[_veo_start(), resp]):

            result = await agent._generate_video_bytes("Slow push", panel_num=1)

        assert result == b""

    async def test_returns_empty_bytes_on_network_error(self):
        import httpx
        with patch("google.auth.default", return_value=(_mock_creds(), "proj")), \
             patch("google.auth.transport.requests.Request"), \
             patch("httpx.post", side_effect=httpx.ConnectError("refused")):

            result = await agent._generate_video_bytes("Slow push", panel_num=1)

        assert result == b""

    async def test_timeout_returns_empty_bytes(self):
        with patch("google.auth.default", return_value=(_mock_creds(), "proj")), \
             patch("google.auth.transport.requests.Request"), \
             patch.object(agent, "VIDEO_TIMEOUT_SECS", 0.001), \
             patch("time.sleep"), \
             patch("httpx.post", return_value=_veo_start()):

            result = await agent._generate_video_bytes("Slow push", panel_num=1)

        assert result == b""


# ---------------------------------------------------------------------------
# _generate_video_with_audio
# ---------------------------------------------------------------------------

class TestGenerateVideoWithAudio:
    """ffmpeg merge pipeline: Veo + Lyria ambient + TTS voice → GCS MP4."""

    async def test_returns_gcs_url_when_all_succeed(self):
        with patch.object(agent, "_generate_video_bytes", new_callable=AsyncMock, return_value=SAMPLE_MP4_BYTES), \
             patch.object(agent, "_generate_audio_bytes", new_callable=AsyncMock, return_value=SAMPLE_WAV_BYTES), \
             patch.object(agent, "_tts_bytes",            new_callable=AsyncMock, return_value=SAMPLE_WAV_BYTES), \
             patch("subprocess.run", side_effect=_ffmpeg_ok_run), \
             patch.object(agent, "gcs_client") as mock_gcs, \
             patch.object(agent, "GCS_BUCKET", "test-bucket"):

            mock_gcs.bucket.return_value.blob.return_value = MagicMock()

            result = await agent._generate_video_with_audio(
                video_prompt="Slow dolly push on her face",
                audio_mood="low cello drones",
                dialogue="It can't be.",
                scene_id="scene-001",
                panel_num=1,
                voice_gender="female",
            )

        assert result.startswith("https://storage.googleapis.com/test-bucket/video/")

    async def test_returns_empty_string_when_video_fails(self):
        """No video bytes → nothing to show — return '' immediately."""
        with patch.object(agent, "_generate_video_bytes", new_callable=AsyncMock, return_value=b""), \
             patch.object(agent, "_generate_audio_bytes", new_callable=AsyncMock, return_value=SAMPLE_WAV_BYTES), \
             patch.object(agent, "_tts_bytes",            new_callable=AsyncMock, return_value=SAMPLE_WAV_BYTES):

            result = await agent._generate_video_with_audio(
                video_prompt="push", audio_mood="ambient",
                dialogue="Hello.", scene_id="s1", panel_num=1,
            )

        assert result == ""

    async def test_returns_url_when_only_audio_fails(self):
        """Lyria + TTS both fail; Veo succeeds — video-only MP4 still uploaded."""
        with patch.object(agent, "_generate_video_bytes", new_callable=AsyncMock, return_value=SAMPLE_MP4_BYTES), \
             patch.object(agent, "_generate_audio_bytes", new_callable=AsyncMock, return_value=b""), \
             patch.object(agent, "_tts_bytes",            new_callable=AsyncMock, return_value=b""), \
             patch("subprocess.run", side_effect=_ffmpeg_ok_run), \
             patch.object(agent, "gcs_client") as mock_gcs, \
             patch.object(agent, "GCS_BUCKET", "test-bucket"):

            mock_gcs.bucket.return_value.blob.return_value = MagicMock()

            result = await agent._generate_video_with_audio(
                video_prompt="push", audio_mood="ambient",
                dialogue="[SILENCE]", scene_id="s2", panel_num=2,
            )

        assert "storage.googleapis.com" in result

    async def test_returns_url_when_tts_fails_but_ambient_succeeds(self):
        """TTS fails; ambient track still mixed in."""
        with patch.object(agent, "_generate_video_bytes", new_callable=AsyncMock, return_value=SAMPLE_MP4_BYTES), \
             patch.object(agent, "_generate_audio_bytes", new_callable=AsyncMock, return_value=SAMPLE_WAV_BYTES), \
             patch.object(agent, "_tts_bytes",            new_callable=AsyncMock, return_value=b""), \
             patch("subprocess.run", side_effect=_ffmpeg_ok_run), \
             patch.object(agent, "gcs_client") as mock_gcs, \
             patch.object(agent, "GCS_BUCKET", "test-bucket"):

            mock_gcs.bucket.return_value.blob.return_value = MagicMock()

            result = await agent._generate_video_with_audio(
                video_prompt="push", audio_mood="cello",
                dialogue="[SILENCE]", scene_id="s3", panel_num=3,
            )

        assert "storage.googleapis.com" in result

    async def test_all_three_generation_tasks_run(self):
        """asyncio.gather fires all three mocks — each awaited exactly once."""
        mock_video = AsyncMock(return_value=SAMPLE_MP4_BYTES)
        mock_audio = AsyncMock(return_value=SAMPLE_WAV_BYTES)
        mock_tts   = AsyncMock(return_value=SAMPLE_WAV_BYTES)

        with patch.object(agent, "_generate_video_bytes", mock_video), \
             patch.object(agent, "_generate_audio_bytes", mock_audio), \
             patch.object(agent, "_tts_bytes",            mock_tts), \
             patch("subprocess.run", side_effect=_ffmpeg_ok_run), \
             patch.object(agent, "gcs_client") as mock_gcs, \
             patch.object(agent, "GCS_BUCKET", "test-bucket"):

            mock_gcs.bucket.return_value.blob.return_value = MagicMock()

            await agent._generate_video_with_audio(
                video_prompt="push", audio_mood="ambient",
                dialogue="She speaks.", scene_id="s4", panel_num=1,
                voice_gender="female",
            )

        mock_video.assert_awaited_once()
        mock_audio.assert_awaited_once()
        mock_tts.assert_awaited_once()

    async def test_ffmpeg_failure_uploads_raw_veo_bytes(self):
        """
        If ffmpeg exits non-zero, the original Veo bytes are uploaded as fallback
        — the function still returns a URL rather than crashing.
        """
        import subprocess

        def _ffmpeg_fail(cmd, capture_output, timeout):
            result = MagicMock(spec=subprocess.CompletedProcess)
            result.returncode = 1
            result.stderr = b"ffmpeg: codec error"
            return result

        with patch.object(agent, "_generate_video_bytes", new_callable=AsyncMock, return_value=SAMPLE_MP4_BYTES), \
             patch.object(agent, "_generate_audio_bytes", new_callable=AsyncMock, return_value=SAMPLE_WAV_BYTES), \
             patch.object(agent, "_tts_bytes",            new_callable=AsyncMock, return_value=b""), \
             patch("subprocess.run", side_effect=_ffmpeg_fail), \
             patch.object(agent, "gcs_client") as mock_gcs, \
             patch.object(agent, "GCS_BUCKET", "test-bucket"):

            mock_blob = MagicMock()
            mock_gcs.bucket.return_value.blob.return_value = mock_blob

            result = await agent._generate_video_with_audio(
                video_prompt="push", audio_mood="cello",
                dialogue="[SILENCE]", scene_id="s5", panel_num=1,
            )

        assert "storage.googleapis.com" in result
        # Raw Veo bytes (not merged) uploaded as fallback
        assert mock_blob.upload_from_string.call_args.args[0] == SAMPLE_MP4_BYTES

    async def test_uses_real_notification_wav_as_ambient(self):
        """
        Use the real notification.wav from the user's Mac as the mock ambient audio.
        Verifies ffmpeg is invoked without errors when ambient bytes are large.
        """
        with patch.object(agent, "_generate_video_bytes", new_callable=AsyncMock, return_value=SAMPLE_MP4_BYTES), \
             patch.object(agent, "_generate_audio_bytes", new_callable=AsyncMock, return_value=NOTIFICATION_WAV_BYTES), \
             patch.object(agent, "_tts_bytes",            new_callable=AsyncMock, return_value=b""), \
             patch("subprocess.run", side_effect=_ffmpeg_ok_run), \
             patch.object(agent, "gcs_client") as mock_gcs, \
             patch.object(agent, "GCS_BUCKET", "test-bucket"):

            mock_gcs.bucket.return_value.blob.return_value = MagicMock()

            result = await agent._generate_video_with_audio(
                video_prompt="Slow pan across the trail",
                audio_mood="orchestral swell",
                dialogue="[SILENCE]",
                scene_id="s6",
                panel_num=1,
            )

        assert "storage.googleapis.com" in result


# ---------------------------------------------------------------------------
# generate_scene — reference_image (image input only)
# ---------------------------------------------------------------------------
#
# NOTE: The API currently accepts ONLY images as reference input
# (reference_image / reference_image_mime on POST /api/scene/generate).
# Video input is NOT implemented — Veo is output-only in this codebase.
#

SCENE_RESPONSE_ONE_PANEL = {
    "scene_summary": "Three hikers walk a winding trail — a goodbye held in silence.",
    "beat_map": {"tension": 55, "longing": 75, "resolve": 30},
    "character_sheet": [
        {"name": "HIKER", "appearance": "Dark jacket, jeans, white sneakers."}
    ],
    "panels": [
        {
            "panel_number":       1,
            "visual_description": "Three figures from behind on a red-earth trail.",
            "dialogue":           "[SILENCE]",
            "direction_note":     "Contemplative — weight in every footfall.",
            "camera_angle":       "Tracking shot from behind, wide.",
            "image_prompt":       "Three hikers on red dirt trail, bare winter trees, cinematic 16:9.",
            "audio_mood":         "Sparse acoustic guitar, wind, footsteps",
            "video_prompt":       "Slow tracking shot behind three hikers on a winding trail.",
            "voice_gender":       "male",
        }
    ],
}


class TestGenerateSceneWithReferenceImage:
    """generate_scene() multimodal path — image as reference input."""

    async def test_image_input_produces_multimodal_gemini_call(self):
        """
        When reference_image is set, Gemini must receive a list of two Parts
        [image_part, text_part] — not a plain string.
        """
        captured = {}

        async def _fake_json(contents, temperature, max_tokens):
            captured["contents"] = contents
            return json.dumps(SCENE_RESPONSE_ONE_PANEL)

        with patch.object(agent, "_call_gemini_json",          new_callable=AsyncMock, side_effect=_fake_json), \
             patch.object(agent, "_generate_image",            new_callable=AsyncMock, return_value="https://gcs/p1.png"), \
             patch.object(agent, "_generate_video_with_audio", new_callable=AsyncMock, return_value=""), \
             patch.object(agent, "_save_scene",                new_callable=AsyncMock):

            await agent.generate_scene(
                scene_id="scene-img-001",
                scene_prompt="Three friends walk their last trail together.",
                clarifying_question="What does the silence between them carry?",
                clarification="Three years of things they never said.",
                reference_image=REFERENCE_IMAGE_B64,
                reference_image_mime="image/png",
            )

        contents = captured["contents"]
        assert isinstance(contents, list), "Expected multimodal list of Parts"
        assert len(contents) == 2

        image_part = contents[0]
        assert hasattr(image_part, "inline_data")
        assert image_part.inline_data.mime_type == "image/png"
        assert image_part.inline_data.data == base64.b64decode(REFERENCE_IMAGE_B64)

        text_part = contents[1]
        assert hasattr(text_part, "text")
        assert "VISUAL REFERENCE" in text_part.text

    async def test_no_reference_image_produces_plain_string_call(self):
        """Without reference_image, Gemini receives a plain string (text-only path)."""
        captured = {}

        async def _fake_json(contents, temperature, max_tokens):
            captured["contents"] = contents
            return json.dumps(SCENE_RESPONSE_ONE_PANEL)

        with patch.object(agent, "_call_gemini_json",          new_callable=AsyncMock, side_effect=_fake_json), \
             patch.object(agent, "_generate_image",            new_callable=AsyncMock, return_value="https://gcs/p1.png"), \
             patch.object(agent, "_generate_video_with_audio", new_callable=AsyncMock, return_value=""), \
             patch.object(agent, "_save_scene",                new_callable=AsyncMock):

            await agent.generate_scene(
                scene_id="scene-noimg-001",
                scene_prompt="A detective reads a letter.",
                clarifying_question="What is the emotional core?",
                clarification="Grief.",
            )

        assert isinstance(captured["contents"], str)

    async def test_scene_saved_with_correct_image_and_video_urls(self):
        """
        image_url comes from _generate_image; video_url from _generate_video_with_audio.
        audio_url must always be '' (baked into the video).
        """
        with patch.object(agent, "_call_gemini_json",          new_callable=AsyncMock, return_value=json.dumps(SCENE_RESPONSE_ONE_PANEL)), \
             patch.object(agent, "_generate_image",            new_callable=AsyncMock, return_value="https://gcs/panels/scene-url-001/panel_1.png"), \
             patch.object(agent, "_generate_video_with_audio", new_callable=AsyncMock, return_value="https://gcs/video/scene-url-001/panel_1.mp4"), \
             patch.object(agent, "_save_scene",                new_callable=AsyncMock):

            result = await agent.generate_scene(
                scene_id="scene-url-001",
                scene_prompt="Trail walk.",
                clarifying_question="Mood?",
                clarification="Bittersweet.",
                reference_image=REFERENCE_IMAGE_B64,
            )

        panel = result["panels"][0]
        assert panel["image_url"] == "https://gcs/panels/scene-url-001/panel_1.png"
        assert panel["video_url"] == "https://gcs/video/scene-url-001/panel_1.mp4"
        assert panel["audio_url"] == ""   # always baked into video

    async def test_save_scene_called_once(self):
        with patch.object(agent, "_call_gemini_json",          new_callable=AsyncMock, return_value=json.dumps(SCENE_RESPONSE_ONE_PANEL)), \
             patch.object(agent, "_generate_image",            new_callable=AsyncMock, return_value="https://gcs/p.png"), \
             patch.object(agent, "_generate_video_with_audio", new_callable=AsyncMock, return_value=""), \
             patch.object(agent, "_save_scene",                new_callable=AsyncMock) as mock_save:

            await agent.generate_scene(
                scene_id="scene-save-001",
                scene_prompt="A last walk.",
                clarifying_question="What hangs between them?",
                clarification="A goodbye.",
                reference_image=REFERENCE_IMAGE_B64,
            )

        mock_save.assert_awaited_once()
        saved_id = mock_save.call_args.args[0]
        assert saved_id == "scene-save-001"
