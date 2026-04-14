/**
 * AIサービス利用状況管理 - GAS 集計・整形・通知スクリプト
 *
 * このスクリプトは Google Sheets にデプロイして使用する。
 * raw_cursor / raw_codex / raw_claude_code シートから集計を行い、
 * summary シートへ反映し、必要に応じて通知を送信する。
 */

// ============================================
// 設定
// ============================================

const CONFIG = {
  // raw シート名
  RAW_SHEETS: ["raw_cursor", "raw_codex", "raw_claude_code"],

  // 集計結果シート名
  SUMMARY_SHEET: "summary",
  SUMMARY_BY_USER_SHEET: "summary_by_user",
  SUMMARY_BY_SERVICE_SHEET: "summary_by_service",

  // 通知先 (メールアドレス)
  NOTIFICATION_EMAIL: "",  // 設定してください

  // 通知先 (Google Chat Webhook URL)
  GOOGLE_CHAT_WEBHOOK_URL: "",  // 設定してください

  // raw シートのカラムインデックス (0始まり)
  COL: {
    FETCHED_AT: 0,
    SERVICE_NAME: 1,
    USER_NAME: 2,
    USER_EMAIL: 3,
    PLAN_NAME: 4,
    USAGE_DATE: 5,
    METRIC_NAME: 6,
    METRIC_VALUE: 7,
    SOURCE_TYPE: 8,
    RAW_PAYLOAD: 9,
    BATCH_ID: 10,
  },
};


// ============================================
// メイン集計処理
// ============================================

/**
 * 全 raw シートからデータを読み込み、集計を実行する。
 * トリガーまたは手動で実行する。
 */
function runAggregation() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const allRecords = [];

  // 全 raw シートからデータ読み込み
  for (const sheetName of CONFIG.RAW_SHEETS) {
    const sheet = ss.getSheetByName(sheetName);
    if (!sheet) {
      Logger.log(`シート '${sheetName}' が見つかりません。スキップします。`);
      continue;
    }

    const data = sheet.getDataRange().getValues();
    if (data.length <= 1) {
      Logger.log(`シート '${sheetName}' にデータがありません。`);
      continue;
    }

    // ヘッダー行をスキップ
    for (let i = 1; i < data.length; i++) {
      allRecords.push(data[i]);
    }
  }

  Logger.log(`全 raw シートから ${allRecords.length} 件のレコードを読み込みました。`);

  if (allRecords.length === 0) {
    Logger.log("集計対象データがありません。");
    return;
  }

  // 集計実行
  const byService = aggregateByService_(allRecords);
  const byUser = aggregateByUser_(allRecords);
  const dailySummary = aggregateDaily_(allRecords);

  // 集計結果シートへ出力
  writeSummaryByService_(ss, byService);
  writeSummaryByUser_(ss, byUser);
  writeDailySummary_(ss, dailySummary);

  Logger.log("集計処理が完了しました。");
}


// ============================================
// 集計ロジック
// ============================================

/**
 * サービス別集計
 */
function aggregateByService_(records) {
  const result = {};

  for (const row of records) {
    const service = row[CONFIG.COL.SERVICE_NAME];
    if (!result[service]) {
      result[service] = { recordCount: 0, users: new Set() };
    }
    result[service].recordCount++;
    const email = row[CONFIG.COL.USER_EMAIL];
    if (email) {
      result[service].users.add(email);
    }
  }

  // Set → 数値に変換
  for (const key of Object.keys(result)) {
    result[key].uniqueUsers = result[key].users.size;
    delete result[key].users;
  }

  return result;
}

/**
 * ユーザー別集計
 */
function aggregateByUser_(records) {
  const result = {};

  for (const row of records) {
    const email = row[CONFIG.COL.USER_EMAIL] || "(不明)";
    const name = row[CONFIG.COL.USER_NAME] || "";
    const service = row[CONFIG.COL.SERVICE_NAME];
    const key = `${email}__${service}`;

    if (!result[key]) {
      result[key] = {
        email: email,
        name: name,
        service: service,
        recordCount: 0,
        latestFetch: "",
      };
    }
    result[key].recordCount++;

    const fetchedAt = row[CONFIG.COL.FETCHED_AT];
    if (fetchedAt > result[key].latestFetch) {
      result[key].latestFetch = fetchedAt;
    }
  }

  return result;
}

