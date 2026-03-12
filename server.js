// server.js - Posture Police v2
// 功能：WebSocket Proxy，把前端的音訊串流轉發給 Gemini Live API
// 同時保護 Service Account Key，前端完全看不到認證資訊

const express = require('express');
const cors = require('cors');
const { WebSocketServer, WebSocket } = require('ws');
const { GoogleAuth } = require('google-auth-library');
const http = require('http');

const app = express();
app.use(cors());
app.use(express.json());

// 健康檢查（Cloud Run 需要這個）
app.get('/', (req, res) => {
    res.json({ status: '🐢 Posture Police v2 Live Agent is on duty' });
});


// ================================================================
// HTTP POST /roast
// ================================================================
const { VertexAI } = require('@google-cloud/vertexai');

app.post('/roast', async (req, res) => {
    try {
        const { userReply } = req.body || {};
        const vertexAI = new VertexAI({ project: PROJECT_ID, location: REGION });
        const model = vertexAI.getGenerativeModel({
            model: 'gemini-2.0-flash-001',
            systemInstruction: SYSTEM_INSTRUCTION
        });
        const prompt = userReply ? `用戶頂嘴說：「${userReply}」，嘴回去！` : 'SLOUCH_DETECTED';
        const result = await model.generateContent(prompt);
        const text = result.response.candidates[0].content.parts[0].text;
        res.json({ roast: text.trim() });
    } catch (err) {
        console.error('/roast 錯誤:', err.message);
        res.status(500).json({ error: err.message });
    }
});

const server = http.createServer(app);

// ================================================================
// WebSocket Server：接受來自前端的連線
// ================================================================
const wss = new WebSocketServer({ server });

// Gemini Live API 的 Vertex AI endpoint
// 格式：{region}-aiplatform.googleapis.com
const REGION = process.env.REGION || 'us-central1';
const PROJECT_ID = process.env.GOOGLE_CLOUD_PROJECT;
const MODEL = 'gemini-live-2.5-flash-native-audio'; // Live API 專用模型

// 毒舌刑警的系統提示詞
const SYSTEM_INSTRUCTION = `你是一個名叫「姿勢刑警」的毒舌AI語音教練。
你正在即時監控用戶的坐姿。你的個性是：犀利、幽默、毒舌，但骨子裡是為用戶好。

規則：
1. 當系統通知你「SLOUCH_DETECTED」時，立刻用一句話（20字以內）毒舌嘲諷用戶駝背，命令他坐直
2. 當用戶語音頂嘴時，嘴回去，更犀利，30字以內
3. 當用戶坐直了系統通知「POSTURE_OK」時，給一句簡短的認可（可以帶點不情願）
4. 語言規則：預設用英文回應，偵測到用戶說繁體中文才切換成繁體中文。
   - 預設 → 用英文回應
   - 用戶說繁體中文 → 切換成繁體中文回應
   - 用戶說英文 → 維持英文回應
   - 系統自動觸發（SLOUCH_DETECTED / POSTURE_OK）→ 預設用英文
5. 語氣要像一個不耐煩但有責任心的私人教練`;

// ================================================================
// 取得 Vertex AI Access Token（用 Service Account）
// ================================================================
async function getAccessToken() {
    // 優先用環境變數裡的 Service Account JSON
    // Cloud Run 部署時會把 JSON 內容放進 GOOGLE_APPLICATION_CREDENTIALS_JSON
    if (process.env.GOOGLE_APPLICATION_CREDENTIALS_JSON) {
        const credentials = JSON.parse(process.env.GOOGLE_APPLICATION_CREDENTIALS_JSON);
        const auth = new GoogleAuth({
            credentials,
            scopes: ['https://www.googleapis.com/auth/cloud-platform']
        });
        const client = await auth.getClient();
        const token = await client.getAccessToken();
        return token.token;
    }

    // 本地開發時用 GOOGLE_APPLICATION_CREDENTIALS 環境變數指向 JSON 檔案路徑
    const auth = new GoogleAuth({
        scopes: ['https://www.googleapis.com/auth/cloud-platform']
    });
    const client = await auth.getClient();
    const token = await client.getAccessToken();
    return token.token;
}

// ================================================================
// 每個前端連線都會建立一個對應的 Gemini Live API 連線
// ================================================================
const ipConnections = new Map();
const MAX_PER_IP = 2;  // 允許2條，給重連緩衝空間

