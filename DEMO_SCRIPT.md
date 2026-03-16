# DIRECTOR'S LAB — Demo Script v3
## Gemini Live Agent Challenge · Creative Storyteller
### Speakers: SAKETH (S) · ADITHYA (A)
### Target: Under 4 minutes · Record in one take

---

## BEFORE YOU HIT RECORD

**Screen setup:**
- Saketh: browser open on https://gemini-live-agent-challenge-26.web.app/ — landing page visible, nothing typed
- Adithya: GCP console open in a SEPARATE TAB — Logs page bookmarked, ready to switch instantly
- GOW2.jpg saved to desktop for quick upload
- Pre-generate the Rome scene the night before as a backup — if anything crashes, cut to it

**One rule:** Never go silent. Gaps are proof. Fill every second.

---

## [0:00 – 0:22] OPENING — SAKETH ON LANDING PAGE

*Camera on screen. Saketh speaks.*

**S:** "Every director has a scene living in their head. The light. The silence. The moment someone doesn't look back. The problem is — getting it out of your head fast enough that the feeling doesn't die in translation."

*Pause one beat. Let the landing page breathe.*

**S:** "This is Director's Lab. You pitch the moment. The director takes it from there."

*Point to the subtitle on screen as you say it.*

---

## [0:22 – 0:50] SCENE 1 — TEXT INPUT · SAKETH TYPES

*Click into the text box. Type slowly — let viewers read it.*

**S:** "Three ways in — text, voice, or a reference image. We're starting with text."

*Type into the box:*
```
Two strangers meet on the steps of the Pantheon at midnight.
Rome, present day. She's leaving for Milan in the morning.
He's been watching her for three nights. This is the last time.
```

**S:** "Romeo and Juliet — but modern Rome. Unresolved. No happy ending. That's the pitch."

*Click PITCH SCENE →*

---

## GAP 1 — Waiting for clarifying question (~5–10 sec)
## DO NOT GO SILENT. Saketh fills immediately.

**S:** "Right now Gemini 2.5 Flash is analyzing the scene — the setting, the emotional subtext, what's unresolved. It's not generating yet. It's thinking about what it needs to know first. That's the difference between a generator and a director."

*Question appears on screen.*

---

## [0:50 – 1:10] CLARIFYING QUESTION — ADITHYA TAKES OVER

*Adithya reads the question on screen aloud.*

**A:** "Before a single image is generated — the Director asks one question to lock in the emotional core. This isn't a chatbot looping back for more input. This is a collaborator making sure it understands the feeling before it builds the scene."

*Type the answer:*
`Unresolved longing. She's already decided.`

*Click confirm / send.*

**A:** "One question. That's it. Then it takes over."

---

## GAP 2 — Waiting for full scene generation (~45–90 sec)
## THIS IS THE LONGEST WAIT. Both speakers fill the entire time.

*Start talking the instant you hit confirm.*

**A:** "Five AI models are running in parallel right now. Gemini 2.5 Flash writing the defining moment of the scene — the emotional peak, the single frame that holds the whole story."

**S:** "Imagen 3 on Vertex AI painting that frame. Not stock images. Not templates. Generated from the exact emotional brief we just gave it — the longing, the unresolved tension, the specific characters."

**A:** "Lyria composing an ambient score. Mood-matched to the scene. You'll hear it underneath when the clip plays."

**S:** "Gemini TTS voicing the dialogue. Gender-matched voices — Fenrir for the male character, Kore for the female. Real synthesized performance, with acting-style direction baked into the prompt. Not text-to-speech defaults."

**A:** "And Veo 2 rendering a 15-second cinematic clip — with the Lyria score and the TTS voice merged together via ffmpeg in the cloud. This is what real generation latency looks like. Not a cached demo."

*If still waiting:*

**S:** "Every one of these calls is hitting Vertex AI in us-central1. You'll see all of them live in the Cloud Run logs at the end."

**A:** "This is why Cloud Run matters — the backend is handling all five AI model calls without blocking the UI. Serverless. Scales to zero when idle. Zero infrastructure management on our end."

*Full scene appears.*

**S:** "There it is."

---

## [1:55 – 2:15] BEAT MAP — SAKETH EXPLAINS

*Point to the beat map sidebar.*

**S:** "This is the beat map. Tension. Longing. Resolve — scored zero to a hundred. These aren't labels. These are the parameters anchoring the Imagen prompt, the Lyria score, and the Veo clip. Everything in the same emotional register. One defining moment — not four random images stitched together."

*Pause one beat.*

**S:** "Now watch what happens when we change the direction."

---

## [2:15 – 2:42] REVISION LOOP — ADITHYA LEADS, SAKETH SUPPORTS

*Adithya types into the Director's Note box.*

**A:** "Director's note —"

*Type:*
`Make it colder. Less dialogue. She already knows he's lying.`

*Click the revision / preview button.*

**A:** "Before a single Imagen call fires — Gemini shows us the proposed changes. Beat map delta. What's changing. Why."

*HITL preview modal appears.*

**S:** "This is the human-in-the-loop layer. You see the beat map shift — tension up, resolve down. You approve or reject the panel before anything regenerates. No surprise costs. No AI deciding what to change. You stay the director."

*Adithya approves the panel.*

**A:** "Approved. Apply."

*Click Apply.*

---

## GAP 3 — Waiting for panel to regenerate (~20–40 sec)
## Adithya leads. Saketh closes when panel appears.

**A:** "The approved panel is hitting Imagen and Veo right now — new frame, new clip, new score. If we'd rejected it, the original image and URL stay untouched. No unnecessary generation. No cost blowout. That's the HITL loop — human in the loop, every single step."

