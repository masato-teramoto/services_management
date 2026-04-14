# AIコーディング支援ツール利用状況管理 基本構想

## 1. 背景と目的

社内で利用されている **Cursor / Claude / Codex** の利用状況を継続的に把握し、ライセンス管理・利用傾向分析・費用対効果の確認を行うための仕組みを整備する。

本構想では、各ツールの利用データを定期取得し、**Google Sheets に raw データとして蓄積**したうえで、**GAS（Google Apps Script）により集計・整形・通知**を行う運用を想定する。

---

## 2. 対象ツールと取得方針

### 2.1 Cursor
- Cursor は API により利用量および料金情報を取得可能
- そのため、**API 経由で定期的にデータ取得**を行う
- 想定取得項目
  - ユーザー識別情報（`/teams/members`）
  - 利用量
  - 実行日時
  - 対象期間
  - オンデマンド利用額（`/teams/spend` → `spendCents`）
- 料金の取得方針
  - **基本料金**: API からは直接取得せず、`CURSOR_MONTHLY_RATE`（月額単価）とメンバー履歴から日割り計算
  - **オンデマンド料金**: Cursor API `/teams/spend` から `spendCents` を取得し USD 化

### 2.2 Codex
- Codex は Enterprise プランではないため、利用状況取得用 API が利用できない
- そのため、**Playwright によるブラウザ自動操作**で管理画面等から必要データを取得する
- 想定取得項目
  - ユーザー別利用状況
  - 利用日時または集計期間
  - 利用量・回数など画面上で確認可能な指標
  - オンデマンド利用額（Usage ページの金額表示）
  - メンバー数（チーム管理ページ）
- 料金の取得方針
  - **基本料金**: `CODEX_MONTHLY_RATE`（月額単価）× メンバー数 で内部計算
  - **オンデマンド料金**: Playwright で Usage ページから利用額を抽出

### 2.3 Claude Code
- Claude Code も Enterprise プランではないため、API 経由での取得が困難
- そのため、**Playwright によるブラウザ自動操作**でデータを取得する
- 想定取得項目
  - ユーザー別利用状況
  - 利用日時または集計期間
  - 利用量・回数など画面上で確認可能な指標
  - オンデマンド利用額（Usage ページの金額表示）
  - メンバー数（メンバー管理ページ）
- 料金の取得方針
  - **基本料金**: `CLAUDE_MONTHLY_RATE`（月額単価）× メンバー数 で内部計算
  - **オンデマンド料金**: Playwright で Usage ページから利用額を抽出

---

## 3. 全体アーキテクチャ

全体の流れは以下の通り。

1. **WSL 上のバッチ処理**で各サービスの利用データを取得
2. 取得結果を **Google Sheets の raw_* シートへ追記**
3. raw データ蓄積後、**GAS により集計・整形処理を実行**
4. 集計結果に基づき、必要に応じて **通知（メール / Google Chat 等）** を実施

---

## 4. 実装方針

## 4.1 バッチ実行基盤
データ取得処理は **WSL 上のバッチ**として実装する。

想定構成:
- 実行環境: WSL
- 実装言語候補: Python / Node.js
- スケジューラ:
  - Linux 側: `cron`
  - Windows 側: `Task Scheduler`

役割分担のイメージ:
- `cron` または `Task Scheduler` が定期的にバッチ起動
- バッチが Cursor / Codex / Claude Code の各取得処理を順次実行
- 最後に Google Sheets へ raw データを追記

---

## 4.2 取得方式の切り分け

| 対象 | 利用状況の取得方式 | 料金の取得方式 | 備考 |
|---|---|---|---|
| Cursor | API (`/teams/members`, `/teams/spend`) | 基本=内部計算, オンデマンド=API | 安定的・構造化データ取得が可能 |
| Codex | Playwright | 基本=内部計算, オンデマンド=Playwright | 画面操作による取得が必要 |
| Claude Code | Playwright | 基本=内部計算, オンデマンド=Playwright | 画面操作による取得が必要 |

このため、実装は以下の 2 系統に分かれる。

### API 取得系
- Cursor 専用
- Basic 認証 (`CURSOR_API_KEY`) を用いて API 実行
- `/teams/members` でメンバー一覧を取得
- `/teams/spend` (POST) でオンデマンド利用額を取得
- レスポンスを正規化して利用データおよび料金データを Sheets 投入形式へ変換

