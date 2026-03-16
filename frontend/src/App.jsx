import { useState, useRef, useCallback, useEffect } from "react";
import BeatMap from "./components/BeatMap";
import QuickCuts from "./components/QuickCuts";

// In production, Firebase Hosting rewrites /api/** to Cloud Run — relative URLs work.
// In dev, Vite proxies /api/** to localhost:8080 — also relative. No VITE_API_URL needed.
// Override with VITE_API_URL only if calling the backend directly (e.g., staging tests).
const API = import.meta.env.VITE_API_URL || "";

// ── State machine ────────────────────────────────────────────────────────────
// idle → clarifying → generating → scene ↔ revising
const STATES = {
  IDLE:       "idle",
  CLARIFYING: "clarifying",
  GENERATING: "generating",
  SCENE:      "scene",
  REVISING:   "revising",
};

const LOAD_STEPS = [
  "Analyzing emotional core…",
  "Crafting the key moment…",
  "Writing scene direction…",
  "Generating storyboard frame…",
  "Composing ambient score…",
  "Voicing character dialogue…",
  "Rendering cinematic clip…",
  "Weaving it all together…",
];

// Per-call timeouts (ms) — all fast-path (Veo runs in background).
// 55s is just under Firebase Hosting's 60s proxy limit.
const TIMEOUTS = {
  clarify:  30_000,
  generate: 55_000,
  revise:   55_000,
};

