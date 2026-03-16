# Deployment

## Backend → Cloud Run

```bash
gcloud run deploy directors-lab-api \
  --source backend/ \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars "GEMINI_API_KEY=<key>,GOOGLE_CLOUD_PROJECT=<proj>,GCS_BUCKET_NAME=<bucket>,FIRESTORE_COLLECTION=scenes,CORS_ORIGINS=https://<project>.web.app"
```

No local Docker needed — Cloud Build handles the container automatically.

## Frontend → Firebase Hosting

```bash
firebase use --add          # link GCP project (one-time)
cd frontend && npm run build
cd .. && firebase deploy --only hosting
```

Firebase Hosting rewrites `/api/**` → Cloud Run. **No `VITE_API_URL` needed.**

## GCS Bucket Setup (one-time)

```bash
gsutil mb -p $PROJECT -l us-central1 gs://$BUCKET
gsutil uniformbucketlevelaccess set on gs://$BUCKET
gsutil iam ch allUsers:objectViewer gs://$BUCKET
```

## Required IAM Roles (service account)

- `Vertex AI User` — Imagen 3, Lyria, Veo 3.1
- `Cloud Datastore User` — Firestore read/write
- `Storage Object Admin` — GCS upload + public URL

## Media URL Pattern

```
Images: https://storage.googleapis.com/{BUCKET}/panels/{scene_id}/panel_{n}.png
Audio:  https://storage.googleapis.com/{BUCKET}/audio/{scene_id}/panel_{n}.wav
Video:  https://storage.googleapis.com/{BUCKET}/video/{scene_id}/panel_{n}.mp4
```

## Related Notes

- [[Architecture]]
