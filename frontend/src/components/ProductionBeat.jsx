import { useState } from "react";

const ARC_LABELS = {
  1: "ESTABLISH",
  2: "ESCALATE",
  3: "TENSION",
  4: "RESOLVE",
};

export default function ProductionBeat({
  panel,
  beatIndex,
  onSelect,
  isSelected,
  canSelect,
  onDialogueEdit,
  isRegenerating,
}) {
  const [imgLoaded, setImgLoaded] = useState(false);
  const beatLabel = ARC_LABELS[beatIndex] || `BEAT ${beatIndex}`;

  return (
    <section className={`beat-section fade-in ${isRegenerating ? "regenerating" : ""} ${isSelected ? "beat-selected" : ""}`}>

      {/* ── Beat header ───────────────────────────────────────────── */}
      <div className="beat-header">
        <div className="beat-number">BEAT {beatIndex}</div>
        <div className="beat-arc-label">{beatLabel}</div>
        {isRegenerating && <span className="panel-arc-revising">• GENERATING</span>}
      </div>

      {/* ── Intro narration — visual description ──────────────────── */}
      {panel.visual_description && (
        <div className="beat-narration beat-narration--intro">
          <span className="beat-narration-marker">↠ SCENE</span>
          <p>{panel.visual_description}</p>
        </div>
      )}

      {/* ── Camera note ───────────────────────────────────────────── */}
      {panel.camera_angle && (
        <div className="beat-camera">📷 {panel.camera_angle}</div>
      )}

      {/* ── Still image ───────────────────────────────────────────── */}
      <div className="beat-image-wrap">
        {panel.image_url ? (
          <img
            className={`beat-image ${imgLoaded ? "loaded" : "loading"}`}
            src={panel.image_url}
            alt={`Beat ${beatIndex} — ${panel.visual_description}`}
            onLoad={() => setImgLoaded(true)}
          />
        ) : (
          <div className="beat-image-placeholder">
            <span className="spinner" style={{ width: 32, height: 32 }} />
            <span style={{ marginTop: 12, color: "var(--text-secondary)", fontSize: 11 }}>
              Generating storyboard frame…
            </span>
          </div>
        )}
      </div>

      {/* ── Mid narration — dialogue ───────────────────────────────── */}
      <div className="beat-narration beat-narration--mid">
        <span className="beat-narration-marker">↠ DIALOGUE</span>
        <blockquote
          className={`beat-dialogue ${!isRegenerating && onDialogueEdit ? "editable" : ""}`}
          onClick={() => !isRegenerating && onDialogueEdit?.(panel.panel_number, null)}
          title={!isRegenerating && onDialogueEdit ? "Click to edit dialogue" : undefined}
        >
          {panel.dialogue || "[SILENCE]"}
          {!isRegenerating && onDialogueEdit && <span className="dialogue-edit-hint">✎</span>}
        </blockquote>
        {panel.direction_note && (
          <p className="beat-direction">↳ {panel.direction_note}</p>
        )}
      </div>

      {/* ── Video clip (audio baked in via ffmpeg merge) ───────────── */}
      {panel.video_url ? (
        <div className="beat-video-wrap">
          <video
            key={panel.video_url}
            className="beat-video"
            src={panel.video_url}
            controls
            playsInline
            preload="metadata"
            aria-label={`Beat ${beatIndex} cinematic clip`}
          />
          <div className="beat-media-label">🎬 CINEMATIC CLIP · 15s · score + dialogue</div>
        </div>
      ) : (
        <div className="beat-video-pending">
          <span className="spinner" style={{ width: 18, height: 18 }} />
          <span>Rendering video clip…</span>
        </div>
      )}

      {/* ── Select button ─────────────────────────────────────────── */}
      {canSelect && (
        <button
          className={`btn beat-select-btn ${isSelected ? "btn-selected" : "btn-primary"}`}
          onClick={() => onSelect(panel.panel_number)}
        >
          {isSelected ? "✓ SELECTED FOR POLISH" : `Select Beat ${beatIndex} for Final Polish →`}
        </button>
      )}
    </section>
  );
}
