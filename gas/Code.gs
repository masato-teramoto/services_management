/**
 * AIサービス利用状況管理 - GAS 集計・整形・通知スクリプト
 *
 * このスクリプトは Google Sheets にデプロイして使用する。
 * raw_cursor / raw_codex / raw_claude_code シートから利用状況の集計を行い、
 * raw_pricing シートから料金集計を行い、
 * 各集計シートへ反映し、必要に応じて通知を送信する。
 */

// ============================================
// 設定
// ============================================

const CONFIG = {
  // raw シート名
  // NOTE: Codex は利用料をサイトから確認することが不可能なため、現時点では対象外。
  //       将来的に対応可能になった場合は "raw_codex" を追加する。
  RAW_SHEETS: ["raw_cursor", "raw_claude_code"],

  // 料金データシート名
  RAW_PRICING_SHEET: "raw_pricing",

  // 集計結果シート名
  SUMMARY_SHEET: "summary",
  SUMMARY_BY_USER_SHEET: "summary_by_user",
  SUMMARY_BY_SERVICE_SHEET: "summary_by_service",

  // 料金集計シート名
  PRICING_SUMMARY_SHEET: "pricing_summary",

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

  // raw_pricing シートのカラムインデックス (0始まり)
  PRICING_COL: {
    FETCHED_AT: 0,
    SERVICE_NAME: 1,
    ACCOUNTING_MONTH: 2,
    USER_EMAIL: 3,
    USER_NAME: 4,
    CHARGE_TYPE: 5,
    AMOUNT_USD: 6,
    DESCRIPTION: 7,
    BATCH_ID: 8,
  },

  // サービス名の表示用マッピング
  SERVICE_DISPLAY_NAMES: {
    "cursor": "Cursor",
    "codex": "Codex",
    "claude_code": "Claude Code",
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

  // 料金集計
  runPricingAggregation();

  Logger.log("集計処理が完了しました。");
}


// ============================================
// 料金集計処理
// ============================================

/**
 * raw_pricing シートからデータを読み込み、サービス別の料金集計を行う。
 * 各サービスの基本料金・オンデマンド料金・合計料金を算出して
 * pricing_summary シートへ出力する。
 */
function runPricingAggregation() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(CONFIG.RAW_PRICING_SHEET);

  if (!sheet) {
    Logger.log(`シート '${CONFIG.RAW_PRICING_SHEET}' が見つかりません。料金集計をスキップします。`);
    return;
  }

  const data = sheet.getDataRange().getValues();
  if (data.length <= 1) {
    Logger.log("料金データがありません。");
    return;
  }

  // ヘッダー行をスキップして料金レコードを読み込み
  const pricingRecords = [];
  for (let i = 1; i < data.length; i++) {
    pricingRecords.push(data[i]);
  }

  Logger.log(`料金データ: ${pricingRecords.length} 件を読み込みました。`);

  // 計上月別 × サービス別に集計
  const pricingByMonth = aggregatePricingByMonth_(pricingRecords);

  // 料金集計シートへ出力
  writePricingSummary_(ss, pricingByMonth);

  Logger.log("料金集計が完了しました。");
}

/**
 * 料金レコードを計上月別 × サービス別に集計する。
 *
 * 結果の構造:
 * {
 *   "YYYY-MM": {
 *     "cursor": { base: X, ondemand: Y },
 *     "codex": { base: X, ondemand: Y },
 *     "claude_code": { base: X, ondemand: Y },
 *   }
 * }
 */
function aggregatePricingByMonth_(records) {
  const result = {};

  for (const row of records) {
    const accountingMonth = String(row[CONFIG.PRICING_COL.ACCOUNTING_MONTH]);
    const serviceName = String(row[CONFIG.PRICING_COL.SERVICE_NAME]);
    const chargeType = String(row[CONFIG.PRICING_COL.CHARGE_TYPE]);
    const amountUsd = Number(row[CONFIG.PRICING_COL.AMOUNT_USD]) || 0;

    if (!result[accountingMonth]) {
      result[accountingMonth] = {};
    }
    if (!result[accountingMonth][serviceName]) {
      result[accountingMonth][serviceName] = { base: 0, ondemand: 0 };
    }

    if (chargeType === "base") {
      result[accountingMonth][serviceName].base += amountUsd;
    } else if (chargeType === "ondemand") {
      result[accountingMonth][serviceName].ondemand += amountUsd;
    }
  }

  return result;
}