### 画面取得系
- Codex / Claude Code 共通の考え方
- Playwright でログイン、画面遷移、対象情報抽出を実施
- Usage ページからオンデマンド利用額（$XX.XX 形式）を抽出
- チーム管理ページからメンバー数を取得
- DOM 構造変更に備えて保守性の高いセレクタ設計を行う
- 取得失敗時はスクリーンショット / ログを保存し、原因追跡可能にする

---

## 5. Google Sheets 設計方針

取得データは **Google Sheets の raw_* シート**へ追記する。

想定シート:
- `raw_cursor` — Cursor 利用状況データ
- `raw_codex` — Codex 利用状況データ
- `raw_claude_code` — Claude Code 利用状況データ
- `raw_pricing` — 全サービス共通の料金データ
- `pricing_summary` — 料金集計結果（GAS が生成）

### 5.1 raw シートの役割
- 取得した元データをできるだけ加工せずに保存する
- 後続の集計・再計算・調査に利用する
- 障害時の再処理や差分確認の基礎データとする

### 5.2 raw シートの基本カラム案（利用状況）
共通的には以下のようなカラムを想定する。

- `fetched_at`: 取得日時
- `service_name`: サービス名
- `user_name`: ユーザー名
- `user_email`: メールアドレス等の識別子
- `plan_name`: プラン名
- `usage_date`: 利用日または対象期間
- `metric_name`: 指標名
- `metric_value`: 指標値
- `source_type`: `api` / `playwright`
- `raw_payload`: 必要に応じた原文・JSON・取得元情報
- `batch_id`: 実行単位識別子

### 5.3 raw_pricing シートのカラム案（料金）
各サービスの料金データを統一フォーマットで保存する。

- `fetched_at`: 取得日時
- `service_name`: サービス名 (`cursor` / `codex` / `claude_code`)
- `accounting_month`: 計上月 (`YYYY-MM` 形式)
- `user_email`: メールアドレス（ユーザー別の場合）
- `user_name`: ユーザー名
- `charge_type`: 料金種別 (`base` / `ondemand`)
- `amount_usd`: 金額 (USD)
- `description`: 計算根拠等の説明
- `batch_id`: 実行単位識別子

### 5.4 pricing_summary シートの構成（GAS 集計結果）
GAS の `runPricingAggregation()` が `raw_pricing` を集計して出力する。

| 計上月 | サービス名 | 基本料金(USD) | オンデマンド料金(USD) | 合計料金(USD) | 集計日時 |
|---|---|---|---|---|---|
| 2026-04 | Cursor | 100.00 | 25.50 | 125.50 | ... |
| 2026-04 | Codex | 80.00 | 15.00 | 95.00 | ... |
| 2026-04 | Claude Code | 60.00 | 10.00 | 70.00 | ... |
| 2026-04 | 【合計】 | 240.00 | 50.50 | 290.50 | ... |

### 5.5 追記方針
- raw シートには **append-only（追記専用）** で保存する
- 更新ではなく追記を基本とすることで監査性を確保する
- 必要に応じて GAS 側で最新データ採用・重複排除を行う

---

## 6. GAS による後続処理

データ取得後の処理は **GAS** で行う。

### 6.1 GAS の役割
- raw シートから必要データを読み込み
- サービス横断で利用状況の集計・整形
- `raw_pricing` シートからサービス別の料金集計（基本料金・オンデマンド料金・合計料金）
- 集計結果シートへ反映
- 閾値超過や定例レポートを通知

### 6.2 集計・整形の例
- ツール別利用者数
- 日次 / 週次 / 月次利用量
- 上位利用者ランキング
- 未利用ライセンスの検出
- 急増 / 急減ユーザーの抽出
- プラン別・組織別の利用傾向
- **サービス別月次料金集計（基本料金・オンデマンド料金・合計料金）**

### 6.3 通知の例
- 日次または週次のサマリ通知
- 一定閾値超過時のアラート
- データ取得失敗時の異常通知
- 一定期間未利用ユーザーの通知

---

## 7. 定期実行設計

