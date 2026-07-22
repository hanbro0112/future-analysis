"""
Daily Report Test Script - 測試每日報告生成
手動觸發每日報告生成，無需等待定時任務
"""
import os
import sys
from datetime import datetime, timedelta
import argparse
from dotenv import load_dotenv

from firestore_writer import FirestoreWriter
from daily_report import DailyReportGenerator


def main():
    """測試每日報告生成"""
    # 載入環境變數
    load_dotenv()

    # 解析命令列參數
    parser = argparse.ArgumentParser(description='測試每日報告生成')
    parser.add_argument(
        '--date',
        type=str,
        help='指定日期 (格式: YYYY-MM-DD)，預設為今天',
        default=None
    )
    parser.add_argument(
        '--skip-save',
        action='store_true',
        help='跳過儲存到 Firestore，只顯示報告內容'
    )
    args = parser.parse_args()

    try:
        # 初始化每日報告生成器
        print("=" * 70)
        print("📊 每日市場分析報告測試")
        print("=" * 70)
        print()

        report_generator = DailyReportGenerator()
        print("✅ 每日報告生成器已初始化")
        print(f"🤖 使用模型: {report_generator.model_name}\n")

        # 確定目標日期
        if args.date:
            target_date = datetime.strptime(args.date, '%Y-%m-%d')
            print(f"📅 指定日期: {target_date.strftime('%Y-%m-%d')}")
        else:
            target_date = datetime.now()
            print(f"📅 使用今天: {target_date.strftime('%Y-%m-%d')}")

        # 檢查是否為交易日
        if not report_generator.is_trading_day(target_date):
            print(f"⚠️  {target_date.strftime('%Y-%m-%d')} 不是交易日（週末）")
            # 取得最近的交易日
            last_trading_day = report_generator.get_last_trading_day(target_date - timedelta(days=1))
            print(f"💡 使用最近的交易日: {last_trading_day.strftime('%Y-%m-%d')}")
            target_date = last_trading_day

        print()
        print("-" * 70)
        print()

        # 生成報告
        report_data = report_generator.generate_report(target_date)

        print()
        print("-" * 70)
        print()
        print("✅ 報告生成成功！")
        print()
        print(f"📄 報告摘要:")
        print(f"  - 日期: {report_data['date']}")
        print(f"  - 模型: {report_data['model_used']}")
        print(f"  - 建立時間: {report_data['created_at']}")
        print(f"  - 內容長度: {len(report_data['raw_content'])} 字元")
        print()

        # 儲存到 Firestore
        if not args.skip_save:
            print("-" * 70)
            print()
            print("💾 儲存報告到 Firestore...")

            firestore_writer = FirestoreWriter(
                project_id=os.getenv("GCP_PROJECT_ID", "demo-project")
            )

            try:
                report_generator.save_report(report_data, firestore_writer)
                print("✅ 報告已儲存")
            finally:
                firestore_writer.close()
        else:
            print("⏭️  跳過儲存（使用 --skip-save 選項）")

        print()
        print("=" * 70)
        print("✨ 測試完成")
        print("=" * 70)

    except ValueError as e:
        print(f"❌ 錯誤: {e}")
        print()
        print("💡 提示:")
        print("  1. 請確認已設定 GEMINI_API_KEY 環境變數")
        print("  2. 可在 apps/.env 檔案中設定")
        print("  3. 或執行: export GEMINI_API_KEY=your-api-key")
        sys.exit(1)

    except Exception as e:
        import traceback
        print(f"❌ 發生錯誤: {e}")
        print(f"🔍 詳細錯誤:\n{traceback.format_exc()}")
        sys.exit(1)


if __name__ == '__main__':
    main()