async function apiFetch(path, options = {}, timeoutMs = 300_000, _retry = true) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API}${path}`, {
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      ...options,
    });
    // Retry once on cold-start gateway errors (502/503/504) after a short delay
    if (_retry && (res.status === 502 || res.status === 503 || res.status === 504)) {
      clearTimeout(timer);
      await new Promise((r) => setTimeout(r, 2000));
      return apiFetch(path, options, timeoutMs, false);
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `Request failed (${res.status})`);
    }
    return res.json();
  } catch (err) {
    if (err.name === "AbortError") throw new Error("Request timed out — please try again.");
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

/** Read a File object as a base64 string (strips the data-URL prefix). */
function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload  = () => resolve(reader.result.split(",")[1]);
    reader.onerror = () => reject(new Error("Failed to read image file"));
    reader.readAsDataURL(file);
  });
}

export default function App() {
  const [theme, setTheme] = useState(() => localStorage.getItem("theme") || "dark");
  const [appState,    setAppState]    = useState(STATES.IDLE);
  const [sceneInput,  setSceneInput]  = useState("");
  const [clarifyCtx,  setClarifyCtx]  = useState(null);
  const [clarifyAns,  setClarifyAns]  = useState("");
  const [scene,       setScene]       = useState(null);
  const [loadStep,    setLoadStep]    = useState(0);
  const [error,       setError]       = useState(null);
  const [affectedPanels, setAffectedPanels] = useState([]);

  // Multimodal reference image
  const [refImage,     setRefImage]     = useState(null);   // base64 string
  const [refImageMime, setRefImageMime] = useState("image/jpeg");
  const [refImageName, setRefImageName] = useState("");
  const imageInputRef = useRef(null);

  // Export state
  const [notebookLMCopied, setNotebookLMCopied] = useState(false);

  const recognitionRef = useRef(null);
  const [recording, setRecording] = useState(false);
  const [inputModality, setInputModality] = useState("text"); // "text" | "image" | "voice"

  // ── All useState/useRef declarations above this line ──────────────────────
  // NOTE: both useEffects are intentionally placed HERE, after every useState/useRef,
  // so the minifier never hoists them above a const TDZ.

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  // Poll for video_url when scene is loaded but video is still rendering in background
  useEffect(() => {
    if (!scene || appState !== STATES.SCENE) return;
    if (scene.panels?.[0]?.video_url) return; // already have it
    const id = setInterval(async () => {
      try {
        const data = await apiFetch(`/api/scene/${scene.scene_id}`, {}, 10_000);
        if (data.panels?.[0]?.video_url) {
          setScene(data);
          clearInterval(id);
        }
      } catch { /* keep polling silently */ }
    }, 5_000);
    return () => clearInterval(id);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scene?.scene_id, scene?.panels?.[0]?.video_url, appState]);

  // ── Reference image upload ──────────────────────────────────────────────────
  const handleImageUpload = useCallback(async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setError("Please select an image file (JPEG, PNG, WebP, etc.).");
      return;
    }
    try {
      const b64 = await readFileAsBase64(file);
      setRefImage(b64);
      setRefImageMime(file.type);
      setRefImageName(file.name);
      setInputModality("image");
    } catch {
      setError("Could not read the image. Try a different file.");
    }
    // Reset the input so the same file can be re-selected
    e.target.value = "";
  }, []);

  const clearRefImage = useCallback(() => {
    setRefImage(null);
    setRefImageName("");
    if (inputModality === "image") setInputModality("text");
  }, [inputModality]);

  // ── TTS — speak the clarification question aloud (voice modality) ──────────
  const speakQuestion = useCallback((text) => {
    if (!("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utt = new SpeechSynthesisUtterance(text);
    utt.rate = 0.88;
    utt.pitch = 0.95;
    utt.volume = 1;
    window.speechSynthesis.speak(utt);
  }, []);

  // ── Voice input helper ─────────────────────────────────────────────────────
  const startVoice = useCallback((onTranscript) => {
    if (!("webkitSpeechRecognition" in window || "SpeechRecognition" in window)) {
      setError("Voice input not supported in this browser. Try Chrome.");
      return;
    }
    if (recording) {
      recognitionRef.current?.stop();
      return;
    }
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const rec = new SpeechRecognition();
    rec.continuous = false;
    rec.interimResults = false;
    rec.lang = "en-US";
    rec.onresult = (e) => onTranscript(e.results[0][0].transcript);
    rec.onerror = () => setRecording(false);
    rec.onend   = () => setRecording(false);
    rec.start();
    recognitionRef.current = rec;
    setRecording(true);
  }, [recording]);

  // Voice for pitch textarea
  const toggleVoice = useCallback(() => {
    setInputModality("voice");
    startVoice((t) => setSceneInput(t));
  }, [startVoice]);

  // Voice for clarify answer textarea
  const toggleVoiceClarify = useCallback(() => {
    startVoice((t) => setClarifyAns(t));
  }, [startVoice]);

  // ── Step 1: Clarify ────────────────────────────────────────────────────────
  const handleClarify = async () => {
    if (!sceneInput.trim()) return;
    setError(null);
    setAppState(STATES.CLARIFYING);
    if (inputModality === "text" && sceneInput.trim()) setInputModality("text");
    try {
      const data = await apiFetch("/api/scene/clarify", {
        method: "POST",
        body: JSON.stringify({ scene_prompt: sceneInput.trim() }),
      }, TIMEOUTS.clarify);
      setClarifyCtx(data);
      // If user pitched by voice — read the question aloud
      if (inputModality === "voice") speakQuestion(data.question);
    } catch (err) {
      setError(err.message);
      setAppState(STATES.IDLE);
    }
  };

  // ── Step 2: Generate full scene ────────────────────────────────────────────
  const handleGenerate = async () => {
    if (!clarifyAns.trim()) return;
    setError(null);
    setAppState(STATES.GENERATING);
    setLoadStep(0);

    const interval = setInterval(() => {
      setLoadStep((s) => (s < LOAD_STEPS.length - 1 ? s + 1 : s));
    }, 2200);

    try {
      const body = {
        scene_id:            clarifyCtx.scene_id,
        scene_prompt:        sceneInput.trim(),
        clarifying_question: clarifyCtx.question,
        clarification:       clarifyAns.trim(),
      };
      if (refImage) {
        body.reference_image      = refImage;
        body.reference_image_mime = refImageMime;
      }
      const data = await apiFetch("/api/scene/generate", {
        method: "POST",
        body:   JSON.stringify(body),
      }, TIMEOUTS.generate);
      clearInterval(interval);
      setScene(data);
      setAffectedPanels([]);
      setAppState(STATES.SCENE);
    } catch (err) {
      clearInterval(interval);
      setError(err.message);
      setAppState(STATES.IDLE);
    }
  };

  // ── Quick Cut: directly revise with the given note (no preview step) ───────
  const handleQuickCut = async (note) => {
    if (!scene || appState === STATES.REVISING) return;
    setError(null);
    setAffectedPanels([1]);
    setAppState(STATES.REVISING);
    try {
      const data = await apiFetch(`/api/scene/${scene.scene_id}/revise`, {
        method: "POST",
        body: JSON.stringify({
          revision_note:   note,
          approved_panels: [1],
        }),
      }, TIMEOUTS.revise);
      setScene(data);
      setAffectedPanels(data.affected_panels || [1]);
    } catch (err) {
      setError(err.message);
    } finally {
      setAppState(STATES.SCENE);
    }
  };

  // ── Reset ──────────────────────────────────────────────────────────────────
  const handleReset = () => {
    setAppState(STATES.IDLE);
    setSceneInput("");
    setClarifyCtx(null);
    setClarifyAns("");
    setScene(null);
    setError(null);
    setAffectedPanels([]);
    setInputModality("text");
    clearRefImage();
  };

  // ── Export helpers ─────────────────────────────────────────────────────────
  const exportToObsidian = useCallback(() => {
    if (!scene) return;
    const bm   = scene.beat_map || {};
    const date = new Date().toISOString().split("T")[0];
    const slug = (scene.scene_prompt || "scene")
      .slice(0, 50).replace(/[^a-z0-9]+/gi, "-").toLowerCase().replace(/(^-|-$)/g, "");

    const lines = [
      "---",
      `title: "${(scene.scene_prompt || "Untitled Scene").replace(/"/g, '\\"')}"`,
      `scene_id: "${scene.scene_id}"`,
      `date: ${date}`,
      `tags: [directors-lab, scene]`,
      `beat_map:`,
      `  tension: ${bm.tension ?? 0}`,
      `  longing: ${bm.longing ?? 0}`,
      `  resolve: ${bm.resolve ?? 0}`,
      "---",
      "",
      `# ${scene.scene_prompt || "Untitled Scene"}`,
      "",
      `> ${scene.scene_summary || ""}`,
      "",
      "## 🎬 Beat Map",
      "| | Score |",
      "|---|---|",
      `| 🔴 Tension | ${bm.tension ?? 0} / 100 |`,
      `| 🟣 Longing | ${bm.longing ?? 0} / 100 |`,
      `| 🟢 Resolve | ${bm.resolve ?? 0} / 100 |`,
      "",
      "---",
      "",
    ];

    for (const panel of (scene.panels || [])) {
      lines.push(`## Scene Frame`, "");
      if (panel.camera_angle)       lines.push(`📷 *${panel.camera_angle}*`, "");
      if (panel.visual_description) lines.push("**↠ SCENE**", panel.visual_description, "");
      if (panel.dialogue && panel.dialogue !== "[SILENCE]")
        lines.push("**↠ DIALOGUE**", `> "${panel.dialogue}"`, "");
      if (panel.direction_note)     lines.push(`↳ *${panel.direction_note}*`, "");
      if (panel.image_url)          lines.push(`![Scene Frame](${panel.image_url})`, "");
      if (panel.video_url)          lines.push(`🎬 [Cinematic Clip](${panel.video_url})`, "");
      if (panel.audio_url)          lines.push(`🎵 [Ambient Score](${panel.audio_url})`, "");
      lines.push("---", "");
    }

    lines.push(`*Generated by [Director's Lab](https://github.com/Sakethv7/director-s-lab) · ${date}*`);

    const md   = lines.join("\n");
    const blob = new Blob([md], { type: "text/markdown" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = `${slug}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }, [scene]);

  const exportToNotebookLM = useCallback(() => {
    if (!scene) return;
    const bm = scene.beat_map || {};
    let text  = `DIRECTOR'S LAB — SCENE EXPORT\n${"=".repeat(40)}\n\n`;
    text     += `SCENE: ${scene.scene_prompt}\n`;
    text     += `SUMMARY: ${scene.scene_summary || ""}\n\n`;
    text     += `BEAT MAP  |  Tension: ${bm.tension}/100  |  Longing: ${bm.longing}/100  |  Resolve: ${bm.resolve}/100\n\n`;
    text     += `${"─".repeat(40)}\n\n`;

    for (const panel of (scene.panels || [])) {
      text += `SCENE FRAME\n`;
      if (panel.camera_angle)       text += `Camera: ${panel.camera_angle}\n`;
      if (panel.visual_description) text += `Scene: ${panel.visual_description}\n`;
      if (panel.dialogue)           text += `Dialogue: "${panel.dialogue}"\n`;
      if (panel.direction_note)     text += `Direction: ${panel.direction_note}\n`;
      text += "\n";
    }

    navigator.clipboard.writeText(text).catch(() => {});
    window.open("https://notebooklm.google.com", "_blank");
    setNotebookLMCopied(true);
    setTimeout(() => setNotebookLMCopied(false), 5000);
  }, [scene]);

  const isRevising = appState === STATES.REVISING;
  const showStream = [STATES.SCENE, STATES.REVISING].includes(appState);

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="app">
      <header className="app-header">
        <div className="logo">
          <span className="logo-icon">🎬</span>
          <div>
            <div>Director&apos;s Lab</div>
            <div className="logo-sub">Gemini Live Agent Challenge · Creative Storyteller</div>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {scene && (
            <span className="scene-id-badge">
              SCENE {scene.scene_id.slice(0, 8).toUpperCase()}
            </span>
          )}
          <button
            className="theme-toggle"
            onClick={() => setTheme(t => t === "dark" ? "light" : "dark")}
            title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          >
            {theme === "dark" ? "☀" : "☾"}
          </button>
        </div>
      </header>

      {error && (
        <div className="error-banner" style={{ marginBottom: 20 }}>
          ⚠ {error}
          <button
            className="btn btn-ghost"
            onClick={() => setError(null)}
            style={{ marginLeft: "auto", padding: "4px 10px", fontSize: 11 }}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* ── IDLE ── */}
      {appState === STATES.IDLE && (
        <div className="stage fade-in">
          <div style={{ textAlign: "center" }}>
            <h1 className="stage-headline">What&apos;s your scene?</h1>
            <p className="stage-tagline">Pitch the moment. The director takes it from there.</p>
          </div>

          <div className="scene-input-wrap">
            <textarea
              className="scene-input"
              placeholder="e.g. A detective finds a letter from her dead sister — written yesterday."
              value={sceneInput}
              onChange={(e) => setSceneInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleClarify();
              }}
              rows={4}
            />

            {/* Reference image preview */}
            {refImage && (
              <div className="ref-image-preview">
                <img
                  src={`data:${refImageMime};base64,${refImage}`}
                  alt="Visual reference"
                  className="ref-image-thumb"
                />
                <div className="ref-image-info">
                  <span className="ref-image-label">📷 Visual reference</span>
                  <span className="ref-image-name">{refImageName}</span>
                </div>
                <button
                  className="btn btn-ghost ref-image-remove"
                  onClick={clearRefImage}
                  title="Remove reference image"
                >
                  ✕
                </button>
              </div>
            )}

            <div className="input-actions">
              {/* Hidden file input for image upload */}
              <input
                ref={imageInputRef}
                type="file"
                accept="image/*"
                style={{ display: "none" }}
                onChange={handleImageUpload}
              />
              <button
                className="btn btn-voice"
                onClick={() => imageInputRef.current?.click()}
                title="Add visual reference image"
                style={{ color: refImage ? "var(--gold)" : undefined }}
              >
                📷 {refImage ? "Image ✓" : "Image"}
              </button>
              <button
                className={`btn btn-voice ${recording ? "recording" : ""}`}
                onClick={toggleVoice}
                title="Voice input"
              >
                {recording ? "🔴 Recording…" : "🎙 Voice"}
              </button>
              <button
                className="btn btn-primary"
                onClick={handleClarify}
                disabled={!sceneInput.trim()}
              >
                Pitch Scene →
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── CLARIFYING ── */}
      {appState === STATES.CLARIFYING && clarifyCtx && (
        <div className="stage fade-in">
          <div className="clarify-wrap">
            <div className="director-callout">
              <span className="icon">🎬</span>
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                  <div className="label">Director asks</div>
                  <div className="modality-tag">
                    via <span>{inputModality === "voice" ? "🎙 voice" : inputModality === "image" ? "📷 image" : "⌨ text"}</span>
                    {inputModality === "voice" && (
                      <button
                        className="btn btn-ghost"
                        style={{ padding: "2px 8px", fontSize: 10 }}
                        onClick={() => speakQuestion(clarifyCtx.question)}
                        title="Hear the question"
                      >🔊</button>
                    )}
                  </div>
                </div>
                <div className="question">{clarifyCtx.question}</div>
              </div>
            </div>

            <textarea
              className="clarify-input"
              placeholder="Answer the director…"
              value={clarifyAns}
              onChange={(e) => setClarifyAns(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleGenerate();
              }}
              rows={3}
            />

            <div style={{ display: "flex", gap: 10, justifyContent: "space-between", alignItems: "center" }}>
              <button className="btn btn-ghost" onClick={handleReset}>← Start over</button>
              <div style={{ display: "flex", gap: 10 }}>
                <button
                  className={`btn btn-voice ${recording ? "recording" : ""}`}
                  onClick={toggleVoiceClarify}
                  title="Voice answer"
                >
                  {recording ? "🔴 Recording…" : "🎙 Voice"}
                </button>
                <button
                  className="btn btn-primary"
                  onClick={handleGenerate}
                  disabled={!clarifyAns.trim()}
                >
                  Roll camera →
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── GENERATING ── */}
      {appState === STATES.GENERATING && (
        <div className="loading-stage fade-in">
          <div className="clapperboard-anim">🎬</div>
          <h2>Directing your scene…</h2>
          <div className="loading-steps">
            {LOAD_STEPS.map((step, i) => (
              <div
                key={step}
                className={`loading-step ${i === loadStep ? "active" : i < loadStep ? "done" : ""}`}
              >
                <div className="step-dot" />
                {step}
              </div>
            ))}
          </div>
          <p className="loading-hint">
            1 storyboard frame · ambient score · voiced dialogue · 15s cinematic clip — takes about 2–3 minutes.
          </p>
        </div>
      )}

      {/* ── SCENE / REVISING ── */}
      {showStream && scene && (() => {
        const panel = scene.panels[0];
        if (!panel) return null;
        const isRegenPanel = isRevising && affectedPanels.includes(panel.panel_number);
        return (
          <div className="workspace fade-in">
            {/* ── Hero frame ── */}
            <div className="hero-frame">
              <div className="hero-synopsis">
                <span className="label">Synopsis</span>
                <p>{scene.scene_summary}</p>
              </div>

              <div className="hero-content">
                {/* Left: storyboard image */}
                <div className="hero-image-wrap">
                  {isRegenPanel ? (
                    <div className="hero-image-placeholder">
                      <span className="spinner" style={{ width: 40, height: 40 }} />
                      <span>Regenerating frame…</span>
                    </div>
                  ) : panel.image_url ? (
                    <img className="hero-image" src={panel.image_url} alt="Scene frame" />
                  ) : (
                    <div className="hero-image-placeholder">
                      <span className="spinner" style={{ width: 40, height: 40 }} />
                      <span>Generating frame…</span>
                    </div>
                  )}
                  {panel.camera_angle && (
                    <div className="hero-camera-badge">📷 {panel.camera_angle}</div>
                  )}
                </div>

                {/* Right: scene text */}
                <div className="hero-text">
                  <div className="hero-scene-label">↠ SCENE</div>
                  <p className="hero-visual-desc">{panel.visual_description}</p>
                  <div className="hero-scene-label" style={{ marginTop: 16 }}>↠ DIALOGUE</div>
                  <blockquote className="hero-dialogue">
                    {panel.dialogue || "[SILENCE]"}
                  </blockquote>
                  {panel.direction_note && (
                    <p className="hero-direction">↳ {panel.direction_note}</p>
                  )}
                </div>
              </div>

              {/* Video with baked audio */}
              <div className="hero-video-wrap">
                {isRegenPanel ? (
                  <div className="hero-video-pending">
                    <span className="spinner" style={{ width: 24, height: 24 }} />
                    <span>Regenerating cinematic clip…</span>
                  </div>
                ) : panel.video_url ? (
                  <>
                    <video
                      key={panel.video_url}
                      className="hero-video"
                      src={panel.video_url}
                      controls
                      playsInline
                      preload="metadata"
                    />
                    <div className="hero-video-label">🎬 CINEMATIC CLIP · 15s · score + dialogue</div>
                  </>
                ) : (
                  <div className="hero-video-pending">
                    <span className="spinner" style={{ width: 24, height: 24 }} />
                    <span>Rendering cinematic clip…</span>
                  </div>
                )}
              </div>
            </div>

            {/* ── Sidebar: beat map + quick cuts + export ── */}
            <div className="sidebar">
              <BeatMap beatMap={scene.beat_map} />
              <QuickCuts
                onRevise={handleQuickCut}
                isRevising={isRevising}
              />
              {/* ── Export bar ── */}
              {appState === STATES.SCENE && (
                <div className="export-bar">
                  <div className="export-bar-label">EXPORT SCENE</div>
                  <button
                    className="btn export-btn export-btn--obsidian"
                    onClick={exportToObsidian}
                    title="Download as Obsidian-ready Markdown note"
                  >
                    📓 Obsidian
                  </button>
                  <button
                    className={`btn export-btn export-btn--notebooklm ${notebookLMCopied ? "export-btn--copied" : ""}`}
                    onClick={exportToNotebookLM}
                    title="Copy scene text and open NotebookLM"
                  >
                    {notebookLMCopied ? "✓ Copied — paste in NotebookLM" : "🔬 NotebookLM"}
                  </button>
                </div>
              )}

              <div className="new-scene-wrap">
                <button className="btn btn-ghost" onClick={handleReset} disabled={isRevising}>
                  ✦ New Scene
                </button>
              </div>
            </div>
          </div>
        );
      })()}
    </div>
  );
}