*Revised panel appears.*

**S:** "Same scene. Different feeling. That's directing — not prompting."

---

## [2:42 – 2:57] VOICE INPUT — SAKETH

*Click the VOICE button.*

**S:** "One more — voice input."

*Speak clearly into the mic:*
> "A crime thriller in Taipei. Neon reflections on wet pavement.
> A detective meets an informant in a 24-hour noodle bar.
> Hong Kong aesthetics — slow motion, cigarette smoke,
> faces half in shadow. Someone is about to betray someone."

**S:** "Web Speech API — straight into Gemini. No transcription step. No lag. Three modalities. One pipeline."

*Don't wait for generation — cut straight to GCP.*

---

## [2:57 – 3:40] GCP CONSOLE — ADITHYA TAKES FULL CONTROL

*Switch to GCP console tab. Adithya drives entirely.*

**A:** "Under the hood — this is running entirely on Google Cloud."

*Go to: Cloud Run → directors-lab-api → Revisions tab*

**A:** "directors-lab-api. Cloud Run. Serverless. Running in us-central1 — latest revision taking 100% of traffic."

*Click Observability → Metrics*

**A:** "Request count — those spikes are the Gemini, Imagen, and Veo calls from the demo you just watched. Latency over one minute on some requests — that's Veo 2 rendering a cinematic clip in the cloud. Real latency. Real generation."

*Click Logs in the left sidebar*

**A:** "Live logs."

*Scroll to find and ZOOM IN on these two lines:*
- `INFO:agent:Gemini TTS: 311566 PCM bytes synthesised`
- `INFO:agent:Panel 1: 15s video merged (ambient=True voice=True)`

**A:** "Gemini TTS — PCM audio bytes synthesized. Gender-matched voice, with acting direction. Panel 1 — 15-second video merged. Ambient score on. Voiced dialogue on."

*Scroll up to show the wall of Vertex AI POST requests.*

**A:** "Every one of these POST requests is a Vertex AI call — Imagen 3, Lyria, Veo 2 — logged in sequence. Text. Image. Audio. Video. In one pipeline. On Google Cloud."

---

## [3:40 – 3:58] CLOSING — BOTH SPEAKERS

*Switch back to the app. Show the finished scene with video player visible.*

**S:** "Director's Lab."

**A:** "Gemini writes it."

**S:** "Imagen paints it."

**A:** "Lyria scores it."

**S:** "Veo renders it."

**A:** "You direct it."

*One beat of silence.*

**S + A:** "Shoot, cut, and direct at 24fps."

*Hold on screen 3 seconds. Fade.*

---

## TIMING SUMMARY

| Section | Speaker | Time | Gap fill? |
|---|---|---|---|
| Opening | Saketh | 0:00 – 0:22 | — |
| Text input | Saketh | 0:22 – 0:50 | — |
| Gap 1 — clarifying question wait | Saketh | ~5–10 sec | ✓ |
| Clarifying question | Adithya | 0:50 – 1:10 | — |
| Gap 2 — full scene generation | Both alternating | ~45–90 sec | ✓ |
| Beat map | Saketh | 1:55 – 2:15 | — |
| Revision / HITL | Adithya leads, Saketh supports | 2:15 – 2:42 | — |
| Gap 3 — panel regeneration | Adithya leads, Saketh closes | ~20–40 sec | ✓ |
| Voice input | Saketh | 2:42 – 2:57 | — |
| GCP console | Adithya | 2:57 – 3:40 | — |
| Closing | Both | 3:40 – 3:58 | — |

**Total: ~3:58** ✓ Under 4 minutes

---

## THE THREE GAP LINES — MEMORISE THESE COLD

Say them naturally. Not like you're reading.

**Gap 1 — Saketh:**
> *"It's not generating yet. It's thinking about what it needs to know first.*
> *That's the difference between a generator and a director."*

**Gap 2 — Adithya (the big one):**
> *"This is what real generation latency looks like. Not a cached demo."*

**Gap 2 — Saketh:**
> *"Every one of these calls is hitting Vertex AI in us-central1."*

**Gap 3 — Adithya:**
> *"No unnecessary generation. No cost blowout.*
> *Human in the loop, every single step."*

---

## KEY LINES — DO NOT READ FROM SCRIPT

**Saketh:**
- *"You pitch the moment. The director takes it from there."*
- *"Everything in the same emotional register. One defining moment."*
- *"That's directing — not prompting."*

**Adithya:**
- *"One question. That's it. Then it takes over."*
- *"No surprise costs. No AI deciding what to change. You stay the director."*
- *"Text. Image. Audio. Video. In one pipeline. On Google Cloud."*

---

## BACKUP PLAN — IF GENERATION FAILS OR CRASHES

**If scene fails to generate:**
- Adithya says: *"Here's a scene we generated earlier —"*
- Switch to pre-generated Rome scene from the night before
- Pick up from beat map section — everything from 1:55 onwards works identically

**If GCP console is slow to load:**
- Saketh fills: *"While that loads — everything you just watched,
  five AI models, ffmpeg merge, revision loop —
  all running on a single Cloud Run service in us-central1."*

---

## PRE-DEMO CHECKLIST

- [ ] App loaded on landing page, nothing typed
- [ ] GCP console logged in as sakethv7@gmail.com on gemini-live-agent-challenge-26
- [ ] GCP Logs tab bookmarked and one click away
- [ ] GOW2.jpg saved to desktop
- [ ] Rome scene pre-generated overnight as backup
- [ ] Mic tested for voice input
- [ ] Screen recording software running before you start
- [ ] Both speakers have read script out loud at least twice
- [ ] Agreed on who controls the mouse at each handoff
