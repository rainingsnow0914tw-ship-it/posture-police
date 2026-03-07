#!/bin/bash
# =============================================================
# Posture Police — Automated Deployment Script
# Deploys frontend to Firebase Hosting + backend to Cloud Run
# Created for Gemini Live Agent Hackathon 2026
# =============================================================

set -e  # 任何步驟失敗就停止

PROJECT_ID="project-f30de725-baf2-4498-b70"
REGION="us-central1"
SERVICE_NAME="posture-police-v2"

echo "🐢 Posture Police Deployment Starting..."
echo "📦 Project: $PROJECT_ID"

# ── Step 1: 設定 GCP Project ──────────────────────────────
echo ""
echo "⚙️  Step 1: Setting GCP project..."
gcloud config set project $PROJECT_ID

# ── Step 2: 部署後端到 Cloud Run ──────────────────────────
echo ""
echo "☁️  Step 2: Deploying backend to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
  --source . \
  --region $REGION \
  --allow-unauthenticated \
  --project $PROJECT_ID

# ── Step 3: 部署前端到 Firebase Hosting ───────────────────
echo ""
echo "🔥 Step 3: Deploying frontend to Firebase Hosting..."
cp ~/index.html ~/public/index.html
firebase deploy --only hosting --project $PROJECT_ID

echo ""
echo "✅ Deployment Complete!"
echo "🌐 Frontend: https://$PROJECT_ID.web.app"
echo "⚙️  Backend:  https://$SERVICE_NAME-1069534499581.$REGION.run.app"
