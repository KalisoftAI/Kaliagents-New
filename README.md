# 🚀 Deploy n8n on Google Cloud Run (Kalisoft Agent Space)

This guide explains how to **deploy n8n** — an automation and workflow engine — to **Google Cloud Run**, with support for Docker, Artifact Registry, and environment configuration.

---

## 🧩 STEP 1: Set Up Your Environment

### Option 1 — Use **Google Cloud Shell** (Recommended)

No local setup required.

1. Go to **[Google Cloud Console](https://console.cloud.google.com)**
2. Open **Cloud Shell** (top-right terminal icon)
3. Confirm your project:

```bash
gcloud config set project sacred-machine-474009-q2
```

---

## 🐳 STEP 2: Create Dockerfile for n8n

Create a new file named `Dockerfile` in your project root:

```dockerfile
FROM n8nio/n8n:latest

# Optional: copy custom workflows or credentials
# COPY .n8n /home/node/.n8n

# Cloud Run automatically uses the PORT environment variable
EXPOSE 5678
```

> 💡 If you are deploying a custom backend (e.g. Django + yt-dlp), your Dockerfile will differ.
> Paste your backend code here for adaptation if needed.

---

## 🏗️ STEP 3: Build and Push Docker Image to Artifact Registry

Replace variables as needed:

```bash
REGION=us-central1
PROJECT_ID=sacred-machine-474009-q2
IMAGE_NAME=clipcraftai
```

### Enable Required APIs

```bash
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com
```

### Create Artifact Registry Repository (One-Time)

```bash
gcloud artifacts repositories create n8n-repo \
  --repository-format=docker \
  --location=$REGION
```

### Build and Push Docker Image

```bash
gcloud builds submit --tag $REGION-docker.pkg.dev/$PROJECT_ID/n8n-repo/$IMAGE_NAME
```

---

## ☁️ STEP 4: Deploy to Cloud Run

Deploy your image with:

```bash
gcloud run deploy clipcraftai \
  --image $REGION-docker.pkg.dev/$PROJECT_ID/n8n-repo/$IMAGE_NAME \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --port 5678
```

Once complete, you’ll get a live URL like:

```
https://clipcraftai-311239505993.us-central1.run.app
```

🎉 This is your **live n8n instance**.

---

## ⚙️ STEP 5: Configure Environment Variables

Go to:
**Cloud Run → Your Service → Edit & Deploy New Revision → Environment Variables**

Example configuration:

| Key                     | Value                                                                                                          |
| ----------------------- | -------------------------------------------------------------------------------------------------------------- |
| WEBHOOK_URL             | [https://clipcraftai-311239505993.us-central1.run.app/](https://clipcraftai-311239505993.us-central1.run.app/) |
| N8N_ENCRYPTION_KEY      | your-long-random-secret                                                                                        |
| GENERIC_TIMEZONE        | Asia/Kolkata                                                                                                   |
| N8N_BASIC_AUTH_ACTIVE   | true                                                                                                           |
| N8N_BASIC_AUTH_USER     | admin                                                                                                          |
| N8N_BASIC_AUTH_PASSWORD | yourpassword                                                                                                   |

### Optional: Database Configuration

If using PostgreSQL instead of local SQLite:

| Key                    | Value            |
| ---------------------- | ---------------- |
| DB_TYPE                | postgresdb       |
| DB_POSTGRESDB_HOST     | my-postgres-host |
| DB_POSTGRESDB_USER     | n8n_user         |
| DB_POSTGRESDB_PASSWORD | supersecret      |
| DB_POSTGRESDB_DATABASE | n8n              |

SQLite (default) is fine for light workflows and will persist if you attach a **Cloud Storage volume**.

---

## 🔐 STEP 6: (Optional) Add Cloud SQL or Redis

For production or multi-agent setups, use **Cloud SQL (PostgreSQL)** for persistence.

Example connection:

```bash
DB_POSTGRESDB_HOST=/cloudsql/myproject:us-central1:n8n-db
```

Then, attach your **Cloud SQL connection** under:

> Cloud Run → Connections → Cloud SQL Connections

---

## ✅ STEP 7: Test Deployment

Once deployed, test:

```bash
curl https://clipcraftai-311239505
```
