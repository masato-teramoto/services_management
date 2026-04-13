# Whileループ非実行の原因
_Exported on 4/6/2026 at 16:15:22 GMT+9 from Cursor (2.3.41)_

---

**User**

525行目のexecuteSqlで1件以上のデータがUPDATEされているのですが、550行目のwhlie分の中にある処理が実行されません。B37_walletCharge.phpと比較して原因を教えてください。ソースコードは変えないでください。

---

**Cursor**

原因は **`B39_pontaCharge.php` 側で `fetchRow()` を先に1回消費していること**です。  
`$sttsResult` の1行目をログ出力で取得してしまっているため、結果が1件だけの場合は `while` に入る時点で残りが0件になり、ループが実行されません。`B37_walletCharge.php` ではこの「先読み」がありません。

```548:551:module/Bat/B39_pontaCharge.php
$clsLogger->WriteBatchLog(LogInfo::LOG_D,$sttsResult->fetchRow(MDB2_FETCHMODE_ASSOC));
// ステータス遷移情報テーブル更新
while ($row = $sttsResult->fetchRow(MDB2_FETCHMODE_ASSOC)) {
    foreach ($row as $key => $val) {
```

一方で `B37_walletCharge.php` では `fetchRow()` の事前消費がなく、取得結果をそのまま `while` で回しています。

```1608:1612:module/Bat/B37_walletCharge.php
// ステータス遷移情報を更新
while ($row = $sttsResult->fetchRow(MDB2_FETCHMODE_ASSOC)) {
    foreach ($row as $key => $val) {
```

つまり、**B39ではログ出力のための `fetchRow()` が原因で、1件しかない結果が消費されてしまう**点がB37との決定的な差分です。  
（ソース変更は不要とのことなので、原因説明のみです。）

---

**User**

該当のログ出力部分を削除しましたが実行されません。

---

**Cursor**

結論：**ログ削除は関係なく、`while` に入らない本質は「`$sttsResult` が0件」**です。  
`B39` では `sttsSql` に `OUTPUT_DATE_RETURN_SECOND is NULL` が固定で入っており、**その条件に合わないと1件も返らず**、`while` は実行されません。

```372:390:module/Bat/B39_pontaCharge.php
$sttsSql = "SELECT ";
...
$sttsSql .= "WHERE ";
$sttsSql .= "    SEQ = ? ";
$sttsSql .= "    AND T_REQUEST.OUTPUT_DATE_RETURN_SECOND is NULL";
```

さらに、`while` 自体は **この `sttsSql` の結果に依存**しています。

```520:550:module/Bat/B39_pontaCharge.php
$sttsResult = $cdb->executeSql($sttsSql, $type, $data);
...
while ($row = $sttsResult->fetchRow(MDB2_FETCHMODE_ASSOC)) {
```

### B37との比較でのポイント
- `B37` も同じ条件 (`OUTPUT_DATE_RETURN_SECOND is NULL`) ですが、**B37で処理対象となるデータはその条件を満たすケースが多い**前提です。
- `B39` は `OUTPUT_DATE_PONTA_CHARGE` を更新対象にしているため、**`OUTPUT_DATE_RETURN_SECOND` が既に埋まっているデータが混ざると即0件**になります。

### もう1つの入口条件
`B39` では **除外SEQチェック**もあるので、ここで弾かれている可能性もあります。

```520:521:module/Bat/B39_pontaCharge.php
if(is_null($exclusion_seq_list) || !in_array($seq, $exclusion_seq_list, true)) {
```

---

## 確認すべきこと（ソース変更不要）
- 対象SEQの `T_REQUEST.OUTPUT_DATE_RETURN_SECOND` が **NULLかどうか**
- `getExclusionSeq()` に対象SEQが **含まれていないか**

この2点がどちらかに該当すると、ログ削除後でも `while` は実行されません。

