#!/usr/bin/env bash
# One-time setup for hosting the MCP server on Google Cloud Run.
#
# Creates: Cloud Run service (placeholder image, real image comes from GitHub Actions),
# Artifact Registry repo, GitHub Workload Identity Federation, a monthly budget and
# the budget-guard function that makes the service private once the budget is used up.
#
# The hosted instance runs without UK keys (UK tools disabled): everyone needing UK
# data runs the server locally with their own transportapi.com credentials.
#
# Usage:
#   PROJECT_ID=my-project BILLING_ACCOUNT=XXXXXX-XXXXXX-XXXXXX ./deploy/gcp-setup.sh
#
# BUDGET_AMOUNT must be in the billing account's currency (e.g. 3CHF or 3EUR).
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID}"
: "${BILLING_ACCOUNT:?set BILLING_ACCOUNT (gcloud billing accounts list)}"
REGION="${REGION:-europe-west1}"
SERVICE="${SERVICE:-mcp-public-transport}"
BUDGET_AMOUNT="${BUDGET_AMOUNT:-3CHF}"
GITHUB_REPO="${GITHUB_REPO:-mirodn/mcp-server-public-transport}"

RUNTIME_SA="mcp-runtime@${PROJECT_ID}.iam.gserviceaccount.com"
DEPLOY_SA="github-deployer@${PROJECT_ID}.iam.gserviceaccount.com"
GUARD_SA="budget-guard@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud config set project "$PROJECT_ID"
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')

echo "==> Enabling APIs"
gcloud services enable \
  run.googleapis.com artifactregistry.googleapis.com \
  iamcredentials.googleapis.com sts.googleapis.com pubsub.googleapis.com \
  billingbudgets.googleapis.com cloudfunctions.googleapis.com cloudbuild.googleapis.com \
  eventarc.googleapis.com cloudresourcemanager.googleapis.com

echo "==> Service accounts"
gcloud iam service-accounts create mcp-runtime --display-name="MCP server runtime"
gcloud iam service-accounts create github-deployer --display-name="GitHub Actions deployer"
gcloud iam service-accounts create budget-guard --display-name="Budget guard"

echo "==> Artifact Registry"
gcloud artifacts repositories create mcp --repository-format=docker --location="$REGION"
gcloud artifacts repositories add-iam-policy-binding mcp --location="$REGION" \
  --member="serviceAccount:${DEPLOY_SA}" --role=roles/artifactregistry.writer

echo "==> Cloud Run service (placeholder image, limits keep costs bounded)"
# These settings persist across deploys; the GitHub workflow only swaps the image.
gcloud run deploy "$SERVICE" \
  --image=us-docker.pkg.dev/cloudrun/container/hello \
  --region="$REGION" \
  --service-account="$RUNTIME_SA" \
  --min-instances=0 --max-instances=1 \
  --cpu=1 --memory=512Mi --concurrency=80 --timeout=60 \
  --set-env-vars=MCP_STATELESS=true \
  --no-allow-unauthenticated
gcloud run services add-iam-policy-binding "$SERVICE" --region="$REGION" \
  --member=allUsers --role=roles/run.invoker

echo "==> GitHub Workload Identity Federation"
gcloud iam workload-identity-pools create github --location=global --display-name="GitHub Actions"
gcloud iam workload-identity-pools providers create-oidc github \
  --location=global --workload-identity-pool=github \
  --issuer-uri=https://token.actions.githubusercontent.com \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='${GITHUB_REPO}'"
gcloud iam service-accounts add-iam-policy-binding "$DEPLOY_SA" \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github/attribute.repository/${GITHUB_REPO}"
# Deployer may roll out revisions but not change who can call the service
gcloud run services add-iam-policy-binding "$SERVICE" --region="$REGION" \
  --member="serviceAccount:${DEPLOY_SA}" --role=roles/run.developer
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" \
  --member="serviceAccount:${DEPLOY_SA}" --role=roles/iam.serviceAccountUser

echo "==> Budget + guard"
gcloud pubsub topics create budget-alerts
gcloud billing budgets create \
  --billing-account="$BILLING_ACCOUNT" \
  --display-name="${SERVICE} monthly" \
  --budget-amount="$BUDGET_AMOUNT" \
  --filter-projects="projects/${PROJECT_ID}" \
  --credit-types-treatment=include-all-credits \
  --threshold-rule=percent=0.5 \
  --threshold-rule=percent=0.9 \
  --threshold-rule=percent=1.0 \
  --notifications-rule-pubsub-topic="projects/${PROJECT_ID}/topics/budget-alerts"

# Guard may only touch this one service
gcloud run services add-iam-policy-binding "$SERVICE" --region="$REGION" \
  --member="serviceAccount:${GUARD_SA}" --role=roles/run.admin
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${GUARD_SA}" --role=roles/eventarc.eventReceiver --condition=None
# Newer projects build functions with the compute default SA, which lacks this role
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role=roles/cloudbuild.builds.builder --condition=None
echo "    waiting for IAM propagation..."
sleep 60

gcloud functions deploy budget-guard \
  --gen2 --runtime=python312 --region="$REGION" \
  --source="$(dirname "$0")/budget-guard" --entry-point=stop_on_budget \
  --trigger-topic=budget-alerts \
  --service-account="$GUARD_SA" --trigger-service-account="$GUARD_SA" \
  --set-env-vars="SERVICE_NAME=projects/${PROJECT_ID}/locations/${REGION}/services/${SERVICE}" \
  --max-instances=1 --no-allow-unauthenticated
gcloud functions add-invoker-policy-binding budget-guard --region="$REGION" \
  --member="serviceAccount:${GUARD_SA}"

cat <<EOF

Done. Set these GitHub repository variables (Settings > Secrets and variables > Actions > Variables):

  gh variable set GCP_PROJECT_ID   --body "${PROJECT_ID}"
  gh variable set GCP_REGION       --body "${REGION}"
  gh variable set GCP_SERVICE      --body "${SERVICE}"
  gh variable set GCP_DEPLOY_SA    --body "${DEPLOY_SA}"
  gh variable set GCP_WIF_PROVIDER --body "projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github/providers/github"

Then run the "Deploy to Cloud Run" workflow once (Actions tab) to replace the placeholder image.
Service URL: $(gcloud run services describe "$SERVICE" --region="$REGION" --format='value(status.url)')/mcp
EOF