## 7.1 実行タイミング
定期実行は `cron` または `Task Scheduler` により実施する。

想定例:
- 毎日早朝に 1 回実行
- 平日のみ定時実行
- 必要に応じて日次 / 週次でジョブ分割

## 7.2 実行単位
以下のようにジョブを分けると保守しやすい。

- Job 1: Cursor API 取得
- Job 2: Codex Playwright 取得
- Job 3: Claude Code Playwright 取得
- Job 4: Google Sheets 追記
- Job 5: GAS 集計 / 通知トリガー

または、単一の親バッチから順次実行してもよい。

---

## 8. 想定ディレクトリ構成

```text
project-root/
├─ batch/
│  ├─ run_all.sh
│  ├─ run_cursor.sh
│  ├─ run_codex.sh
│  └─ run_claude_code.sh
├─ src/
│  ├─ cursor/
│  │  └─ fetch_cursor_usage.py
│  ├─ codex/
│  │  └─ fetch_codex_usage.ts
│  ├─ claude_code/
│  │  └─ fetch_claude_code_usage.ts
│  ├─ sheets/
│  │  └─ append_to_sheets.py
│  └─ common/
│     ├─ config.*
│     ├─ logger.*
│     └─ utils.*
├─ logs/
├─ screenshots/
├─ output/
└─ docs/
   └─ concept.md
```

---

## 9. 認証・秘密情報管理

本仕組みでは複数の認証情報を扱うため、安全な管理が必要。

### 9.1 想定する認証情報
- Cursor API キー (`CURSOR_API_KEY`)
- Codex ログイン情報 (`CODEX_LOGIN_EMAIL`, `CODEX_LOGIN_PASSWORD`)
- Claude Code ログイン情報 (`CLAUDE_LOGIN_EMAIL`, `CLAUDE_LOGIN_PASSWORD`)
- Google Sheets 書き込み用のサービスアカウント情報または OAuth 認証情報

### 9.2 料金関連の設定値
- `CURSOR_MONTHLY_RATE`: Cursor 1 ユーザーあたりの月額 USD 単価
- `CURSOR_BILLING_CYCLE_START_DAY`: Cursor 請求サイクル開始日（デフォルト: 26）
- `CODEX_MONTHLY_RATE`: Codex 1 ユーザーあたりの月額 USD 単価
- `CLAUDE_MONTHLY_RATE`: Claude Code 1 ユーザーあたりの月額 USD 単価

### 9.3 管理方針
- ソースコードへ直書きしない
- `.env` や OS の資格情報管理機構を利用する
- Codex / Claude Code などのログインに必要な情報は、WSL 上の環境変数として配置して利用する
- アクセス権を最小限にする
- ログへ秘密情報を出力しない
- Playwright のセッション保存時は保存場所と権限管理に注意する

---

## 10. 監視・障害対応

## 10.1 ログ設計
- 実行開始 / 終了
- 各サービスの取得件数
- Sheets 追記件数
- エラー内容
- 再試行有無
- 実行ID（batch_id）

## 10.2 エラー時の挙動
- 一時的な失敗は再試行
- Playwright 失敗時はスクリーンショット保存
- 取得不可サービスがあっても、他サービスは可能な範囲で継続実行
- 最終的に異常通知を送信

## 10.3 代表的なリスク
- 画面 DOM 変更による Playwright 破損
- 多要素認証やログインフロー変更
- API 仕様変更
- Google Sheets の行数増大による処理性能低下
- 重複データの蓄積

---

## 11. 運用上のポイント

### 11.1 Playwright 利用時の注意
- 画面構造変更に弱いため定期メンテナンス前提とする
- セレクタはテキスト依存を避け、安定した属性を優先する
- ヘッドレス実行だけでなく、障害調査時にヘッドあり実行可能とする

### 11.2 データ品質担保
- 同一 batch_id 単位で整合性確認
- 取得件数の急減急増を検知
- サービス別に最低限の必須項目チェックを行う
- raw データと集計データの対応関係を追跡可能にする

### 11.3 スケーラビリティ
- 当初は Google Sheets をデータ蓄積先とする
- データ量が増えた場合は BigQuery 等への移行を検討する
- ただし初期フェーズでは Sheets + GAS により迅速に構築する

---

