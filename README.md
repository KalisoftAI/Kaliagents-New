# 🚀 Deploy n8n on Google Cloud Run (Kalisoft Agent Space)

This guide explains how to **deploy n8n** — an automation and workflow engine — to **Google Cloud Run**, with full automation support using a production-ready `deploy.sh` script, or manual step-by-step instructions.

---

## ⚙️ Automated Deployment with deploy.sh

A ready-to-use **`deploy.sh`** script automates:

✅ GCP project setup
✅ Enabling required APIs
✅ Artifact Registry creation
✅ Docker image build & push
✅ Cloud Run deployment
✅ Environment variable configuration

### 📄 `deploy.sh`

```bash
#!/bin/bash
set -e  # Exit immediately if a command exits with a non-zero status

##############################################
# CONFIGURATION
##############################################

# ===== Change these values =====
PROJECT_ID="cool-mile-474408-d8"
REGION="us-central1"
IMAGE_NAME="n8n"
SERVICE_NAME="n8n-service"
REPO_NAME="n8n-repo"

# ===== Optional Environment Variables =====
WEBHOOK_URL="https://${SERVICE_NAME}-${REGION}.a.run.app/"
ENCRYPTION_KEY=$(openssl rand -hex 16)
TIMEZONE="Asia/Kolkata"
ADMIN_USER="admin"
ADMIN_PASS="yourpassword"

##############################################
# SETUP
##############################################

echo "🔧 Setting project: $PROJECT_ID"
gcloud config set project $PROJECT_ID

echo "✅ Enabling required APIs..."
gcloud services enable run.googleapis.com \
    artifactregistry.googleapis.com \
    cloudbuild.googleapis.com

##############################################
# ARTIFACT REGISTRY
##############################################

echo "📦 Creating Artifact Registry repo (if not exists)..."
if ! gcloud artifacts repositories describe $REPO_NAME --location=$REGION >/dev/null 2>&1; then
  gcloud artifacts repositories create $REPO_NAME \
    --repository-format=docker \
    --location=$REGION \
    --description="Docker repo for n8n image"
else
  echo "✅ Repository $REPO_NAME already exists."
fi

##############################################
# BUILD AND PUSH IMAGE
##############################################

echo "🚀 Building and pushing Docker image..."
gcloud builds submit --tag $REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/$IMAGE_NAME

##############################################
# DEPLOY TO CLOUD RUN
##############################################

echo "🌐 Deploying n8n to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
  --image $REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/$IMAGE_NAME \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --port 5678 \
  --set-env-vars "WEBHOOK_URL=${WEBHOOK_URL},N8N_ENCRYPTION_KEY=${ENCRYPTION_KEY},GENERIC_TIMEZONE=${TIMEZONE},N8N_BASIC_AUTH_ACTIVE=true,N8N_BASIC_AUTH_USER=${ADMIN_USER},N8N_BASIC_AUTH_PASSWORD=${ADMIN_PASS}"

##############################################
# FINISH
##############################################

URL=$(gcloud run services describe $SERVICE_NAME --region $REGION --format='value(status.url)')
echo "🎉 Deployment complete!"
echo "🌍 Your n8n instance is live at: $URL"
echo "👤 Login credentials:"
echo "   Username: $ADMIN_USER"
echo "   Password: $ADMIN_PASS"
```

---

### 🧩 Usage

Save the script:

```bash
nano deploy.sh
```

Make it executable:

```bash
chmod +x deploy.sh
```

Run it:

```bash
./deploy.sh
```

---

### 📦 Folder Structure Example

```
n8n-cloudrun/
├── Dockerfile
└── deploy.sh
```

**Dockerfile:**

```dockerfile
FROM n8nio/n8n:latest
EXPOSE 5678
```

---

### ✅ After Successful Run

Output:

```
🎉 Deployment complete!
🌍 Your n8n instance is live at: https://n8n-service-xxxxxx-uc.a.run.app
👤 Login credentials:
   Username: admin
   Password: yourpassword
```

Then, open the URL in your browser to access your **n8n dashboard** 🎨

---

## 🧩 Manual Deployment (Step-by-Step)

If you prefer manual deployment, follow these steps.

### STEP 1 — Set Up Environment

Use **Google Cloud Shell**:

```bash
gcloud config set project sacred-machine-474009-q2
```

---

### STEP 2 — Create Dockerfile

```dockerfile
FROM n8nio/n8n:latest
EXPOSE 5678
```

---

### STEP 3 — Build and Push Docker Image

```bash
REGION=us-central1
PROJECT_ID=sacred-machine-474009-q2
IMAGE_NAME=clipcraftai

gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com

gcloud artifacts repositories create n8n-repo \
  --repository-format=docker \
  --location=$REGION

gcloud builds submit --tag $REGION-docker.pkg.dev/$PROJECT_ID/n8n-repo/$IMAGE_NAME
```

