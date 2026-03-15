import { useState, useEffect, useRef } from "react";

// Arc labels map panel number → narrative beat name
const ARC_LABELS = {
  1: "ESTABLISH",
  2: "ESCALATE",
  3: "TENSION",
  4: "RESOLVE",
};

export default function StoryboardPanel({ panel, isRegenerating, onDialogueEdit }) {
  const [imgLoaded, setImgLoaded] = useState(false);
  const [editingDialogue, setEditingDialogue] = useState(false);
  const [draftDialogue, setDraftDialogue] = useState(panel.dialogue || "");
  const textareaRef = useRef(null);

  const hasAudio = Boolean(panel.audio_url);
  const hasVideo = Boolean(panel.video_url);
  const arcLabel = ARC_LABELS[panel.panel_number] || `PANEL ${panel.panel_number}`;

  // Sync draft when server returns updated panel
  useEffect(() => {
    if (!editingDialogue) setDraftDialogue(panel.dialogue || "");
  }, [panel.dialogue, editingDialogue]);

  // Auto-size textarea height
  useEffect(() => {
    if (editingDialogue && textareaRef.current) {
      const el = textareaRef.current;
      el.style.height = "auto";
      el.style.height = el.scrollHeight + "px";
    }
  }, [editingDialogue, draftDialogue]);

  const commitEdit = () => {
    setEditingDialogue(false);
    const trimmed = draftDialogue.trim() || "[SILENCE]";
    if (trimmed !== (panel.dialogue || "[SILENCE]")) {
      onDialogueEdit?.(panel.panel_number, trimmed);
    }
  };

  const cancelEdit = () => {
    setEditingDialogue(false);
    setDraftDialogue(panel.dialogue || "");
  };

  return (
    <div className={`panel-card fade-in ${isRegenerating ? "regenerating" : ""}`}>

      {/* ── Arc header ─────────────────────────────────────────────── */}
      <div className="panel-arc-header">
        <span className="panel-arc-num">FRAME {panel.panel_number}</span>
        <span className="panel-arc-label">{arcLabel}</span>
        {isRegenerating && <span className="panel-arc-revising">• REVISING</span>}
      </div>

      {/* ── Script / direction ─────────────────────────────────────── */}
      <div className="panel-body">
        {panel.visual_description && (
          <p className="panel-visual-desc">
            {panel.visual_description}
          </p>
        )}

        {editingDialogue ? (
          <textarea
            ref={textareaRef}
            className="panel-dialogue-edit"
            value={draftDialogue}
            onChange={(e) => setDraftDialogue(e.target.value)}
            onBlur={commitEdit}
            onKeyDown={(e) => {
              if (e.key === "Escape") { e.preventDefault(); cancelEdit(); }
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); commitEdit(); }
            }}
            rows={2}
            autoFocus
          />
        ) : (
          <div
            className={`panel-dialogue ${!isRegenerating ? "editable" : ""}`}
            onClick={() => !isRegenerating && setEditingDialogue(true)}
            title={isRegenerating ? undefined : "Click to edit dialogue"}
          >
            {panel.dialogue || "[SILENCE]"}
            {!isRegenerating && <span className="dialogue-edit-hint">✎</span>}
          </div>
        )}

        {panel.direction_note && (
          <div className="panel-direction">
            ↳ {panel.direction_note}
          </div>
        )}

        {panel.camera_angle && (
          <div className="panel-camera-inline">
            📷 {panel.camera_angle}
          </div>
        )}
      </div>

      {/* ── Generated still image ─────────────────────────────────── */}
      <div className="panel-image-wrap">
        {panel.image_url ? (
          <img
            className={`panel-image ${imgLoaded ? "" : "loading"}`}
            src={panel.image_url}
            alt={`Frame ${panel.panel_number} — ${panel.visual_description}`}
            onLoad={() => setImgLoaded(true)}
          />
        ) : (
          <div className="panel-image-placeholder">
            <span className="spinner" style={{ width: 28, height: 28 }} />
          </div>
        )}
        <div className="panel-media-label">🖼 STORYBOARD FRAME</div>
      </div>

      {/* ── Ambient score (inline audio player) ───────────────────── */}
      {hasAudio && (
        <div className="panel-audio-wrap">
          <span className="panel-audio-label">🎵 SCORE</span>
          <audio
            className="panel-audio"
            src={panel.audio_url}
            controls
            preload="none"
            aria-label={`Frame ${panel.panel_number} ambient score`}
          />
        </div>
      )}

      {/* ── Veo video clip ─────────────────────────────────────────── */}
      {hasVideo && (
        <div className="panel-video-wrap">
          <video
            key={panel.video_url}
            className="panel-video"
            src={panel.video_url}
            controls
            playsInline
            preload="metadata"
            aria-label={`Frame ${panel.panel_number} cinematic clip`}
          />
          <div className="panel-media-label panel-media-label--video">🎥 CINEMATIC CLIP</div>
        </div>
      )}
    </div>
  );
}
