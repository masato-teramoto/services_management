# プランカテゴリーとアカウント件数の処理一覧
_Exported on 4/6/2026 at 15:38:52 GMT+9 from Cursor (2.3.41)_

---

**User**

プランカテゴリー(planCategory)、アカウント件数(accountCountCategory)を使用した処理をしているファイルを一覧にしてください。それぞれどのような処理を行っているかも説明してください。

---

**Cursor**

それぞれの変数（`planCategory` と `accountCountCategory`）は、主に「プランの種別管理」と「画面上のアカウント入力項目の表示制御」という目的で使用されています。

以下に、それぞれを使用しているファイルとその処理内容をまとめました。

---

### 1. `planCategory`（プランカテゴリー）について
プランのカテゴリー（例: `0`=優先プラン(Priority Plan), `1`=プールプラン(Pooled Plan) など）を表し、アカウントとプランを紐付けるためのグループ分けとして利用されています。

#### 該当ファイルと処理内容

**① 画面表示・フロントエンド処理**
* **`src/main/resources/templates/scripts/account-selector-modal-script.html`**
  * アカウント選択モーダル内で、値が `0` なら「優先プラン」、`1` なら「プールプラン」というラベルに変換し、一覧表（テーブル）に表示する処理を行っています。
* **`src/main/resources/templates/modal/account-selector-modal.html`**
  * アカウント選択モーダル内のテーブルのヘッダー（列名）「プランカテゴリー」の表示定義をしています。
* **`src/main/resources/templates/regist.html`** / **`refer.html`**
  * プランを選択するセレクトボックスのカスタム属性（`data-planCategory`）として値を保持し、選択された際に隠しフィールド(`input type="hidden"`)にセットしてサーバーに送信する準備をしています。
* **`src/main/resources/messages_ja.yml`**
  * 画面に表示する「プランカテゴリー」という日本語ラベルの定義ファイルです。

**② データベースへのアクセス（MyBatis Mapper）とエンティティ**
* **`src/main/resources/com/kddi/starlinkadmin/domain/mapper/MPlanMasterMapper.xml`**
* **`src/main/resources/com/kddi/starlinkadmin/domain/mapper/AccountMasterMapper.xml`**
  * SQLの `WHERE PLAN_CATEGORY = #{planCategory}` のように、特定のプランカテゴリーに属するプラン一覧やアカウント一覧をDBから「検索・カウント」するための絞り込み条件として使用しています。
* **`src/main/java/.../domain/entity/MPlanMaster.java`**
* **`src/main/java/.../domain/entity/AccountMaster.java`**
  * データベースのテーブル（プランマスタ、アカウントマスタ）からデータを格納するためのクラスプロパティとして定義されています。

**③ サーバーサイドのビジネスロジック・バリデーション**
* **`src/main/java/.../function/.../RegistService.java`**, **`SearchUtService.java`**, **`DeleteUtLinkService.java`**, **`ReferService.java`**
  * マッパーを呼び出す際に、検索条件（`planCategory = 1` など）をMap等にセットし、特定カテゴリーのアカウント件数や情報を取得する処理を行っています。
* **`src/main/java/.../common/validation/AccountPlanAssociationValidator.java`**
  * **相関チェック（バリデーション）：** ユーザーが選択した「アカウントのプランカテゴリ」と、「選択したプラン自身のプランカテゴリ」が一致しているかを検証し、不整合があればエラーにする処理を行っています。

---

### 2. `accountCountCategory`（アカウント件数 / 表示制御フラグ）について
プランに対してアカウントを紐付ける必要があるかどうか（アカウントの要否）を示すフラグです。（`1`＝アカウント選択が必要、`0`＝アカウント選択は不要）

#### 該当ファイルと処理内容

**① 画面表示・フロントエンド処理（動的UI切り替え）**
* **`src/main/resources/templates/regist.html`**
* **`src/main/resources/static/js/custom.js`**
  * ユーザーがセレクトボックスでプランを選択・変更した際、そのプランの `data-accountCountCategory` を取得します。
  * その値が **`1` の場合は「利用アカウント」の入力項目群を画面に表示 (`display: block`) し、`0` の場合は非表示 (`display: none`) にする**という、画面UIの切り替え処理を行っています。
  * `0`（非表示）の際は、選択されていたアカウント情報（Account Number等）をクリアする処理も行っています。

**② データベースへのアクセス（MyBatis Mapper）とエンティティ**
* **`src/main/resources/com/kddi/starlinkadmin/domain/mapper/MPlanMasterMapper.xml`**
  * データベース上の `ACCOUNT_COUNT` カラムの値をSQLで取得し、Java側で扱いやすいように `accountCountCategory` というエイリアス名（別名）にマッピングして取得しています。
* **`src/main/java/.../domain/entity/MPlanMaster.java`**
  * エンティティ内のプロパティ変数として定義されています。

**③ サーバーサイドのビジネスロジック・バリデーション**
* **`src/main/java/.../function/O004/RegistForm.java`**
  * 画面から送信されるフォームデータを受け取るための変数として定義されています。また、後述のバリデーションに値を渡しています。
* **`src/main/java/.../common/validation/AccountExistValidator.java`**
  * **存在チェック（バリデーション）：** `accountCountCategory` の値が `0`（画面上でアカウントを選択させないプラン）であった場合、システム内部で「そのプランカテゴリー(`planCategory`)に紐づくアカウントがDB上に最低1件以上存在しているか」を確認する処理を行っています。