/**
 * 日次集計
 */
function aggregateDaily_(records) {
  const result = {};

  for (const row of records) {
    const fetchedAt = row[CONFIG.COL.FETCHED_AT];
    const dateStr = String(fetchedAt).substring(0, 10); // YYYY-MM-DD
    const service = row[CONFIG.COL.SERVICE_NAME];
    const key = `${dateStr}__${service}`;

    if (!result[key]) {
      result[key] = {
        date: dateStr,
        service: service,
        recordCount: 0,
      };
    }
    result[key].recordCount++;
  }

  return result;
}


// ============================================
// 集計結果出力
// ============================================

/**
 * サービス別集計結果をシートへ出力する。
 */
function writeSummaryByService_(ss, byService) {
  const sheet = getOrCreateSheet_(ss, CONFIG.SUMMARY_BY_SERVICE_SHEET);
  sheet.clear();

  const headers = ["サービス名", "レコード数", "ユニークユーザー数", "集計日時"];
  const rows = [headers];

  const now = new Date().toISOString();
  for (const [service, data] of Object.entries(byService)) {
    rows.push([service, data.recordCount, data.uniqueUsers, now]);
  }

  if (rows.length > 1) {
    sheet.getRange(1, 1, rows.length, headers.length).setValues(rows);
  }

  Logger.log(`${CONFIG.SUMMARY_BY_SERVICE_SHEET}: ${rows.length - 1} 件出力`);
}

/**
 * ユーザー別集計結果をシートへ出力する。
 */
function writeSummaryByUser_(ss, byUser) {
  const sheet = getOrCreateSheet_(ss, CONFIG.SUMMARY_BY_USER_SHEET);
  sheet.clear();

  const headers = ["メールアドレス", "ユーザー名", "サービス名", "レコード数", "最終取得日時", "集計日時"];
  const rows = [headers];

  const now = new Date().toISOString();
  for (const data of Object.values(byUser)) {
    rows.push([data.email, data.name, data.service, data.recordCount, data.latestFetch, now]);
  }

  if (rows.length > 1) {
    sheet.getRange(1, 1, rows.length, headers.length).setValues(rows);
  }

  Logger.log(`${CONFIG.SUMMARY_BY_USER_SHEET}: ${rows.length - 1} 件出力`);
}

/**
 * 日次集計結果をシートへ出力する。
 */
function writeDailySummary_(ss, dailySummary) {
  const sheet = getOrCreateSheet_(ss, CONFIG.SUMMARY_SHEET);
  sheet.clear();

  const headers = ["日付", "サービス名", "レコード数", "集計日時"];
  const rows = [headers];

  const now = new Date().toISOString();
  const entries = Object.values(dailySummary).sort((a, b) => {
    if (a.date !== b.date) return a.date < b.date ? -1 : 1;
    return a.service < b.service ? -1 : 1;
  });

  for (const data of entries) {
    rows.push([data.date, data.service, data.recordCount, now]);
  }

  if (rows.length > 1) {
    sheet.getRange(1, 1, rows.length, headers.length).setValues(rows);
  }

  Logger.log(`${CONFIG.SUMMARY_SHEET}: ${rows.length - 1} 件出力`);
}


// ============================================
// 通知処理
// ============================================

/**
 * 日次サマリ通知を送信する。
 * トリガーで runAggregation の後に実行する想定。
 */
function sendDailySummaryNotification() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(CONFIG.SUMMARY_BY_SERVICE_SHEET);

  if (!sheet) {
    Logger.log("集計結果シートが見つかりません。先に runAggregation を実行してください。");
    return;
  }

  const data = sheet.getDataRange().getValues();
  if (data.length <= 1) {
    Logger.log("集計結果がありません。");
    return;
  }

  // 通知本文の構築
  const today = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "yyyy-MM-dd");
  let body = `【AIサービス利用状況レポート】${today}\n\n`;
  body += "■ サービス別集計\n";

  for (let i = 1; i < data.length; i++) {
    const [service, recordCount, uniqueUsers] = data[i];
    body += `  ${service}: レコード数=${recordCount}, ユーザー数=${uniqueUsers}\n`;
  }

  body += `\nスプレッドシート: ${ss.getUrl()}\n`;

  // メール送信
  if (CONFIG.NOTIFICATION_EMAIL) {
    MailApp.sendEmail({
      to: CONFIG.NOTIFICATION_EMAIL,
      subject: `[AIサービス管理] 日次レポート ${today}`,
      body: body,
    });
    Logger.log("メール通知を送信しました。");
  }

  // Google Chat 送信
  if (CONFIG.GOOGLE_CHAT_WEBHOOK_URL) {
    sendGoogleChatNotification_(body);
    Logger.log("Google Chat 通知を送信しました。");
  }
}