## 12. 推奨実装ステップ

1. **raw シート定義**
   - `raw_cursor`
   - `raw_codex`
   - `raw_claude_code`
   - `raw_pricing`

2. **Cursor API 取得処理の実装**
   - API 接続（`/teams/members`, `/teams/spend`）
   - レスポンス整形（利用レコード + 料金レコード）
   - Sheets 追記

3. **Codex Playwright 取得処理の実装**
   - ログイン
   - Usage ページ遷移・データ抽出
   - オンデマンド利用額抽出
   - メンバー数取得
   - 料金レコード生成
   - Sheets 追記

4. **Claude Code Playwright 取得処理の実装**
   - ログイン
   - Usage ページ遷移・データ抽出
   - オンデマンド利用額抽出
   - メンバー数取得
   - 料金レコード生成
   - Sheets 追記

5. **共通バッチ化**
   - WSL バッチ化
   - cron / Task Scheduler 登録

6. **GAS 実装**
   - 利用状況集計シート作成
   - **料金集計シート作成（`pricing_summary`）**
     - サービス別の基本料金・オンデマンド料金・合計料金
     - 月別合計行
   - 整形処理
   - 通知処理（料金情報を含む）

7. **監視・運用整備**
   - ログ
   - エラー通知
   - 再試行制御
   - 保守手順書作成

---

## 13. 今後の拡張案

- 利用者マスタとの突合
- 部署別・ライセンス別の集計
- 月次レポート自動配信
- **為替レート (USD → JPY) の自動取得と円建て料金の算出**
- **Cursor 請求明細シートとの連携（日割り計算の精密化）**
- **組織按分機能（ユーザー組織履歴に基づく按分）**
- コスト管理との連携
- 退職者 / 異動者アカウントの検出
- ダッシュボード化（Looker Studio 等）

---

## 14. 料金管理の全体像

### 14.1 料金体系

各サービスの料金は **基本料金** と **オンデマンド料金** に分けて管理する。

| サービス | 基本料金の算出方法 | オンデマンド料金の取得元 |
|---|---|---|
| Cursor | 月額単価 × 稼働日数 ÷ サイクル日数（内部計算） | API `/teams/spend` の `spendCents` |
| Codex | 月額単価 × メンバー数（内部計算） | Playwright で Usage ページから抽出 |
| Claude Code | 月額単価 × メンバー数（内部計算） | Playwright で Usage ページから抽出 |

### 14.2 データフロー

```text
[Cursor API]         → 基本料金(計算) + オンデマンド(API) → raw_pricing
[Codex Playwright]   → 基本料金(計算) + オンデマンド(抽出) → raw_pricing
[Claude Playwright]  → 基本料金(計算) + オンデマンド(抽出) → raw_pricing
                                                              ↓
                                                  GAS runPricingAggregation()
                                                              ↓
                                                      pricing_summary
                                                  (基本/オンデマンド/合計)
```

### 14.3 合計料金

合計料金は GAS 集計時に算出する。

```text
合計料金 = 基本料金 + オンデマンド料金
```

`pricing_summary` シートにはサービスごとの行に加えて、月ごとの **【合計】行** も出力する。

---

## 15. まとめ

本構想では、**Cursor は API、Codex / Claude Code は Playwright** を用いて利用状況および料金情報を取得し、**WSL バッチ + cron / Task Scheduler** により定期実行する。  
取得したデータは **Google Sheets の raw_* シートおよび raw_pricing シートへ追記**し、以降の **集計・整形・通知は GAS** で実施する。

料金データについては、各サービスの **基本料金**（月額単価からの内部計算）と **オンデマンド料金**（API / Playwright からの取得）を `raw_pricing` シートに蓄積し、GAS により **サービス別の基本料金・オンデマンド料金・合計料金** を `pricing_summary` シートへ集計する。

この方式により、各ツールで取得手段が異なる状況でも、運用上は共通のデータ蓄積・可視化基盤を構築できる。  
初期構築は比較的軽量に進めつつ、将来的にはデータ基盤やダッシュボードへ拡張可能な構成とする。

---

## 16. 一言で表す構成

**「取得は WSL バッチ、蓄積は Google Sheets raw、料金集計は GAS で基本/オンデマンド/合計」**
