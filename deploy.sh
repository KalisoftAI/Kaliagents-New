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
