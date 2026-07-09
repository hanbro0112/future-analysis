# 籌碼快訊報告處理功能

## 功能說明

每交易日 15:21 自動執行：
1. 從永豐金證券網站下載當天的台指籌碼快訊 PDF
2. 提取「小台 (MTX) 散戶多空比」和「微台 (TMF) 散戶多空比」兩張圖表
3. 儲存到專案根目錄的 `saved-data/chip-reports/YYYYMMDD/` 目錄

## 檔案結構

```
apps/price-analyzer/
├── src/price_analyzer/
│   └── chip_report.py          # 籌碼報告處理模組
├── test_chip_report.py         # 測試腳本
└── README_CHIP_REPORT.md       # 本文件
```

## 手動測試

```bash
cd apps/price-analyzer
uv run python test_chip_report.py
```

## 調整圖表裁切座標

PDF 格式可能會變動，需要調整裁切座標。

### 步驟 1: 開啟 PDF 並找到座標

使用 PDF 檢視器（如 Adobe Acrobat）開啟 PDF，記錄圖表的位置：
- 左上角座標 (x0, y0)
- 右下角座標 (x1, y1)

### 步驟 2: 修改 chip_report.py

編輯 `chip_report.py` 中的座標常數：

```python
class ChipReportProcessor:
    # 小台 (MTX) 散戶多空比圖表座標 (x0, y0, x1, y1)
    SMALL_FUTURES_CHART_BBOX = (50, 200, 550, 450)
    
    # 微台 (TMF) 散戶多空比圖表座標 (x0, y0, x1, y1)
    MICRO_FUTURES_CHART_BBOX = (50, 500, 550, 750)
```

### 步驟 3: 使用測試腳本驗證

執行測試腳本檢查裁切結果：

```bash
uv run python test_chip_report.py
```

檢查輸出的圖片：`<專案根目錄>/saved-data/chip-reports/YYYYMMDD/*.png`

### 座標系統說明

- 原點 (0, 0) 在 PDF 頁面的**左下角**
- x 軸向右為正
- y 軸向上為正
- 單位為點 (point)，1 英吋 = 72 點

## 輸出檔案

圖片儲存在專案根目錄：
```
saved-data/chip-reports/
└── YYYYMMDD/
    ├── YYYYMMDD_MTX_futures_ratio.png  # 小台 (MTX) 散戶多空比
    └── YYYYMMDD_TMF_futures_ratio.png  # 微台 (TMF) 散戶多空比
```

## 錯誤處理

如果處理失敗（PDF 不存在或網路問題），會在 log 中顯示錯誤訊息：
- `❌ 找不到 YYYY/MM/DD 的 PDF 檔案`
- `❌ 網路請求失敗`
- `❌ 提取圖表失敗`

## 依賴套件

- `requests`: HTTP 請求
- `beautifulsoup4`: HTML 解析
- `pymupdf (fitz)`: PDF 處理
- `pillow`: 圖片處理

已在 `pyproject.toml` 中定義。

## 定時任務

定時任務在 `price-analyzer` 主程式啟動時自動開始：
- 每交易日 15:21 執行
- 使用 `threading.Timer` 實作
- 錯誤不會中斷主程式

## 未來改進

1. 加入交易日判斷（目前每天都會執行）
2. 支援更靈活的圖表識別（OCR 標題識別）
3. 加入圖片上傳到 Firestore Storage 的功能
4. 支援歷史資料批次下載
