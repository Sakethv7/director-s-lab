# Director's Lab — Teardown & Billing Cleanup Guide

This document covers how to shut down every billable service used in this project.
Run these commands in the **Google Cloud SDK Shell**.

---

## Services Used (and their billing impact)

| Service | Billing trigger |
|---|---|
| Cloud Run | Per request + CPU/memory while running |
| Firebase Hosting | Storage + bandwidth (free tier is generous) |
| Firestore | Reads/writes/storage (free tier covers most usage) |
| Cloud Storage (GCS) | Storage + bandwidth |
| Vertex AI (Imagen 3, Lyria, Veo 2) | Per generation call |
| Cloud Build | Per build minute (first 120 min/day free) |
| Artifact Registry | Container image storage |

---

## Option A — Pause (keep data, stop charges)

### 1. Delete the Cloud Run service
This stops all compute billing immediately. Your data in Firestore and GCS is untouched.

```bash
gcloud run services delete directors-lab-api \
  --region us-central1 \
  --project gemini-live-agent-challenge-26
```

### 2. Unpublish Firebase Hosting
This removes the frontend from the public URL but keeps the project intact.

```bash
firebase hosting:disable \
  --project gemini-live-agent-challenge-26
```

---

## Option B — Full Teardown (delete everything)

Run these in order.

### 1. Delete Cloud Run service
```bash
gcloud run services delete directors-lab-api \
  --region us-central1 \
  --project gemini-live-agent-challenge-26
```

### 2. Delete the GCS bucket and all its contents (images, audio, video)
```bash
gsutil rm -r gs://gemini-hackathon-2026-bucket
```

### 3. Delete all Firestore data (scenes collection)
```bash
gcloud firestore operations list \
  --project gemini-live-agent-challenge-26

# Delete all documents in the scenes collection
gcloud firestore documents delete \
  --project gemini-live-agent-challenge-26 \
  --collection scenes
```
Or delete via the Firebase Console:
**Firestore → scenes collection → Delete collection**

### 4. Delete Artifact Registry images (built by Cloud Build)
```bash
# List repositories first
gcloud artifacts repositories list \
  --project gemini-live-agent-challenge-26 \
  --location us-central1

# Delete the repository (adjust name if different)
gcloud artifacts repositories delete cloud-run-source-deploy \
  --location us-central1 \
  --project gemini-live-agent-challenge-26
```

### 5. Delete Firebase Hosting site
```bash
firebase hosting:disable \
  --project gemini-live-agent-challenge-26
```
Then go to **Firebase Console → Hosting → Delete site** to fully remove it.

### 6. Remove the service account key (local security hygiene)
Delete the JSON key file from your Downloads folder:
```
C:\Users\Adithya\Downloads\gemini-live-agent-challenge-26-434503397f42.json
```
Also revoke it in GCP Console:
**IAM & Admin → Service Accounts → select account → Keys → Delete key**

---

## Option C — Delete the entire GCP project (nuclear option)

This deletes **everything** — all services, data, billing, APIs — with no recovery.

```bash
gcloud projects delete gemini-live-agent-challenge-26
```

Or via console: **GCP Console → IAM & Admin → Manage Resources → select project → Delete**

> The project is held for 30 days before permanent deletion. You can restore it within that window at console.cloud.google.com/cloud-resource-manager.

---

## Verify No Billing Is Running

After teardown, confirm in GCP Console:
- **Cloud Run** → no services listed
- **Cloud Storage** → bucket deleted or empty
- **Artifact Registry** → no repositories
- **Billing → Cost breakdown** → all line items at $0

---

## Free Tier Limits (if keeping project alive)

These services won't bill you within these limits:

| Service | Free tier |
|---|---|
| Cloud Run | 2M requests/month, 360K GB-seconds |
| Firestore | 1 GB storage, 50K reads/day, 20K writes/day |
| Cloud Storage | 5 GB, 1 GB egress/month |
| Firebase Hosting | 10 GB storage, 360 MB/day bandwidth |
| Cloud Build | 120 build-minutes/day |

Vertex AI (Imagen, Lyria, Veo) has **no free tier** — charges apply per generation.
