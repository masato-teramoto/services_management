# Cursor料金の取得方法まとめ

## 概要
このシステムでは、Cursor の料金を **基本料金（base）** と **オンデマンド料金（ondemand）** に分けて扱っています。

- **基本料金**: Cursor API から請求額を直接取得せず、設定済みの月額単価とメンバー履歴から日割り計算する
- **オンデマンド料金**: Cursor API (`/teams/spend`) から利用額を取得する
- **最終集計**: 基本料金は `Cursor請求明細` シート、オンデマンド料金は `月次利用データ` シートを元に集計する

---

## 1. 基本料金（base）の取得方法

### 1-1. 取得元
基本料金は API から直接取得していません。
月額単価は `CURSOR_MONTHLY_RATE` という設定値を `Settings` シートから取得しています。

```ts
var getCursorMonthlyRate = () => {
  const raw = getSettingValue("CURSOR_MONTHLY_RATE");
  if (!raw) {
    throw new Error("CURSOR_MONTHLY_RATEが未設定です");
  }
  const rate = Number(raw);
  if (!Number.isFinite(rate)) {
    throw new Error(`CURSOR_MONTHLY_RATEが不正です: ${raw}`);
  }
  return rate;
};
```

### 1-2. 計算に使うデータ
基本料金の計算には次を使います。

- `CURSOR_MONTHLY_RATE`（1ユーザーあたりの月額 USD 単価）
- `Cursorメンバー履歴` シート
  - メールアドレス
  - 請求サイクル
  - 追加日
  - 削除日
  - 稼働日数
- `ユーザー組織履歴` シート
  - 組織按分用
- 請求サイクル情報
  - `cursor: { startDay: 26, cutoffHour: 9 }`

### 1-3. メンバー履歴の更新方法
`fetchCursorData()` の中で、まず Cursor API の `/teams/members` から現在メンバー一覧を取得します。
その後、既存の `Cursorメンバー履歴` と比較して、追加・削除を履歴に反映します。

処理の流れ:
1. `fetchTeamMembers()` で現在メンバー一覧を取得
2. `detectMemberChanges()` で前回との差分を判定
3. 追加メンバーは `addMemberHistory()` で履歴追加
4. 削除メンバーは `updateRemovalDate()` で削除日と稼働日数を更新
5. `recalculateMemberHistoryActiveDays()` で請求サイクル内の稼働日数を再計算

### 1-4. 基本料金の計算方法
基本料金は `buildCursorBaseRowsByOrgHistory(...)` と `buildCursorBillingDetails(...)` で作られます。

#### 月次利用データ用の基本料金行
`buildCursorBaseRowsByOrgHistory(...)` では、各メンバーの稼働期間を組織履歴に応じて分割し、
各組織に対して基本料金行を作ります。行の `chargeType` は `base` です。

#### 請求明細用の基本料金明細
`buildCursorBillingDetails(...)` では、請求明細を次の 3 種類で作成します。

- `regular`: サイクル開始時点で在籍していたメンバー分
- `member_add`: サイクル途中で追加されたメンバーの日割り分
- `member_remove`: サイクル途中で削除されたメンバーの返金相当（マイナス計上）

計算式は `calculateProratedAmount(totalAmount, activeDays, cycleDays)` により、
概ね次の式です。

```text
基本料金USD = 月額単価USD × 稼働日数 ÷ 請求サイクル日数
```

### 1-5. 基本料金の計上先
基本料金は最終的に次の 2 か所に反映されます。

- `Cursor請求明細` シート
  - `proratedUsd`, `proratedJpy` として保存
- `月次利用データ` シート
  - `service = cursor`
  - `chargeType = base`
  - `baseFeeUsd` に保存

### 1-6. 基本料金の最終集計
`calculateCursorAmounts(accountingMonth)` では、基本料金は `Cursor請求明細` シートから集計します。

```ts
const details = getBillingDetailsByMonth(accountingMonth);
const baseUsd = roundToTwoDecimals(details.reduce((sum, detail) => sum + detail.proratedUsd, 0));
const baseJpy = roundToTwoDecimals(details.reduce((sum, detail) => sum + detail.proratedJpy, 0));
```

つまり、**基本料金の最終値は API の請求額ではなく、内部計算した明細の合計値**です。

---

## 2. オンデマンド料金（ondemand）の取得方法

