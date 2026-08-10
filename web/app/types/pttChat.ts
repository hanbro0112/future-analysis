/**
 * PTT Stock 板盤中/盤後閒聊類型定義
 */

/**
 * 閒聊時段：intraday = 盤中閒聊, afterhours = 盤後閒聊
 */
export type PttSession = 'intraday' | 'afterhours';

/**
 * 單則 PTT 推文
 */
export interface PttPush {
  push_tag: string // 推文符號: 推 / → / 噓
  userid: string // 推文者帳號
  content: string // 推文內容
  time: string // 推文時間，格式 MM/DD HH:mm
}
