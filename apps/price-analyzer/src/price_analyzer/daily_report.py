"""
Daily Report Generator - 每日市場分析報告
使用 Gemini API 分析台股和美股市場
"""
import os
from datetime import datetime, timedelta
from typing import Optional
from google import genai
from google.genai import types


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
        print(f"🤖 呼叫 Gemini API...")
        
        try:
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
            print(f"❌ Gemini API 呼叫失敗: {e}")
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
