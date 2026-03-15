import { useState } from "react";

export default function FinalEditPanel({
  panel,
  beatIndex,
  polishNote,
  setPolishNote,
  onFinalize,
  onBack,
  isFinalizing,
}) {
  const [imgLoaded, setImgLoaded] = useState(false);
  const arcLabels = { 1: "ESTABLISH", 2: "ESCALATE", 3: "TENSION", 4: "RESOLVE" };
  const beatLabel = arcLabels[beatIndex] || `BEAT ${beatIndex}`;

  return (
    <div className="final-edit-wrap fade-in">
      {/* ── Header ──────────────────────────────────────────────── */}
      <div className="final-edit-header">
        <div>
          <div className="final-edit-supertitle">FINAL POLISH</div>
          <div className="final-edit-title">Beat {beatIndex} · {beatLabel}</div>
        </div>
        <button
          className="btn btn-ghost"
          onClick={onBack}
          disabled={isFinalizing}
        >
          ← Back to stream
        </button>
      </div>

      {/* ── Selected beat preview ─────────────────────────────── */}
      <div className="final-edit-preview">
        <div className="final-edit-preview-cols">
          {panel.image_url && (
            <img
              className={`final-preview-img ${imgLoaded ? "loaded" : "loading"}`}
              src={panel.image_url}
              alt={`Selected beat ${beatIndex}`}
              onLoad={() => setImgLoaded(true)}
            />
          )}
          <div className="final-preview-text">
            {panel.visual_description && (
              <p className="final-preview-visual">{panel.visual_description}</p>
            )}
            <blockquote className="final-preview-dialogue">
              {panel.dialogue || "[SILENCE]"}
            </blockquote>
            {panel.direction_note && (
              <p className="final-preview-direction">↳ {panel.direction_note}</p>
            )}
          </div>
        </div>
        {panel.video_url && (
          <video
            key={panel.video_url}
            className="final-preview-video"
            src={panel.video_url}
            controls
            playsInline
            preload="metadata"
          />
        )}
        {panel.audio_url && (
          <div className="beat-audio-wrap" style={{ marginTop: 12 }}>
            <span className="beat-audio-label">🎵 ATMOSPHERE</span>
            <audio src={panel.audio_url} controls preload="none" className="beat-audio" />
          </div>
        )}
      </div>

      {/* ── Polish input ──────────────────────────────────────── */}
      <div className="final-edit-input-section">
        <label className="final-edit-input-label">
          One last note for the director
        </label>
        <p className="final-edit-input-hint">
          e.g. "Make the lighting warmer", "Slower, sadder music", "More shadow on her face"
        </p>
        <textarea
          className="scene-input"
          placeholder="Your final creative note…"
          value={polishNote}
          onChange={(e) => setPolishNote(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && polishNote.trim()) onFinalize();
          }}
          rows={3}
          disabled={isFinalizing}
        />
        <button
          className="btn btn-primary final-edit-submit"
          onClick={onFinalize}
          disabled={!polishNote.trim() || isFinalizing}
        >
          {isFinalizing ? (
            <><span className="spinner" /> Applying final polish…</>
          ) : (
            "✦ Finalize This Scene →"
          )}
        </button>
      </div>
    </div>
  );
}