/**
 * Google Chat Webhook へ通知を送信する。
 */
function sendGoogleChatNotification_(message) {
  if (!CONFIG.GOOGLE_CHAT_WEBHOOK_URL) return;

  const payload = { text: message };
  const options = {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify(payload),
  };

  UrlFetchApp.fetch(CONFIG.GOOGLE_CHAT_WEBHOOK_URL, options);
}

/**
 * データ取得異常の検知と通知。
 * 直近の batch_id が存在しない、またはレコード数が急減した場合にアラートを送る。
 */
function checkDataAnomalies() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const alerts = [];

  for (const sheetName of CONFIG.RAW_SHEETS) {
    const sheet = ss.getSheetByName(sheetName);
    if (!sheet) {
      alerts.push(`${sheetName}: シートが見つかりません`);
      continue;
    }

    const lastRow = sheet.getLastRow();
    if (lastRow <= 1) {
      alerts.push(`${sheetName}: データが空です`);
      continue;
    }

    // 最終行の取得日時をチェック
    const lastFetchedAt = sheet.getRange(lastRow, 1).getValue();
    if (lastFetchedAt) {
      const lastDate = new Date(lastFetchedAt);
      const now = new Date();
      const hoursDiff = (now - lastDate) / (1000 * 60 * 60);

      if (hoursDiff > 48) {
        alerts.push(`${sheetName}: 最終取得から ${Math.round(hoursDiff)} 時間経過`);
      }
    }
  }

  if (alerts.length > 0) {
    const body = "【AIサービス管理 - 異常検知】\n\n" + alerts.join("\n");
    if (CONFIG.NOTIFICATION_EMAIL) {
      MailApp.sendEmail({
        to: CONFIG.NOTIFICATION_EMAIL,
        subject: "[AIサービス管理] データ取得異常検知",
        body: body,
      });
    }
    if (CONFIG.GOOGLE_CHAT_WEBHOOK_URL) {
      sendGoogleChatNotification_(body);
    }
    Logger.log("異常検知アラートを送信しました: " + alerts.join(", "));
  } else {
    Logger.log("異常は検知されませんでした。");
  }
}


// ============================================
// ユーティリティ
// ============================================

/**
 * シートを取得、なければ新規作成する。
 */
function getOrCreateSheet_(ss, name) {
  let sheet = ss.getSheetByName(name);
  if (!sheet) {
    sheet = ss.insertSheet(name);
    Logger.log(`シート '${name}' を新規作成しました。`);
  }
  return sheet;
}


// ============================================
// トリガー設定ヘルパー
// ============================================

/**
 * 日次集計 + 通知のトリガーを設定する。
 * スクリプトエディタから一度だけ手動実行する。
 */
function setupDailyTriggers() {
  // 既存トリガーを削除
  const triggers = ScriptApp.getProjectTriggers();
  for (const trigger of triggers) {
    ScriptApp.deleteTrigger(trigger);
  }

  // 毎日 9:00 に集計実行
  ScriptApp.newTrigger("runAggregation")
    .timeBased()
    .everyDays(1)
    .atHour(9)
    .create();

  // 毎日 9:30 に通知送信
  ScriptApp.newTrigger("sendDailySummaryNotification")
    .timeBased()
    .everyDays(1)
    .atHour(9)
    .nearMinute(30)
    .create();

  // 毎日 10:00 に異常検知
  ScriptApp.newTrigger("checkDataAnomalies")
    .timeBased()
    .everyDays(1)
    .atHour(10)
    .create();

  Logger.log("日次トリガーを設定しました。");
}
