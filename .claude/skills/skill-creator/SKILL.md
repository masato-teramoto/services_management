---
name: skill-creator
description: Create reusable Skills/Rules for Claude Code and/or Cursor through a guided Q&A. Use when the user wants to author a new Skill, convert an existing workflow or doc into a Skill, or port a Skill between Claude and Cursor. Triggers on phrases like "Skillを作りたい", "create a skill", "make a cursor rule", "turn this workflow into a skill".
---

# Skill Creator

Claude Code向け Skill（`.claude/skills/<name>/SKILL.md`）および Cursor向け Skill/Rule（`.cursor/skills/<name>/SKILL.md` または `.cursor/rules/<name>.mdc`）を、ユーザーとの質疑応答だけで生成するメタSkill。

## いつ起動するか

- ユーザーが「Skillを作りたい／作って」「スキル化したい」「Cursor用のルールを作りたい」と明示した時
- 既存のワークフロー・手順書・READMEを Skill化したいと依頼された時
- 既存 Skill を別ツール向けに変換したい時

## 前提: 両形式の差分

| 項目 | Claude Code | Cursor |
|---|---|---|
| パス | `~/.claude/skills/<name>/SKILL.md`（グローバル）/ `.claude/skills/<name>/SKILL.md`（プロジェクト） | `.cursor/skills/<name>/SKILL.md`（本リポジトリ規約）/ `.cursor/rules/<name>.mdc`（従来形式） |
| frontmatter必須 | `name`, `description` | `description`（`globs`, `alwaysApply` は任意） |
| name規則 | ケバブケース | ファイル名がIDになる |
| description言語 | 発火精度のため英語推奨 | 同左 |
| 本文 | Markdown | Markdown / `.mdc` |

## ワークフロー

起動したら必ず TodoWrite でこのワークフローをタスク化し、1つずつ `in_progress` にして進める。

### Step 1. ターゲット確認

最初の質問で以下を確定する（`AskUserQuestion` を使用）：
- 対象ツール: **Claude Code** / **Cursor** / **両方**
- 配置スコープ: **プロジェクト**（`.claude/skills/` or `.cursor/skills/`）/ **ユーザーグローバル**（`~/.claude/skills/` など）/ **両方**

### Step 2. 質問フェーズ

下記「質問リスト」を上から順に、**1問ずつ** `AskUserQuestion` で尋ねる。選択肢があるものは選択式に、自由記述は選択肢なしで提示。任意項目は「不要」を選択肢に含める。

途中で不足が判明したら追加質問、不要と判断したら省略してよい。

### Step 3. ドラフト生成

集めた回答を後述「テンプレート」に流し込み、本文ドラフトをユーザーに提示する。Bashやコマンド列、参照ファイルパスは具体的に埋める。

### Step 4. レビュー

ドラフトを表示して「この内容で書き出してよいか」を確認。修正要求があれば該当箇所だけ直して再提示。

### Step 5. 書き出し

承認されたら、対象ツール × スコープの組み合わせ分、ファイルを作成する：
- Claude: `<scope>/.claude/skills/<skill-name>/SKILL.md`
- Cursor: `<scope>/.cursor/skills/<skill-name>/SKILL.md`

ディレクトリは `mkdir -p` で作成。既存ファイルがある場合は上書き可否を確認。

### Step 6. 動作確認の案内

- Claude Code: 新セッションで `/<skill-name>` が出るか、または描写に合う依頼で自動起動するかを確認する旨を伝える
- Cursor: Settings → Rules/Skills で読み込まれているか確認する旨を伝える

Gitコミットの指示があれば `git add` → コミットメッセージ草案 → 承認 → コミットまで行う（push はユーザーの明示がない限り行わない）。

## 質問リスト

### A. 基本情報（必須）

1. **Skill名** — ケバブケース（例: `api-migrator`）
2. **対象ツール** — Claude Code / Cursor / 両方
3. **配置スコープ** — プロジェクト / ユーザーグローバル / 両方
4. **目的** — このSkillは何をするものか、1〜2文で
5. **発火条件（description本文）** — どんな時に使わせたいか、具体的シナリオを2〜3個

### B. 動作内容（必須）

6. **入力** — ユーザーから受け取る情報・ファイル・引数
7. **主要ステップ** — 実行手順（何を、どの順で）
8. **出力形式** — テキスト / コード / ファイル作成 / コミットなど、および出力言語

### C. 参照・制約（任意）

9. **参照ファイル/URL/既存ドキュメント** — Skill本文に取り込む資料
10. **使用ツール指定** — 例: `Bash` 禁止、`Grep` 優先
11. **禁則事項** — 破壊的操作、特定ディレクトリ除外など
12. **入出力サンプル** — Few-shot用の例

### D. Cursor固有（対象が Cursor の場合のみ）

13. **`globs`** — 適用対象ファイルパターン（例: `**/*.ts`）。不要なら空
14. **`alwaysApply`** — 常時適用か、description一致時のみか

### E. 公開・運用（任意）

15. **本文言語** — 日本語 / 英語
16. **作者/バージョンメタ** — 記載するか
17. **Git管理** — 作成後に `git add` / コミットまで行うか

## テンプレート

### Claude Code 用 (`SKILL.md`)

```markdown
---
name: <skill-name>
description: <英語で1〜2文。いつ使うか・トリガーを含める>
---

# <タイトル>

<目的を1〜2文で>

## いつ起動するか

- <シナリオ1>
- <シナリオ2>

## ワークフロー

起動したら TodoWrite で以下をタスク化し、1つずつ進める。

### Step 1. <ステップ名>
<詳細>

### Step 2. <ステップ名>
<詳細>

## 入力

- <入力1>
- <入力2>

## 出力

- <出力形式>

## 参照

- <ファイル/URL>

## 禁則事項

- <やってはいけないこと>
```

### Cursor 用（`.cursor/skills/<name>/SKILL.md` 形式）

```markdown
---
description: <英語で1〜2文>
globs: <該当パターン or 空>
alwaysApply: <true/false>
---

# <タイトル>

<以下、Claude版と同構成>
```

## バリデーション

書き出し前に以下を必ずチェック：
- `name` がケバブケース（`^[a-z0-9]+(-[a-z0-9]+)*$`）
- `description` が空でない。目安80〜200文字。英語推奨の旨をユーザーに告げる
- Claude用 frontmatter に `name` と `description` が存在
- Cursor用 frontmatter に `description` が存在
- Skillディレクトリ名 と `name` が一致
- 本文に「いつ使うか」「ステップ」「入出力」が含まれる

## 禁則事項

- ユーザーの明示承認なしに既存の Skill ファイルを上書きしない
- 明示承認なしに `git push` しない
- frontmatter の `name` とディレクトリ名を不一致のまま書き出さない
- 質問を一度にまとめて投げない（1問ずつ対話する）