/**
 * 料金集計結果を pricing_summary シートへ出力する。
 *
 * シートの構成:
 * | 計上月 | サービス名 | 基本料金(USD) | オンデマンド料金(USD) | 合計料金(USD) | 集計日時 |
 */
function writePricingSummary_(ss, pricingByMonth) {
  const sheet = getOrCreateSheet_(ss, CONFIG.PRICING_SUMMARY_SHEET);
  sheet.clear();

  const headers = [
    "計上月",
    "サービス名",
    "基本料金(USD)",
    "オンデマンド料金(USD)",
    "合計料金(USD)",
    "集計日時",
  ];
  const rows = [headers];
  const now = new Date().toISOString();

  // サービスの表示順序
  // NOTE: Codex は利用料をサイトから確認することが不可能なため、現時点では対象外。
  //       将来的に対応可能になった場合は "codex" を追加する。
  const serviceOrder = ["cursor", "claude_code"];

  // 計上月でソート
  const months = Object.keys(pricingByMonth).sort();

  for (const month of months) {
    const monthData = pricingByMonth[month];

    for (const serviceName of serviceOrder) {
      const data = monthData[serviceName] || { base: 0, ondemand: 0 };
      const baseUsd = roundToTwoDecimals_(data.base);
      const ondemandUsd = roundToTwoDecimals_(data.ondemand);
      const totalUsd = roundToTwoDecimals_(baseUsd + ondemandUsd);
      const displayName = CONFIG.SERVICE_DISPLAY_NAMES[serviceName] || serviceName;

      rows.push([month, displayName, baseUsd, ondemandUsd, totalUsd, now]);
    }

    // 月ごとの合計行
    let monthBaseTotal = 0;
    let monthOndemandTotal = 0;
    for (const svc of serviceOrder) {
      const d = monthData[svc] || { base: 0, ondemand: 0 };
      monthBaseTotal += d.base;
      monthOndemandTotal += d.ondemand;
    }
    rows.push([
      month,
      "【合計】",
      roundToTwoDecimals_(monthBaseTotal),
      roundToTwoDecimals_(monthOndemandTotal),
      roundToTwoDecimals_(monthBaseTotal + monthOndemandTotal),
      now,
    ]);
  }

  if (rows.length > 1) {
    sheet.getRange(1, 1, rows.length, headers.length).setValues(rows);
  }

  Logger.log(`${CONFIG.PRICING_SUMMARY_SHEET}: ${rows.length - 1} 件出力`);
}

/**
 * 小数点以下2桁に丸める。
 */
function roundToTwoDecimals_(value) {
  return Math.round(value * 100) / 100;
}


// ============================================
// 利用状況集計ロジック
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

  // 料金集計情報を追加
  const pricingSheet = ss.getSheetByName(CONFIG.PRICING_SUMMARY_SHEET);
  if (pricingSheet) {
    const pricingData = pricingSheet.getDataRange().getValues();
    if (pricingData.length > 1) {
      body += "\n■ 料金集計\n";
      for (let i = 1; i < pricingData.length; i++) {
        const [month, service, baseUsd, ondemandUsd, totalUsd] = pricingData[i];
        body += `  ${month} ${service}: 基本=$${baseUsd}, オンデマンド=$${ondemandUsd}, 合計=$${totalUsd}\n`;
      }
    }
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

  // raw シートのチェック
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

  // 料金シートのチェック
  const pricingSheet = ss.getSheetByName(CONFIG.RAW_PRICING_SHEET);
  if (!pricingSheet) {
    alerts.push(`${CONFIG.RAW_PRICING_SHEET}: シートが見つかりません`);
  } else {
    const lastRow = pricingSheet.getLastRow();
    if (lastRow <= 1) {
      alerts.push(`${CONFIG.RAW_PRICING_SHEET}: データが空です`);
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