### 2-1. 取得元
オンデマンド料金は Cursor API から取得しています。
使用 API は以下です。

- **Endpoint**: `POST https://api.cursor.com/teams/spend`
- **認証**: Script Properties の `CURSOR_API_KEY` を使った Basic 認証

認証ヘッダは `buildAuthHeader()` で作っています。

```ts
var buildAuthHeader = () => {
  const apiKey = getApiKey();
  const encoded = Utilities.base64Encode(`${apiKey}:`);
  return `Basic ${encoded}`;
};
```

### 2-2. API取得処理
`fetchTeamSpend()` が `/teams/spend` をページングしながら取得します。

- `method: "post"`
- `sortBy: "amount"`
- `sortDirection: "desc"`
- `page`
- `pageSize`

レスポンスの `teamMemberSpend` を全ページ分 `allSpend` に追加します。

### 2-3. APIレスポンスからのオンデマンドUSD生成
取得した `spendData.spend` に対し、`buildOnDemandUsdMap(spendData)` でユーザー別 USD マップを作成します。

ここではレスポンス中の `spendCents` を 100 で割って USD に変換しています。

```ts
const spendCents = Number(item.spendCents ?? 0);
const onDemandUsd = spendCents / 100;
```

つまり、**オンデマンド料金は Cursor API が返す `spendCents` を USD 化したもの**です。

### 2-4. 月次利用データへの反映
`fetchCursorData()` では、`fetchTeamSpend()` → `buildOnDemandUsdMap(spendData)` の結果を使って、
ユーザーごとのオンデマンド行を `月次利用データ` に作成しています。

作成される行の特徴:

- `service: "cursor"`
- `chargeType: "ondemand"`
- `onDemandUsd: APIから取得した利用額USD`
- `totalUsd: onDemandUsd`
- `baseFeeUsd: 0`

また、オンデマンドは請求サイクル月の **翌月計上** になるように処理されています。

### 2-5. オンデマンドの再計算
`recalculateCursorForCycle(cycleYearMonth)` では API を再度叩かず、
既に `月次利用データ` にある `cursor / ondemand` 行から `buildOnDemandUsdMapFromMonthlyRows(...)` で再構築しています。

つまり再計算時は、**保存済みの月次利用データをソースとして再利用**します。

### 2-6. オンデマンドの最終集計
`calculateCursorAmounts(accountingMonth)` では、オンデマンドは `月次利用データ` から集計します。

```ts
const monthlyData = getMonthlyData(accountingMonth).filter(
  (row) => row.service === "cursor" && row.chargeType === "ondemand"
);
const onDemandUsd = roundToTwoDecimals(monthlyData.reduce((sum, row) => sum + row.totalUsd, 0));
const onDemandJpy = roundToTwoDecimals(monthlyData.reduce((sum, row) => sum + row.amountJpy, 0));
```

つまり、**オンデマンドの最終値は `月次利用データ` の `cursor / ondemand` 行の合計**です。

---

## 3. APIとシートの役割分担

### APIから取得しているもの
- `/teams/members`
  - 現在の Cursor メンバー一覧
- `/teams/spend`
  - ユーザー別オンデマンド利用額 (`spendCents`)

### シートや設定値から取得しているもの
- `Settings` シート
  - `CURSOR_MONTHLY_RATE`
  - 為替レート（`PROVISIONAL_RATE_YYYY_MM`）
- `Cursorメンバー履歴` シート
  - 追加・削除履歴
  - 稼働日数
- `ユーザー組織履歴` シート
  - 組織按分のための所属履歴
- `月次利用データ` シート
  - base / ondemand の月次行
- `Cursor請求明細` シート
  - 基本料金の計算明細

---

## 4. まとめ

### 基本料金
- **取得方法**: APIではなく内部計算
- **元データ**: `CURSOR_MONTHLY_RATE` + `Cursorメンバー履歴` + 請求サイクル
- **計算式**: 月額単価 × 稼働日数 ÷ サイクル日数
- **最終集計元**: `Cursor請求明細`

### オンデマンド料金
- **取得方法**: Cursor API `/teams/spend`
- **元データ**: API レスポンスの `spendCents`
- **変換方法**: `spendCents / 100` で USD 化
- **最終集計元**: `月次利用データ` の `cursor / ondemand`

### 一言で言うと
- **基本料金は「設定値と履歴から計算」**
- **オンデマンド料金は「Cursor API から取得」**
