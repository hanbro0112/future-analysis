# PTT Stock 板盤中/盤後閒聊功能

## 功能說明

每分鐘由 Cloud Scheduler 觸發 `crawl_ptt_chat`：
1. 抓取 PTT Stock 板當天的「盤中閒聊」「盤後閒聊」文章推文
2. 用推文指紋（fingerprint）當增量游標，只寫入新增的部分
3. 寫入 Firestore `pttThreads` / `pttPosts`

前端在網頁右下角提供彈窗顯示，並記錄使用者捲動到的已讀位置。

## 盤中/盤後與日期判斷邏輯

- **盤中閒聊**：平日 08:30-13:59
- **盤後閒聊**：平日 14:00 ~ 隔天 08:30；假日（週六、週日）整天延續盤後閒聊，
  所以週五的盤後閒聊會一路延續到下週一 08:30
- 只排除週六、週日，沒有國定假日日曆，與 `daily_report.py` 的 `is_trading_day()` 現況一致

## 檔案結構

```
apps/functions/
├── ptt_chat.py                  # PTT 閒聊爬蟲模組 + Cloud Functions entry point
├── test_ptt_chat.py             # pytest 單元測試（mock，不連外網/Firestore）
├── test_ptt_chat_manual.py      # 手動觸發腳本（會真的打 ptt.cc + 寫入 Firestore）
└── README_PTT_CHAT.md           # 本文件

web/app/
├── lib/pttSession.ts            # 盤中/盤後與日期判斷（前端版本，邏輯與 ptt_chat.py 一致）
├── lib/firestoreApi.ts          # subscribeToPttPosts / getPttReadState / savePttReadState / getPttWindowSize / savePttWindowSize
├── components/PttChatWidget.tsx # 右下角彈窗元件
└── types/pttChat.ts             # PttSession / PttPush 型別定義
```

## Firestore Schema

```
pttThreads/{session}
  { date: string, article_url: string, last_fingerprint: string | null, updated_at }

pttPosts/{date}_{session}
  { posts: [ { userid, content, push_tag, time }, ... ], updated_at }

users/{uid}/setting/pttReadState
  {
    intraday: { date: string, last_read_index: number },
    afterhours: { date: string, last_read_index: number },
    width: number,
    height: number,
  }
```

- `session`：`intraday`（盤中閒聊）| `afterhours`（盤後閒聊）
- `date`：`YYYYMMDD`
- `pttThreads` **只維護 intraday/afterhours 兩份文件**，不依日期累積，隔天會直接覆蓋掉
  前一天的內容；文件內用 `date` 欄位記錄目前內容屬於哪一天，讀取時若 `date` 跟查詢的日期
  不同，代表是前一天殘留的舊資料，視為不存在（`article_url` 當作沒鎖定）
- `users/{uid}/setting/pttReadState` 是**單一文件**，盤中/盤後的已讀位置各自存在
  `intraday`/`afterhours` 巢狀欄位（同樣用內部的 `date` 判斷是否為前一天舊資料，不同則視為未讀），
  視窗大小（`width`/`height`）也存在同一份文件；寫入時用 dot-notation（例如
  `intraday.last_read_index`）做局部更新，彼此不會互相覆蓋，捲動位置與拖曳調整視窗大小都是
  「停止操作 10 秒後才寫入」的 debounce
- `pttPosts` 才是實際聊天內容，依日期各自保留歷史，整篇文章的推文存在同一個文件的
  `posts` 陣列（用 `ArrayUnion` 附加），沒有分片機制，超過 Firestore 單一文件 1 MiB
  上限時後續推文會寫入失敗

## 爬蟲流程（每分鐘執行一次）

1. 讀 `pttThreads/{session}`，若文件的 `date` 等於今天且有 `article_url` 就跳到步驟 3
2. 沒有（或 `date` 是前一天殘留的舊資料）就去板面 index (`bbs/Stock/index.html`) 找當天對應文章：
   從最新頁開始找，找不到就往前翻頁（較舊），最多翻到 4 頁（最新頁 + 3 頁），還是找不到就結束本次；
   找到後連同 `date` 一起覆蓋寫入 `pttThreads/{session}`，`last_fingerprint` 歸零
3. 抓文章頁推文，用 `last_fingerprint` 找出新增的部分
   （指紋在畫面上找不到代表被 PTT 隱藏吃掉了，視為全部新增，記警告 log）
4. 用 `ArrayUnion` 寫入 `pttPosts.posts`，並更新 `pttThreads.last_fingerprint`

## 已知限制

- PTT 網頁版推文數過多時會隱藏中段內容（畫面上會出現「檔案過大！部分文章無法顯示」），
  爬蟲已排除這個提示區塊，但代表無法保證 100% 完整抓到，極端爆量時段中間可能會漏接
- `pttPosts` 沒有分片，單一文件頂到 Firestore 1 MiB 上限後，當天該 session 就不會再有新推文寫入
- 沒有國定假日日曆，國定假日當天仍會被當成平日去嘗試解析盤中/盤後閒聊文章
- 板面翻頁最多找 4 頁（`MAX_INDEX_PAGES_TO_SEARCH`），文章若在被爬蟲鎖定前就洗出這個範圍
  （板面流量極大、文章遲遲沒發文），仍然會找不到並持續跳過

## 手動測試

```bash
cd apps/functions
uv sync

# pytest 單元測試（不連外網）
uv run pytest test_ptt_chat.py

# 手動觸發（會真的打 ptt.cc、寫入 Firestore，注意 GCP_PROJECT_ID / FIRESTORE_EMULATOR_HOST 指向哪個環境）
uv run python test_ptt_chat_manual.py
uv run python test_ptt_chat_manual.py --now "2026-08-06 14:00"   # 模擬觸發時間，測試盤中/盤後切換
```

## 部署

`main.py` 已匯出 `crawl_ptt_chat`，但尚未加入 GitHub Action 部署流程與 Cloud Scheduler 排程，
需要額外設定（部署方式比照 [README.md](README.md) 的 `daily_report`/`chip_report`）：

> ⚠️ 以下指令不會由 Claude 自動執行，僅供參考。

```bash
gcloud functions deploy crawl-ptt-chat \
  --gen2 \
  --runtime=python314 \
  --region=asia-east1 \
  --source=. \
  --entry-point=crawl_ptt_chat \
  --trigger-http \
  --no-allow-unauthenticated \
  --set-env-vars=GCP_PROJECT_ID=your-project-id

gcloud functions add-invoker-policy-binding crawl-ptt-chat \
  --region=asia-east1 \
  --member="serviceAccount:scheduler-invoker@your-project-id.iam.gserviceaccount.com"

PTT_CHAT_URL=$(gcloud functions describe crawl-ptt-chat --gen2 --region=asia-east1 --format='value(serviceConfig.uri)')

gcloud scheduler jobs create http crawl-ptt-chat-job \
  --location=asia-east1 \
  --schedule="* * * * *" \
  --time-zone="Asia/Taipei" \
  --uri="$PTT_CHAT_URL" \
  --http-method=POST \
  --oidc-service-account-email="scheduler-invoker@your-project-id.iam.gserviceaccount.com" \
  --max-retry-attempts=3 \
  --min-backoff=30s
```

也需要把 [firestore.rules](../../firestore.rules) 裡新增的 `pttThreads` / `pttPosts` /
`users/{uid}/setting/pttReadState`（文件名寫死，不開放同路徑下其他文件）規則部署到專案
（`firebase deploy --only firestore:rules`）。

## 相關文件

- [README.md](README.md) - Cloud Functions 部署總覽
- [firestore.rules](../../firestore.rules) - Firestore 安全規則
