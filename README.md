<div align="center">

[![Gemini Live Agent Challenge](https://img.shields.io/badge/Gemini_Live_Agent_Challenge-2026-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://geminiliveagentchallenge.devpost.com)
&nbsp;&nbsp;
[![Google Cloud](https://img.shields.io/badge/Google_Cloud-Powered-DB4437?style=for-the-badge&logo=googlecloud&logoColor=white)](https://cloud.google.com)
&nbsp;&nbsp;
[![Demo Video](https://img.shields.io/badge/Demo_Video-YouTube-FF0000?style=for-the-badge&logo=youtube&logoColor=white)](https://youtu.be/NJIgIC2jUCM?si=0hmpTEQ2KJKipYfc)
&nbsp;&nbsp;
[![Live App](https://img.shields.io/badge/Live_App-Try_Now-34A853?style=for-the-badge&logo=firebase&logoColor=white)](https://project-f30de725-baf2-4498-b70.web.app)

</div>

# 🐢 Posture Police
> The Live Agent that roasts you back to health.

A hands-free AI desk companion powered by **Gemini Live API** on Google Cloud.  
It detects your slouch in real time — and argues with you until you sit up straight.

## 🌐 Live Demo
- **Frontend:** https://project-f30de725-baf2-4498-b70.web.app
- **Backend:** https://posture-police-v2-1069534499581.us-central1.run.app

## 🏗️ Architecture
- **Frontend:** Firebase Hosting (TensorFlow.js + MediaPipe BlazePose)
- **Backend:** Google Cloud Run — Node.js WebSocket Proxy
- **AI:** Vertex AI — Gemini Live API (`gemini-live-2.5-flash-native-audio`)

## 🚀 Spin-Up Instructions

### Prerequisites
- Node.js 18+
- Google Cloud account with billing enabled
- Firebase CLI: `npm install -g firebase-tools`
- gcloud CLI installed and authenticated

### 1. Clone the repo
```bash
git clone https://github.com/rainingsnow0914tw-ship-it/posture-police.git
cd posture-police
```

### 2. Deploy Backend to Cloud Run
```bash
gcloud config set project YOUR_PROJECT_ID
gcloud run deploy posture-police-v2 \
  --source . \
  --region us-central1 \
  --allow-unauthenticated
```

### 3. Update Frontend WebSocket URL
In `index.html`, find and update:
```javascript
const WS_URL = 'wss://YOUR-CLOUD-RUN-URL';
```

### 4. Deploy Frontend to Firebase
```bash
cp index.html public/index.html
firebase deploy --only hosting
```

### 5. Or use the automated script
```bash
chmod +x deploy.sh
./deploy.sh
```

## 🎮 How to Use
1. Open the app in your browser
2. Click **Calibrate** — sit up straight first!
3. Monitoring begins — slouch and face the consequences
4. Talk back to the AI when the banter window opens
5. Sit up straight to earn your 30-second grace period

> 🌐 **Bilingual:** The agent speaks English by default. Talk back in Traditional Chinese and it switches automatically.

## 🛠️ Tech Stack
| Layer | Technology |
|-------|-----------|
| Vision | TensorFlow.js + MediaPipe BlazePose |
| Frontend | Vanilla JS + Tailwind CSS |
| Hosting | Firebase Hosting |
| Backend | Node.js + Express + WebSocket |
| Cloud | Google Cloud Run (us-central1) |
| AI | Vertex AI — Gemini Live API |
| Language | English (default) + Traditional Chinese (auto-detect) |
| Auth | Workload Identity Federation |

## 📄 License
MIT
