"""
籌碼快訊報告處理模組
每交易日 15:21 抓取台指籌碼快訊 PDF 並提取散戶多空比圖表
"""
import os
import io
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple
import fitz  # PyMuPDF
from PIL import Image
from bs4 import BeautifulSoup
import urllib3
from google.cloud import storage

# 禁用 SSL 警告（因為目標網站 SSL 證書有問題）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class ChipReportProcessor:
    """籌碼快訊報告處理器"""
    
    BASE_URL = "https://www.spf.com.tw/sinopacSPF/research/list.do?id=1709f20d3ff00000d8e2039e8984ed51"
    
    # 圖表裁切座標 (x0, y0, x1, y1) - 從左下角開始
    # 小台 (MTX) 散戶多空比：只包含標題+圖表，不含備註和免責聲明
    SMALL_FUTURES_CHART_BBOX = (0, 810, 560, 1157)
    # 微台 (TMF) 散戶多空比：頁面底部的圖表
    MICRO_FUTURES_CHART_BBOX = (0, 1154, 560, 1500)
    
    def __init__(self, project_id: Optional[str] = None, bucket_name: Optional[str] = None, 
                 save_locally: bool = False, save_dir: Optional[str] = None):
        """
        初始化籌碼報告處理器
        
        Args:
            project_id: GCP 專案 ID，預設從環境變數讀取
            bucket_name: Storage bucket 名稱，預設為 {project_id}.appspot.com
            save_locally: 是否儲存到本地（用於 find_bbox.py 工具）
            save_dir: 本地儲存目錄（當 save_locally=True 時使用）
        """
        self.save_locally = save_locally
        
        if save_locally:
            # 本地儲存模式（find_bbox.py 使用）
            if save_dir is None:
                project_root = Path(__file__).resolve().parents[4]
                save_dir = project_root / "saved-data" / "chip-reports"
            
            self.save_dir = Path(save_dir)
            self.save_dir.mkdir(parents=True, exist_ok=True)
            self.storage_client = None
            self.bucket = None
        else:
            # Storage 上傳模式（正常使用）
            if project_id is None:
                project_id = os.getenv("GCP_PROJECT_ID", "demo-project")
            
            self.project_id = project_id
            self.bucket_name = bucket_name or f"{project_id}.appspot.com"
            
            # 初始化 Storage 客戶端
            if self._is_emulator_mode():
                print(f"🔧 使用 Storage Emulator")
                # Emulator 模式 - 確保 endpoint 有 http:// 前綴
                emulator_host = os.getenv("STORAGE_EMULATOR_HOST", "http://localhost:9199")
                if not emulator_host.startswith(("http://", "https://")):
                    emulator_host = f"http://{emulator_host}"
                
                self.storage_client = storage.Client(
                    project=project_id,
                    client_options={"api_endpoint": emulator_host}
                )
            else:
                print(f"☁️  連接到正式 Storage 環境")
                self.storage_client = storage.Client(project=project_id)
            
            self.bucket = self.storage_client.bucket(self.bucket_name)
    
    def _is_emulator_mode(self) -> bool:
        """檢查是否在 emulator 模式"""
        return bool(os.getenv("STORAGE_EMULATOR_HOST") or os.getenv("FIRESTORE_EMULATOR_HOST"))
    
    def fetch_pdf(self, target_date: datetime) -> Optional[bytes]:
        """
        從網站抓取指定日期的籌碼快訊 PDF
        
        Args:
            target_date: 目標日期
            
        Returns:
            PDF 檔案的 bytes，如果失敗則返回 None
        """
        try:
            # 請求列表頁面
            response = requests.get(self.BASE_URL, timeout=30, verify=False)
            response.raise_for_status()
            
            # 解析 HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 尋找包含日期的 PDF 連結
            date_str = target_date.strftime('%Y/%m/%d')
            print(f"🔍 搜尋日期: {date_str}")
            
            # 根據網站結構找到 PDF 連結
            # 結構：<li><a href="...">台指期籌碼快訊</a><span>2026/07/08</span></li>
            list_items = soup.find_all('li')
            pdf_url = None
            
            print(f"📋 找到 {len(list_items)} 個列表項目，開始搜尋...")
            
            for li in list_items:
                # 找到 span 標籤檢查日期
                span = li.find('span')
                if span and date_str in span.get_text(strip=True):
                    # 找到對應的 a 標籤
                    link = li.find('a', href=True)
                    if link:
                        href = link['href']
                        text = link.get_text(strip=True)
                        
                        # 確保是「籌碼快訊」而不是「盤後快訊」或其他
                        if '籌碼快訊' not in text:
                            continue
                            
                        print(f"✅ 找到目標連結: {text} - {date_str}")
                        
                        # 確保是 PDF 連結
                        if href.endswith('.pdf') or 'pdf' in href.lower():
                            # 處理相對路徑
                            if href.startswith('http'):
                                pdf_url = href
                            else:
                                base_domain = 'https://www.spf.com.tw'
                                pdf_url = base_domain + href if href.startswith('/') else base_domain + '/' + href
                            print(f"📥 PDF URL: {pdf_url}")
                            break
            
            if not pdf_url:
                print(f"❌ 找不到 {date_str} 的 PDF 檔案")
                return None
            
            # 下載 PDF
            print(f"📥 下載 PDF: {pdf_url}")
            pdf_response = requests.get(pdf_url, timeout=60, verify=False)
            pdf_response.raise_for_status()
            
            print(f"✅ PDF 下載成功，大小: {len(pdf_response.content)} bytes")
            return pdf_response.content
            
        except requests.RequestException as e:
            print(f"❌ 網路請求失敗: {e}")
            return None
        except Exception as e:
            print(f"❌ 抓取 PDF 時發生錯誤: {e}")
            return None
    
    def extract_charts(self, pdf_bytes: bytes, target_date: datetime) -> Tuple[Optional[str], Optional[str]]:
        """
        從 PDF 提取兩張散戶多空比圖表
        
        Args:
            pdf_bytes: PDF 檔案內容
            target_date: 目標日期（用於檔案命名）
            
        Returns:
            如果 save_locally=True: (本地檔案路徑, 本地檔案路徑)
            如果 save_locally=False: (Storage blob 路徑, Storage blob 路徑)
        """
        try:
            # 建立日期字串
            date_str = target_date.strftime('%Y%m%d')
            
            # 開啟 PDF
            pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
            
            if len(pdf_document) == 0:
                print("❌ PDF 沒有任何頁面")
                return None, None
            
            # 假設兩張圖都在第一頁
            page = pdf_document[0]
            
            if self.save_locally:
                # 本地儲存模式
                date_dir = self.save_dir / date_str
                date_dir.mkdir(parents=True, exist_ok=True)
                
                mtx_path = self._extract_chart_from_page(
                    page, 
                    self.SMALL_FUTURES_CHART_BBOX,
                    str(date_dir / f"{date_str}_MTX_futures_ratio.png")
                )
                
                tmf_path = self._extract_chart_from_page(
                    page,
                    self.MICRO_FUTURES_CHART_BBOX,
                    str(date_dir / f"{date_str}_TMF_futures_ratio.png")
                )
            else:
                # Storage 上傳模式
                mtx_path = self._extract_chart_from_page(
                    page, 
                    self.SMALL_FUTURES_CHART_BBOX,
                    f"chip-reports/{date_str}/{date_str}_MTX_futures_ratio.png"
                )
                
                tmf_path = self._extract_chart_from_page(
                    page,
                    self.MICRO_FUTURES_CHART_BBOX,
                    f"chip-reports/{date_str}/{date_str}_TMF_futures_ratio.png"
                )
            
            pdf_document.close()
            
            return mtx_path, tmf_path
            
        except Exception as e:
            print(f"❌ 提取圖表時發生錯誤: {e}")
            return None, None
    
    def _extract_chart_from_page(self, page: fitz.Page, bbox: Tuple[int, int, int, int], 
                                  path: str) -> Optional[str]:
        """
        從 PDF 頁面提取指定區域的圖片
        
        Args:
            page: PDF 頁面物件
            bbox: 裁切區域座標 (x0, y0, x1, y1)
            path: 本地檔案路徑或 Storage blob 路徑
            
        Returns:
            檔案路徑或 blob 路徑，失敗則返回 None
        """
        try:
            # 建立裁切矩形
            rect = fitz.Rect(bbox)
            
            # 將頁面轉換為圖片（高解析度）
            mat = fitz.Matrix(2.0, 2.0)  # 2倍縮放以提高解析度
            pix = page.get_pixmap(matrix=mat, clip=rect)
            
            if self.save_locally:
                # 儲存到本地
                pix.save(path)
                print(f"✅ 圖表已儲存: {path}")
            else:
                # 上傳到 Storage
                img_bytes = pix.tobytes("png")
                blob = self.bucket.blob(path)
                blob.upload_from_string(img_bytes, content_type='image/png')
                print(f"✅ 圖表已上傳: gs://{self.bucket_name}/{path}")
            
            return path
            
        except Exception as e:
            print(f"❌ 提取圖表失敗 (bbox={bbox}): {e}")
            return None
    
    def process_daily_report(self, target_date: Optional[datetime] = None) -> bool:
        """
        處理每日籌碼報告（主流程）
        
        Args:
            target_date: 目標日期，預設為今天
            
        Returns:
            處理是否成功
        """
        if target_date is None:
            target_date = datetime.now()
        
        print(f"\n{'='*60}")
        print(f"📊 開始處理籌碼快訊 - {target_date.strftime('%Y-%m-%d')}")
        print(f"{'='*60}\n")
        
        # 1. 下載 PDF
        pdf_bytes = self.fetch_pdf(target_date)
        if not pdf_bytes:
            print("❌ PDF 下載失敗，處理終止")
            return False
        
        # 2. 提取圖表
        mtx_path, tmf_path = self.extract_charts(pdf_bytes, target_date)
        
        # 3. 驗證結果
        success = mtx_path is not None and tmf_path is not None
        
        if success:
            print(f"\n{'='*60}")
            print(f"✅ 籌碼快訊處理完成")
            print(f"   小台 (MTX) 散戶多空比: {mtx_path}")
            print(f"   微台 (TMF) 散戶多空比: {tmf_path}")
            print(f"{'='*60}\n")
        else:
            print(f"\n{'='*60}")
            print(f"⚠️  籌碼快訊處理部分失敗")
            print(f"{'='*60}\n")
        
        return success


# 提供便捷的函數介面
def process_chip_report(target_date: Optional[datetime] = None, project_id: Optional[str] = None, 
                       bucket_name: Optional[str] = None) -> bool:
    """
    處理籌碼快訊報告（便捷函數）
    
    Args:
        target_date: 目標日期，預設為今天
        project_id: GCP 專案 ID，預設從環境變數讀取
        bucket_name: Storage bucket 名稱，預設為 {project_id}.appspot.com
        
    Returns:
        處理是否成功
    """
    # 從環境變數讀取 project_id
    if project_id is None:
        project_id = os.getenv("GCP_PROJECT_ID", "demo-project")
    
    processor = ChipReportProcessor(project_id=project_id, bucket_name=bucket_name)
    return processor.process_daily_report(target_date)


if __name__ == "__main__":
    # 測試用
    process_chip_report()