---

### STEP 4 — Deploy to Cloud Run

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

---

### STEP 5 — Configure Environment Variables

| Key                     | Value                                                                                                          |
| ----------------------- | -------------------------------------------------------------------------------------------------------------- |
| WEBHOOK_URL             | [https://clipcraftai-311239505993.us-central1.run.app/](https://clipcraftai-311239505993.us-central1.run.app/) |
| N8N_ENCRYPTION_KEY      | your-long-random-secret                                                                                        |
| GENERIC_TIMEZONE        | Asia/Kolkata                                                                                                   |
| N8N_BASIC_AUTH_ACTIVE   | true                                                                                                           |
| N8N_BASIC_AUTH_USER     | admin                                                                                                          |
| N8N_BASIC_AUTH_PASSWORD | yourpassword                                                                                                   |

Optional (PostgreSQL):

| Key                    | Value            |
| ---------------------- | ---------------- |
| DB_TYPE                | postgresdb       |
| DB_POSTGRESDB_HOST     | my-postgres-host |
| DB_POSTGRESDB_USER     | n8n_user         |
| DB_POSTGRESDB_PASSWORD | supersecret      |
| DB_POSTGRESDB_DATABASE | n8n              |

---

### STEP 6 — (Optional) Add Cloud SQL or Redis

```bash
DB_POSTGRESDB_HOST=/cloudsql/myproject:us-central1:n8n-db
```

Attach Cloud SQL under:

> Cloud Run → Connections → Cloud SQL Connections

---

### STEP 7 — Test Deployment

```bash
curl https://clipcraftai-311239505993.us-central1.run.app
```

If you see the login page or JSON response — success 🎉
Webhooks:

```
https://clipcraftai-311239505993.us-central1.run.app/webhook/myagent
```

---

## 🧠 Custom Domain Mapping

```bash
gcloud run domain-mappings create \
  --service clipcraftai \
  --domain api.yourdomain.com
```

---

## 🧰 Troubleshooting

| Problem                    | Fix                                                             |
| -------------------------- | --------------------------------------------------------------- |
| **PORT not set**           | Cloud Run sets `$PORT` automatically.                           |
| **App crashes**            | Check logs: `gcloud logs read --project=$PROJECT_ID --limit=50` |
| **Webhook not responding** | Activate workflow and check HTTP method (GET/POST).             |

---

## 💰 Cost Overview

| Component           | Description           | Est. Monthly Cost |
| ------------------- | --------------------- | ----------------- |
| Cloud Run (n8n app) | Main running service  | $0 – $5           |
| Artifact Registry   | Stores Docker image   | $0 – $1           |
| Cloud SQL           | Persistent database   | $8 – $25          |
| Cloud Storage       | File/workflow storage | $0 – $1           |
| Cloud Logging       | Log storage           | $0 – $2           |

### Cloud Run Pricing Breakdown

| Resource | Free Tier                  | Price Beyond Free           |
| -------- | -------------------------- | --------------------------- |
| vCPU     | 180,000 vCPU-seconds/month | $0.00002400 per vCPU-second |
| Memory   | 360,000 GiB-seconds/month  | $0.00000250 per GiB-second  |
| Requests | 2 million/month            | $0.40 per million requests  |
| Egress   | 1 GiB/month                | $0.12 per GiB               |

---

### ✅ Total (Small Workload): **$5–$15/month**

Ideal for 1–2 users and light automation workflows.

---

## 💡 Example Scenarios

| Use Case                  | Description                     | Estimated Monthly Cost |
| ------------------------- | ------------------------------- | ---------------------- |
| **Personal Testing**      | 1 user, light workflows, SQLite | 🟩 Free                |
| **Team Agent (SQLite)**   | Up to 3 users sharing workflows | 🟨 $3 – $5/month       |
| **Persistent Production** | Cloud SQL + 10K requests/day    | 🟦 $15 – $25/month     |

---

## 🧩 Summary

You’ve successfully:

1. Automated deployment with `deploy.sh` or used manual Cloud Run setup
2. Built and pushed an n8n Docker image
3. Configured authentication & environment variables
4. Optionally added Cloud SQL for persistence
5. Launched a scalable agent space on **Google Cloud**

---

### 🔗 Useful Links

* [n8n Documentation](https://docs.n8n.io/)
* [Google Cloud Run Docs](https://cloud.google.com/run/docs)
* [Artifact Registry Docs](https://cloud.google.com/artifact-registry/docs)
* [Cloud SQL for PostgreSQL](https://cloud.google.com/sql/docs/postgres)

---

**Author:** Kalisoft
**Project:** ClipCraft AI — Intelligent Automation & Agent Deployment
**Cloud Provider:** Google Cloud (Cloud Run + Artifact Registry + Cloud SQL)
