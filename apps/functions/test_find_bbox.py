"""
互動式工具：協助找到 PDF 中圖片的正確裁切座標
"""
from pathlib import Path
import fitz  # PyMuPDF
from PIL import Image

from chip_report import ChipReportProcessor
from datetime import datetime


def extract_full_page_as_image(pdf_bytes: bytes, page_num: int = 0, output_path: str = "page_preview.png"):
    """將 PDF 頁面轉換為完整圖片以便檢視"""
    try:
        pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = pdf_document[page_num]

        # 取得頁面尺寸
        rect = page.rect
        print(f"📐 頁面尺寸: 寬={rect.width:.1f} 高={rect.height:.1f}")

        # 轉換為高解析度圖片
        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat)

        # 確保目錄存在
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        # 儲存
        pix.save(str(output))
        print(f"✅ 完整頁面已儲存: {output.absolute()}")
        print(f"   圖片尺寸: {pix.width} x {pix.height} pixels (2x 縮放)")
        print(f"\n💡 提示：")
        print(f"   1. 用圖片檢視器開啟: {output.absolute()}")
        print(f"   2. 找到你要的圖表位置")
        print(f"   3. 記錄座標 (x0, y0, x1, y1)")
        print(f"   4. 注意：圖片是 2x 縮放，座標需要除以 2")
        print(f"   5. 或用下方的測試功能直接測試座標\n")

        pdf_document.close()
        return rect.width, rect.height

    except Exception as e:
        print(f"❌ 錯誤: {e}")
        return None, None


def test_bbox(pdf_bytes: bytes, bbox: tuple, output_name: str = "test_crop.png"):
    """測試指定的裁切座標"""
    try:
        pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = pdf_document[0]

        # 裁切
        rect = fitz.Rect(bbox)
        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat, clip=rect)

        # 確保目錄存在
        output = Path(output_name)
        output.parent.mkdir(parents=True, exist_ok=True)

        pix.save(str(output))
        print(f"✅ 測試裁切已儲存: {output.absolute()}")
        print(f"   座標: {bbox}")
        print(f"   圖片尺寸: {pix.width} x {pix.height} pixels\n")

        pdf_document.close()

    except Exception as e:
        print(f"❌ 錯誤: {e}")


def main():
    """主程式"""
    print("="*60)
    print("📊 PDF 座標調整工具")
    print("="*60)
    print()

    # 找到專案根目錄
    project_root = Path(__file__).resolve().parents[2]
    output_dir = project_root / "saved-data" / "chip-reports"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 下載今天的 PDF
    processor = ChipReportProcessor(save_locally=True)
    target_date = datetime.now()

    print("正在下載 PDF...")
    pdf_bytes = processor.fetch_pdf(target_date)

    if not pdf_bytes:
        print("❌ 無法下載 PDF")
        return

    print(f"✅ PDF 下載成功 ({len(pdf_bytes)} bytes)\n")

    # 1. 先輸出完整頁面
    print("步驟 1: 產生完整頁面預覽")
    print("-"*60)
    width, height = extract_full_page_as_image(pdf_bytes, 0, str(output_dir / "page_full.png"))

    if not width:
        return

    # 2. 提供互動式測試
    print("\n步驟 2: 測試裁切座標")
    print("-"*60)
    print("輸入格式: x0,y0,x1,y1 (例如: 50,200,550,450)")
    print("直接按 Enter 使用目前的預設座標")
    print("輸入 'q' 結束\n")

    # 測試目前的座標
    print("測試目前預設座標:")
    test_bbox(pdf_bytes, processor.SMALL_FUTURES_CHART_BBOX, str(output_dir / "test_MTX.png"))
    test_bbox(pdf_bytes, processor.MICRO_FUTURES_CHART_BBOX, str(output_dir / "test_TMF.png"))

    # 互動式調整
    while True:
        print("\n" + "="*60)
        user_input = input("輸入座標測試 (或 'q' 結束): ").strip()

        if user_input.lower() == 'q':
            break

        if not user_input:
            continue

        try:
            coords = [float(x.strip()) for x in user_input.split(',')]
            if len(coords) != 4:
                print("❌ 需要 4 個座標值")
                continue

            bbox = tuple(coords)
            test_bbox(pdf_bytes, bbox, str(output_dir / "test_custom.png"))

        except ValueError:
            print("❌ 座標格式錯誤")

    print("\n✨ 完成")


if __name__ == "__main__":
    main()
