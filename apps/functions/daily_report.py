"""
Daily Report - 每日市場分析報告
使用 Gemini API 分析台股和美股市場，由 Cloud Scheduler 觸發的 Cloud Function
"""
import os
import time
from datetime import datetime, timedelta
from typing import Optional
from google import genai
from google.genai import types

from firestore_writer import FirestoreWriter


class DailyReportGenerator:
    """每日市場分析報告生成器"""

    def __init__(self, api_key: Optional[str] = None):
        """
        初始化報告生成器

        Args:
            api_key: Gemini API Key，如果未提供則從環境變數讀取
        """
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("未設定 GEMINI_API_KEY 環境變數")

        # 初始化 Gemini Client
        self.client = genai.Client(api_key=self.api_key)
        self.model_name = 'gemini-3.5-flash'

    def is_trading_day(self, date: datetime) -> bool:
        """
        判斷是否為交易日（排除週末）

        Args:
            date: 要檢查的日期

        Returns:
            是否為交易日
        """
        # 簡單判斷：週一至週五為交易日
        # TODO: 可以加入國定假日判斷
        return date.weekday() < 5  # 0-4 為週一至週五

    def get_last_trading_day(self, date: datetime) -> datetime:
        """
        取得最近的交易日（排除週末）

        Args:
            date: 基準日期

        Returns:
            最近的交易日
        """
        result = date
        while not self.is_trading_day(result):
            result -= timedelta(days=1)
        return result

    def generate_prompt(self, current_date: datetime, previous_date: datetime) -> str:
        """
        生成 Gemini 分析提示詞

        Args:
            current_date: 當前交易日
            previous_date: 上個交易日

        Returns:
            分析提示詞
        """
        current_date_str = current_date.strftime('%Y/%m/%d')
        previous_date_str = previous_date.strftime('%Y/%m/%d')

        prompt = f"""請幫我分析 {previous_date_str} 台股和美股，概括成以下幾點，最後給我 {current_date_str} 台股日盤的建議

        1. 台指期(日盤和夜盤)、加權指數、那斯達克指數、費城半導體指數
        2. 台積電、TSM (美股)
        """

        return prompt

    def generate_report(self, target_date: Optional[datetime] = None) -> dict:
        """
        生成每日市場分析報告

        Args:
            target_date: 目標日期，預設為今天

        Returns:
            報告資料字典
        """
        # 預設為今天
        if target_date is None:
            target_date = datetime.now()

        # 確保目標日期是交易日
        if not self.is_trading_day(target_date):
            raise ValueError(f"{target_date.strftime('%Y-%m-%d')} 不是交易日")

        # 取得上個交易日
        previous_date = self.get_last_trading_day(target_date - timedelta(days=1))

        # 生成提示詞
        prompt = self.generate_prompt(target_date, previous_date)

        print(f"📝 生成報告提示詞:\n{prompt}\n")

        # 重試設定
        max_retries = 5
        base_delay = 2  # 基礎延遲（秒）
        max_delay = 60  # 最大延遲（秒）

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    print(f"🔄 重試 {attempt}/{max_retries}...")
                else:
                    print(f"🤖 呼叫 Gemini API...")

                # 呼叫 Gemini API
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        # 1. 明確告訴時間，確認時間安全限制
                        system_instruction=f"Current year is {target_date.year}. Today's date is {target_date.strftime('%Y/%m/%d')}.",
                        # 2. 開啟 Google 搜尋支援，讓模型可以查詢最新資訊
                        tools=[types.Tool(google_search=types.GoogleSearch())]
                    )
                )
                raw_content = response.text

                print(f"✅ Gemini API 回應成功\n")
                print(f"📄 報告內容:\n{raw_content}\n")

                # 準備報告資料
                report_data = {
                    "date": target_date.strftime('%Y-%m-%d'),
                    "raw_content": raw_content,
                    "summary": {},  # 目前先留空，未來可以讓 Gemini 輸出結構化資料
                    "model_used": self.model_name,
                    "created_at": datetime.now().isoformat()
                }

                return report_data

            except Exception as e:
                error_str = str(e)

                # 判斷是否為可重試的錯誤
                is_retryable = any(code in error_str for code in ['503', '429', '500', '502', '504'])

                if attempt < max_retries - 1 and is_retryable:
                    # 計算延遲時間（指數退避）
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    print(f"❌ Gemini API 呼叫失敗: {e}")
                    print(f"⏳ 等待 {delay} 秒後重試...")
                    time.sleep(delay)
                else:
                    # 最後一次重試或不可重試的錯誤
                    print(f"❌ Gemini API 呼叫失敗: {e}")
                    if attempt == max_retries - 1:
                        print(f"❌ 已達最大重試次數 ({max_retries})，放棄重試")
                    raise

    def save_report(self, report_data: dict, firestore_writer) -> None:
        """
        儲存報告到 Firestore

        Args:
            report_data: 報告資料
            firestore_writer: Firestore Writer 實例
        """
        try:
            # 文件路徑：daily_reports/{YYYYMMDD}
            date_str = report_data['date'].replace('-', '')
            doc_id = date_str

            # 寫入 Firestore
            firestore_writer.write_document(
                collection='daily_reports',
                data=report_data,
                document_id=doc_id
            )

            print(f"💾 報告已儲存到 Firestore: daily_reports/{doc_id}\n")

        except Exception as e:
            print(f"❌ 儲存報告失敗: {e}")
            raise


def daily_report(request):
    """Cloud Functions HTTP entry point：由 Cloud Scheduler 觸發，產生並儲存每日市場分析報告"""
    now = datetime.now()

    try:
        report_generator = DailyReportGenerator()
    except ValueError as e:
        print(f"⚠️  每日報告生成器初始化失敗: {e}")
        return f"設定錯誤: {e}", 500

    if not report_generator.is_trading_day(now):
        message = f"{now.strftime('%Y-%m-%d')} 不是交易日，跳過報告生成"
        print(f"⏸️  {message}")
        return message, 200

    print(f"\n{'='*60}")
    print(f"📊 開始生成每日報告 - {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    try:
        report_data = report_generator.generate_report(now)

        firestore_writer = FirestoreWriter(project_id=os.getenv("GCP_PROJECT_ID", "demo-project"))
        try:
            report_generator.save_report(report_data, firestore_writer)
        finally:
            firestore_writer.close()

        print(f"{'='*60}")
        print(f"✅ 每日報告生成完成")
        print(f"{'='*60}\n")
        return "每日報告生成完成", 200

    except Exception as e:
        import traceback
        print(f"❌ 生成每日報告時發生錯誤: {e}")
        return f"每日報告生成失敗: {e}", 500
