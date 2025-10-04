# Kaliagents-New

# Deploying n8n on Google Cloud Run with Cloud SQL PostgreSQL

This guide provides specific steps to deploy n8n on Google Cloud Run with persistent storage using Cloud SQL PostgreSQL and proper port handling.

-----

## Step 1: Prepare Your Google Cloud Project

1.  **Create or Select Project:** Create a new Google Cloud project or select an existing one.

2.  **Enable APIs:** Enable the **Cloud Run**, **Cloud SQL Admin**, and **Artifact Registry APIs**.

3.  **Set Project and Region:** Configure your project and region for future commands:

    ```bash
    gcloud config set project YOUR_PROJECT_ID
    gcloud config set run/region YOUR_REGION
    ```

-----

## Step 2: Create Custom Dockerfiles to Handle Port Mapping

Cloud Run expects the application to use the port set in the environment variable `PORT`, but n8n uses `N8N_PORT`. Create two files in your working directory:

### `startup.sh`

```bash
#!/bin/sh
if [ -n "$PORT" ]; then
  export N8N_PORT=$PORT
fi
exec /docker-entrypoint.sh
```

**Permissions:** Make sure it has Unix line endings and execute permissions:

```bash
chmod +x startup.sh
```

### `Dockerfile`

```dockerfile
FROM docker.n8n.io/n8nio/n8n:latest
COPY startup.sh /
USER root
RUN chmod +x /startup.sh
USER node
EXPOSE 5678
ENTRYPOINT ["/bin/sh", "/startup.sh"]
```

-----

## Step 3: Build and Push Docker Image

1.  **Create Artifact Registry Docker Repository:**

    ```bash
    gcloud artifacts repositories create n8n-repo \
        --repository-format=docker \
        --location=$REGION \
        --description="Repository for n8n images"
    ```

2.  **Authenticate Docker with Google Cloud:**

    ```bash
    gcloud auth configure-docker $REGION-docker.pkg.dev
    ```

3.  **Build the Docker Image:** Build for the correct architecture (`linux/amd64`):

    ```bash
    docker build --platform linux/amd64 -t $REGION-docker.pkg.dev/$PROJECT_ID/n8n-repo/n8n:latest .
    ```

4.  **Push the Image:**

    ```bash
    docker push $REGION-docker.pkg.dev/$PROJECT_ID/n8n-repo/n8n:latest
    ```

-----

## Step 4: Set Up Cloud SQL PostgreSQL Database

1.  **Create a Cloud SQL Instance:**

    ```bash
    gcloud sql instances create n8n-db \
        --database-version=POSTGRES_13 \
        --tier=db-f1-micro \
        --region=$REGION \
        --storage-size=10GB \
        --root-password="supersecure-rootpassword"
    ```

2.  **Create Database and User for n8n:**

    ```bash
    gcloud sql databases create n8n --instance=n8n-db
    gcloud sql users create n8n-user --instance=n8n-db --password="supersecure-userpassword"
    ```

-----

## Step 5: Deploy n8n to Cloud Run with Database and Secrets

1.  **Get Cloud SQL Connection Name:**

    ```bash
    export SQL_CONNECTION=$(gcloud sql instances describe n8n-db --format="value(connectionName)")
    ```

2.  **Deploy to Cloud Run:** Deploy your n8n service, linking Cloud SQL, setting environment variables, and enabling basic authentication.

    ```bash
    gcloud run deploy n8n \
      --image=$REGION-docker.pkg.dev/$PROJECT_ID/n8n-repo/n8n:latest \
      --platform=managed \
      --region=$REGION \
      --allow-unauthenticated \
      --port=5678 \
      --cpu=1 \
      --memory=2Gi \
      --min-instances=0 \
      --max-instances=1 \
      --set-env-vars="N8N_PATH=/,N8N_PORT=5678,N8N_PROTOCOL=https,DB_TYPE=postgresdb,DB_POSTGRESDB_DATABASE=n8n,DB_POSTGRESDB_USER=n8n-user,DB_POSTGRESDB_HOST=/cloudsql/$SQL_CONNECTION,DB_POSTGRESDB_PORT=5432,DB_POSTGRESDB_SCHEMA=public,N8N_BASIC_AUTH_USER=admin,N8N_BASIC_AUTH_PASSWORD=yourpassword,EXECUTIONS_PROCESS=main,EXECUTIONS_MODE=regular,GENERIC_TIMEZONE=UTC" \
      --add-cloudsql-instances=$SQL_CONNECTION \
      --service-account=n8n-service-account@$PROJECT_ID.iam.gserviceaccount.com
    ```

      * **Important:** Replace `yourpassword` with a strong password for basic authentication.
      * Ensure the specified `n8n-service-account@YOUR_PROJECT_ID.iam.gserviceaccount.com` has the necessary permissions to connect to the Cloud SQL instance.

-----

## Step 6: Access and Use Your n8n Instance

After deployment, Cloud Run will provide a **public HTTPS URL**.
Use this URL to access the n8n UI. Webhooks and executions will be routed correctly with PostgreSQL persistence for your workflows and executions.

-----

## Notes

  * This setup ensures your **workflows and execution data persist** across container restarts.
  * `min-instances=0` enables your service to **scale-to-zero** when idle, significantly saving costs.
  * The **custom Dockerfile and startup script resolve the Cloud Run port mismatch problem**.
  * Consider using **Google Secret Manager** to store sensitive environment variables securely.
  * Adjust **CPU and memory** based on your expected workload to optimize performance and cost.
  * This approach offers a **scalable, cost-efficient, and low-maintenance solution** for self-hosting n8n on Google Cloud Run with persistent storage and secure access.

-----

## Check Sources

  * [https://github.com/datawranglerai/self-host-n8n-on-gcr](https://github.com/datawranglerai/self-host-n8n-on-gcr)
  * [https://community.n8n.io/t/complete-guide-self-hosting-n8n-on-google-cloud-run-with-postgresql-serverless-cost-effective/195995](https://community.n8n.io/t/complete-guide-self-hosting-n8n-on-google-cloud-run-with-postgresql-serverless-cost-effective/195995)
  * [https://docs.n8n.io/hosting/installation/server-setups/google-cloud/](https://docs.n8n.io/hosting/installation/server-setups/google-cloud/)
  * [https://www.oneclickitsolution.com/centerofexcellence/aiml/n8n-setup-on-gcp-vm](https://www.oneclickitsolution.com/centerofexcellence/aiml/n8n-setup-on-gcp-vm)
  * [https://www.reddit.com/r/n8n/comments/1jcz1v2/i\_created\_a\_complete\_guide\_to\_selfhosting\_n8n\_on/](https://www.reddit.com/r/n8n/comments/1jcz1v2/i_created_a_complete_guide_to_selfhosting_n8n_on/)
  * [https://www.youtube.com/watch?v=NNTbwOCPUww](https://www.youtube.com/watch?v=NNTbwOCPUww)
  * [https://community.n8n.io/t/cloud-run-configuration-of-n8n/59644](https://community.n8n.io/t/cloud-run-configuration-of-n8n/59644)
  * [https://www.youtube.com/watch?v=x49ZiJDIVPQ](https://www.youtube.com/watch?v=x49ZiJDIVPQ)
