Perfect 🔥 — below is a **complete, production-grade `README.md`** you can put in your GitHub repo.

It documents **everything**:
✅ setup
✅ Cloud Run deployment
✅ connecting n8n agents
✅ website integration
✅ cost breakdown

This README assumes your Cloud Run service will live at
`https://clipcraftai-311239505993.us-central1.run.app`
and your project ID is `sacred-machine-474009-q2`.

---

```markdown
# 🚀 n8n Cloud Run Deployment — AI Agent Automation Platform

This guide explains **how to deploy n8n (or AI agent backend)** on **Google Cloud Run**  
with full setup, cost estimates, and website integration instructions.

---

## 📋 Overview

You will deploy an **n8n-based AI agent system** that can:
- Run custom automation workflows
- Connect to OpenAI or any API
- Trigger from your website via webhooks
- Scale automatically with usage (Cloud Run)

Example deployed endpoint:
```

[https://clipcraftai-311239505993.us-central1.run.app](https://clipcraftai-311239505993.us-central1.run.app)

````

---

## 🧩 Prerequisites

Before you begin, make sure you have:
- A **Google Cloud project** (e.g. `sacred-machine-474009-q2`)
- **Billing enabled**
- **Cloud Shell** or local **gcloud CLI**
- Basic knowledge of Docker

---

## ⚙️ 1. Setup Environment

Open **Google Cloud Shell** or your local terminal.

```bash
# Configure your project and region
gcloud config set project sacred-machine-474009-q2
export REGION=us-central1
export PROJECT_ID=sacred-machine-474009-q2
export IMAGE_NAME=clipcraftai
````

Enable required APIs:

```bash
gcloud services enable run.googleapis.com \
    artifactregistry.googleapis.com \
    cloudbuild.googleapis.com
```

---

## 🐳 2. Create a Dockerfile

If you are deploying **n8n**, use this minimal `Dockerfile`:

```Dockerfile
# Dockerfile
FROM n8nio/n8n:latest

# Expose Cloud Run port
EXPOSE 5678
```

If you are deploying your **custom backend** (e.g. Django + yt-dlp),
adjust this file to fit your app’s `requirements.txt` and `CMD`.

---

## 🏗️ 3. Build and Push the Image

Create a Docker Artifact Registry:

```bash
gcloud artifacts repositories create n8n-repo \
  --repository-format=docker \
  --location=$REGION
```

Build and push:

```bash
gcloud builds submit --tag $REGION-docker.pkg.dev/$PROJECT_ID/n8n-repo/$IMAGE_NAME
```

---

## ☁️ 4. Deploy to Cloud Run

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

When the deployment finishes, you’ll get:

```
Service URL: https://clipcraftai-311239505993.us-central1.run.app
```

---

## 🔧 5. Configure Environment Variables

In Google Cloud Console → Cloud Run → **Edit & Deploy New Revision** → **Environment variables**, add:

| Variable                  | Example                                                 | Description                    |
| ------------------------- | ------------------------------------------------------- | ------------------------------ |
| `WEBHOOK_URL`             | `https://clipcraftai-311239505993.us-central1.run.app/` | Public endpoint                |
| `N8N_ENCRYPTION_KEY`      | `longrandomstring`                                      | Encryption key for credentials |
| `GENERIC_TIMEZONE`        | `Asia/Kolkata`                                          | Your timezone                  |
| `N8N_BASIC_AUTH_ACTIVE`   | `true`                                                  | Enable login protection        |
| `N8N_BASIC_AUTH_USER`     | `admin`                                                 | Username                       |
| `N8N_BASIC_AUTH_PASSWORD` | `strongpassword`                                        | Password                       |

Optional (for persistence):

```bash
DB_TYPE=postgresdb
DB_POSTGRESDB_HOST=/cloudsql/myproject:us-central1:n8n-db
DB_POSTGRESDB_USER=n8n_user
DB_POSTGRESDB_PASSWORD=supersecret
DB_POSTGRESDB_DATABASE=n8n
```

---

## 🧠 6. Create and Deploy AI Agents in n8n

Once n8n is running:

1. Go to your deployed URL and log in.
2. Create a new **workflow** with a **Webhook Trigger** node.

   * Method: `POST`
   * Path: `ai-agent`
3. Add nodes like:

   * `OpenAI` → for generating text
   * `HTTP Request` → to fetch APIs
   * `Google Sheets` / `Slack` → for actions
4. End with a `Respond to Webhook` node:

   ```json
   {
     "status": "success",
     "response": "AI generated result here..."
   }
   ```
5. Activate the workflow.

Your webhook endpoint will be:

```
https://clipcraftai-311239505993.us-central1.run.app/webhook/ai-agent
```

Test:

```bash
curl -X POST https://clipcraftai-311239505993.us-central1.run.app/webhook/ai-agent \
  -H "Content-Type: application/json" \
  -d '{"topic": "AI in video editing"}'
```

---

## 💻 7. Integrate Agent on Your Website

Example HTML + JavaScript snippet:

```html
<form id="aiForm">
  <input id="userInput" placeholder="Enter a topic..." />
  <button type="submit">Generate</button>
</form>
<div id="result"></div>

<script>
  document.getElementById('aiForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const topic = document.getElementById('userInput').value;
    const res = await fetch('https://clipcraftai-311239505993.us-central1.run.app/webhook/ai-agent', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ topic })
    });
    const data = await res.json();
    document.getElementById('result').innerText = data.response;
  });
</script>
```

✅ This allows users to interact with your n8n agent directly from your website.

---

## 🔐 8. Security Best Practices

* Use **Basic Auth** or API key headers in webhook validation:

  ```js
  $json.headers['x-api-key'] === 'your-secret-key'
  ```
* Restrict credentials visibility in n8n UI.
* Avoid exposing sensitive nodes publicly.

---

## 💰 9. Cost Breakdown

| Component                    | Free Tier                                | Approx. Monthly Cost | Notes               |
| ---------------------------- | ---------------------------------------- | -------------------- | ------------------- |
| **Cloud Run (n8n)**          | 2M requests, 180k vCPU-sec, 360k GiB-sec | **$0 – $5**          | Scales to zero      |
| **Artifact Registry**        | 0.5 GB                                   | **$0 – $1**          | Stores Docker image |
| **Cloud SQL (optional)**     | –                                        | **$8 – $25**         | Persistent DB       |
| **Cloud Storage (optional)** | 5 GB                                     | **$0 – $1**          | File storage        |
| **Cloud Logging**            | 50 GB                                    | **$0 – $2**          | Usage-based         |
| **TOTAL**                    |                                          | **$0 – $30/month**   | Typical range       |

### 💡 Example Scenarios

| Use Case              | Description             | Total Est.     |
| --------------------- | ----------------------- | -------------- |
| Personal Testing      | 1 user, light use       | **Free**       |
| Team Agent (SQLite)   | 3 users                 | **$3–$5/mo**   |
| Persistent Production | Cloud SQL + 10K req/day | **$15–$25/mo** |

---

## 🧰 10. Monitoring and Maintenance

```bash
# Check logs
gcloud logs read --project=$PROJECT_ID --limit=50

# Redeploy with changes
gcloud run deploy clipcraftai \
  --image $REGION-docker.pkg.dev/$PROJECT_ID/n8n-repo/$IMAGE_NAME \
  --region $REGION
```

---

## 🌐 11. (Optional) Use Custom Domain

```bash
gcloud run domain-mappings create \
  --service clipcraftai \
  --domain api.yourdomain.com
```

Then configure DNS (CNAME → ghs.googlehosted.com).

---

## 🧱 12. Optional: Use Cloud SQL Alternative

If you want to stay below $5/month:

* Use **SQLite** (default in n8n)
* Mount **Cloud Storage** as volume for basic persistence
* Avoid Cloud SQL until you scale

---

## ✅ Final Result

Your deployed service:

```
https://clipcraftai-311239505993.us-central1.run.app
```

Example agent webhook:

```
https://clipcraftai-311239505993.us-central1.run.app/webhook/ai-agent
```

Example website request:

```bash
curl -X POST https://clipcraftai-311239505993.us-central1.run.app/webhook/ai-agent \
  -H "Content-Type: application/json" \
  -d '{"topic":"AI short video ideas"}'
```

Response:

```json
{
  "status": "success",
  "response": "Here are 5 short AI video ideas..."
}
```

---

## 🧾 License

This project setup is provided for educational and personal use.
© 2025 ClipCraftAI — All rights reserved.

```

---

Would you like me to **add a ready-to-deploy `cloudbuild.yaml`** (so you can deploy from GitHub with one command: `gcloud builds submit`)?  
It automates building, pushing, and deploying to Cloud Run in one step.
```