wss.on('connection', async (frontendWs, req) => {
  const ip = req.headers['x-forwarded-for'] || req.socket.remoteAddress;
  const count = ipConnections.get(ip) || 0;
  if (count >= MAX_PER_IP) {
    frontendWs.close(1008, 'Too many connections');
    console.log('已拒絕IP: ' + ip);
    return;
  }
  ipConnections.set(ip, count + 1);

  // 每IP每天累計使用時長最多60分鐘
  const dayKey = ip + '_day_' + new Date().toISOString().slice(0,10);
  const dayUsed = ipConnections.get(dayKey) || 0;
  if (dayUsed >= 60 * 60 * 1000) {
    frontendWs.close(1008, 'Daily time limit reached');
    console.log('IP每日時長超限: ' + ip);
    return;
  }

  // 訊息頻率限制（每秒最多10則）
  let msgCount = 0;
  let msgTimer = setInterval(() => { msgCount = 0; }, 1000);

  // 10分鐘會話限制
  const SESSION_LIMIT = 10 * 60 * 1000;
  const WARNING_TIME = 8 * 60 * 1000;

  const warningTimer = setTimeout(() => {
    if (frontendWs.readyState === 1) {
      // 8分鐘警告，發送給後端轉給Gemini說出來
      frontendWs.send(JSON.stringify({
        type: 'system_message',
        text: 'SYSTEM: Please tell the user in English: You have been using Posture Police for 8 minutes. Session will end in 2 minutes. Thank you for trying!'
      }));
    }
  }, WARNING_TIME);

  const sessionTimer = setTimeout(() => {
    console.log('會話時間到，斷線IP: ' + ip);
    frontendWs.close(1000, 'Session limit reached');
  }, SESSION_LIMIT);

  frontendWs.on('message', (rawData) => {
    // 頻率限制
    msgCount++;
    if (msgCount > 60) {
      console.log('訊息頻率超限: ' + ip);
      return;
    }
  });

  const sessionStart = Date.now();
  frontendWs.on('close', () => {
    clearTimeout(warningTimer);
    clearTimeout(sessionTimer);
    clearInterval(msgTimer);
    // 記錄本次session時長到每日累計
    const sessionDuration = Date.now() - sessionStart;
    const dayKey = ip + '_day_' + new Date().toISOString().slice(0,10);
    const dayUsed = ipConnections.get(dayKey) || 0;
    ipConnections.set(dayKey, dayUsed + sessionDuration);
    console.log('IP ' + ip + ' 今日已用: ' + Math.round((dayUsed + sessionDuration)/60000) + ' 分鐘');
  });

  // 機器人偵測：120秒內沒有任何posture_event就踢掉
  let activityTimer = setTimeout(() => {
    console.log('疑似機器人，踢掉IP: ' + ip);
    frontendWs.close(1008, 'No activity detected');
  }, 120000);

  frontendWs.on('message', (data) => {
    // 有訊息進來就重置計時器
    clearTimeout(activityTimer);
    activityTimer = setTimeout(() => {
      console.log('長時間無活動，踢掉IP: ' + ip);
      frontendWs.close(1008, 'Inactivity timeout');
    }, 120000);
  });

  frontendWs.on('close', () => {
    clearTimeout(activityTimer);
    const c = ipConnections.get(ip) || 1;
    if (c <= 1) ipConnections.delete(ip);
    else ipConnections.set(ip, c - 1);
  });
    console.log('前端已連線');

    let geminiWs = null;
    let isGeminiReady = false;
    // 在 Gemini 準備好之前暫存前端送來的音訊
    const audioQueue = [];

    try {
        // 取得 Access Token
        const accessToken = await getAccessToken();

        // 建立連往 Gemini Live API 的 WebSocket
        const geminiUrl = `wss://${REGION}-aiplatform.googleapis.com/ws/google.cloud.aiplatform.v1beta1.LlmBidiService/BidiGenerateContent`;

        geminiWs = new WebSocket(geminiUrl, {
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                'Content-Type': 'application/json'
            }
        });

        // ---- Gemini WebSocket 事件 ----

        geminiWs.on('open', () => {
            console.log('已連線到 Gemini Live API');

            // 第一步：送出 setup 訊息，告訴 Gemini 這個 session 的設定
            const setupMessage = {
                setup: {
                    model: `projects/${PROJECT_ID}/locations/${REGION}/publishers/google/models/${MODEL}`,
                    generation_config: {
                        response_modalities: ['AUDIO'], // 要求 Gemini 直接回傳音訊
                        speech_config: {
                            voice_config: {
                                prebuilt_voice_config: {
                                    voice_name: 'Aoede' // 女聲，適合毒舌刑警角色
                                }
                            }
                        }
                    },
                    system_instruction: {
                        parts: [{ text: SYSTEM_INSTRUCTION }]
                    }
                }
            };

            geminiWs.send(JSON.stringify(setupMessage));
        });

        geminiWs.on('message', (data) => {
            try {
                const message = JSON.parse(data.toString());

                // setup 完成，Gemini 準備好了
                if (message.setupComplete) {
                    console.log('Gemini Live API setup 完成');
                    isGeminiReady = true;

                    // 通知前端 Gemini 已就緒
                    if (frontendWs.readyState === WebSocket.OPEN) {
                        frontendWs.send(JSON.stringify({ type: 'ready' }));
                    }

                    // 把排隊的音訊全部送出去
                    while (audioQueue.length > 0) {
                        const queued = audioQueue.shift();
                        geminiWs.send(queued);
                    }
                    return;
                }

                // 把 Gemini 的回應轉發給前端（轉成 string 確保前端能 JSON.parse）
                if (frontendWs.readyState === WebSocket.OPEN) {
                    frontendWs.send(data.toString());
                }

            } catch (e) {
                // binary 音訊 → 轉 base64 JSON 給前端
                if (frontendWs.readyState === WebSocket.OPEN) {
                    const b64 = Buffer.from(data).toString('base64');
                    frontendWs.send(JSON.stringify({
                        serverContent: {
                            modelTurn: {
                                parts: [{ inlineData: { mimeType: 'audio/pcm', data: b64 } }]
                            }
                        }
                    }));
                }
            }
        });

        geminiWs.on('error', (err) => {
            console.error('Gemini WebSocket 錯誤:', err.message);
            if (frontendWs.readyState === WebSocket.OPEN) {
                frontendWs.send(JSON.stringify({
                    type: 'error',
                    message: 'Gemini 連線錯誤：' + err.message
                }));
            }
        });

        geminiWs.on('close', (code, reason) => {
            console.log(`Gemini WebSocket 關閉: ${code} ${reason}`);
            if (frontendWs.readyState === WebSocket.OPEN) {
                frontendWs.send(JSON.stringify({ type: 'gemini_closed' }));
            }
        });

    } catch (err) {
        console.error('建立 Gemini 連線失敗:', err.message);
        if (frontendWs.readyState === WebSocket.OPEN) {
            frontendWs.send(JSON.stringify({
                type: 'error',
                message: '後端初始化失敗：' + err.message
            }));
        }
        return;
    }

    // ---- 前端 WebSocket 事件 ----

    frontendWs.on('message', (data) => {
        try {
            // 嘗試解析 JSON（文字指令，例如姿勢事件）
            const message = JSON.parse(data.toString());

            if (message.type === 'posture_event') {
                console.log('收到 posture_event:', message.event);
                // 把姿勢事件轉成文字送給 Gemini
                // 例如：「SLOUCH_DETECTED」或「POSTURE_OK」
                const textMessage = {
                    clientContent: {
                        turns: [{
                            role: 'user',
                            parts: [{ text: message.event }]
                        }],
                        turnComplete: true
                    }
                };

                if (geminiWs && geminiWs.readyState === WebSocket.OPEN) {
                    if (isGeminiReady) {
                        geminiWs.send(JSON.stringify(textMessage));
                    } else {
                        audioQueue.push(JSON.stringify(textMessage));
                    }
                }
                return;
            }

            if (message.type === 'audio_chunk') {
                // 前端送來的麥克風音訊（base64 編碼的 PCM）
                // 包成 Gemini Live API 格式轉發
                const audioMessage = {
                    realtimeInput: {
                        mediaChunks: [{
                            mimeType: 'audio/pcm',
                            data: message.data // base64 PCM 16kHz mono
                        }]
                    }
                };

                if (geminiWs && geminiWs.readyState === WebSocket.OPEN) {
                    if (isGeminiReady) {
                        geminiWs.send(JSON.stringify(audioMessage));
                    } else {
                        audioQueue.push(JSON.stringify(audioMessage));
                    }
                }
                return;
            }

        } catch (e) {
            // 不是 JSON，忽略
        }
    });

    frontendWs.on('close', () => {
        console.log('前端已斷線，關閉 Gemini 連線');
        if (geminiWs && geminiWs.readyState === WebSocket.OPEN) {
            geminiWs.close();
        }
    });

    frontendWs.on('error', (err) => {
        console.error('前端 WebSocket 錯誤:', err.message);
        if (geminiWs && geminiWs.readyState === WebSocket.OPEN) {
            geminiWs.close();
        }
    });
});

// ================================================================
// 啟動 Server
// ================================================================
const PORT = process.env.PORT || 8080;
server.listen(PORT, () => {
    console.log(`🐢 Posture Police v2 後端啟動，port ${PORT}`);
    console.log(`Project: ${PROJECT_ID}, Region: ${REGION}`);
});
