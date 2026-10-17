# PG62／PG64 実PDF照合レポート

- 状態：検証支援ツール。実PDFの正確性や公開可否を自動認定するものではない。
- 対象：PG62／PG64の原本と抽出結果を、人が独立確認した値で照合するためのローカルレポート。
- データ取扱い：実PDF、抽出データ、実際の数値を含むレポートを公開リポジトリへ追加しない。権利・保存条件を確認した保管先で管理する。

## 目的と境界

`scripts/validate_pdf_reconciliation.py` は、レビュー記録が必要項目を備え、全ページのレビューが記録され、独立に転記したraw値と抽出raw値が完全一致するかを検査する。レポートの「合格」フラグは入力値として受け取らず、ツール自身が判定する。

このツールが保証しないこと：

- PDFのダウンロードや内容抽出、PDFが公式原本であることの認証
- 人が記録した参照値の正しさ、または表・行の網羅性そのもの
- 利用規約・著作権・再配布権の承認
- 正規化値や分析値の意味の正しさ

値・符号の差は許容しない。表記上の違いも、照合対象の raw token が異なる場合は不一致として扱い、担当者が原因を調査する。比較のためにカンマや符号などを自動で正規化しない。

## レポート形式

レポートはローカルJSONファイルとする。最低限、次を記録する。

- `schema_version: 1`
- `document`：`bulletin_type`（PG62／PG64）、`bulletin_date`、原本に明記された `edition_status`、`sha256`、`page_count`、出典URL、取得時刻
- `review`：確認者、確認時刻、`method: independent_manual_pdf`
- `pages_reviewed`：確認したページ番号の一覧。ページ範囲の全件が必要
- `items`：一意な `check_id`、ページ、表／行／セル等の位置、項目名、PDFを独立確認して転記した `expected_raw`、抽出出力の `extracted_raw`、`independently_verified: true`

例（以下は**合成値のみ**であり、実際のCMEデータではない）：

```json
{
  "schema_version": 1,
  "document": {
    "bulletin_type": "PG62",
    "bulletin_date": "2026-01-01",
    "edition_status": "FINAL",
    "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "page_count": 1,
    "source_url": "https://example.invalid/synthetic-example",
    "retrieved_at": "2026-01-02T00:00:00Z"
  },
  "review": {
    "reviewer": "reviewer-id",
    "reviewed_at": "2026-01-02T01:00:00Z",
    "method": "independent_manual_pdf"
  },
  "pages_reviewed": [1],
  "items": [
    {
      "check_id": "pg62-p1-example-field",
      "page_number": 1,
      "locator": "page 1 / table label / row label / column label",
      "field": "example_raw_field",
      "expected_raw": "SYNTHETIC-123",
      "extracted_raw": "SYNTHETIC-123",
      "independently_verified": true
    }
  ]
}
```

この例はスキーマ・操作説明用であり、実データの fixture や精度証明として使用してはならない。

## 実行方法

実PDFと照合値を含むレポートは、権利と保存場所を確認したうえでローカルに作成する。

```sh
python scripts/validate_pdf_reconciliation.py /path/to/local-report.json
python scripts/validate_pdf_reconciliation.py /path/to/local-report.json --json
python -m unittest discover -s tests -p "test_pdf_reconciliation.py" -v
```

終了コードは、レポートを読み取れない場合は `2`、ゲートが未達の場合は `1`、構造・照合条件を満たした場合は `0`。JSON出力は機械可読の集計とブロッカーを含む。

## ブロッカー条件

- 必須メタデータの欠落、形式不正、SHA-256の形式不正
- PG62／PG64以外の資料種別、無効な日付、ページ数
- すべてのページがレビュー済みとして列挙されていない
- レビュー者・時刻・独立した手作業確認方式が記録されていない
- 照合項目がない、IDが重複している、位置・項目が不明
- 独立確認されていない項目、raw値の欠落、不一致
- 版種が `FINAL` ではない

合格は、記録されたチェックとページ網羅宣言が条件を満たしたことを示すにすぎない。別途、独立レビュー、対象レイアウトの代表性、原本とのトレーサビリティ、権利審査が必要。版種がPRELIMINARY／REVISED／不明の場合は比較・診断に使えても、通常履歴への昇格は認めない。

## 推奨運用フロー

1. 利用条件に従って原本を取得し、原本ファイルのSHA-256とページ数を確認する。
2. 原本上の版種を直接確認する。ファイル名だけでFINALと判断しない。
3. 対象PDFを人が独立して確認し、ページごとに確認範囲を記録する。
4. PDFから転記したraw値と、パーサー出力のraw値を照合項目に記録する。
5. ローカルで検証ツールを実行し、すべての不一致・未確認項目を解消する。
6. 独立レビューと、履歴更新前後の差分・再実行・ロールバック検証を行う。
7. データの公開／再配布は、品質ゲートとは別の権利・公開ゲートで承認する。

実PDFの照合結果がまだない状態では、Phase 2は「検証基盤を用意した」に留まり、「実PDF検証に合格した」とは報告しない。


## ローカル原本リビジョンの登録

`scripts/register_pdf_revision.py` は、手元にあるPDFのSHA-256、バイト数、ページ数を算出し、原本の版種や出典・取得時刻を含むローカルJSONマニフェストを新規作成する。PDFファイル自体は変更せず、マニフェストを公開リポジトリへ追加する必要もない。

```sh
python scripts/register_pdf_revision.py /secure/local/PG62.pdf \
  --type PG62 \
  --date 2026-10-15 \
  --edition FINAL \
  --source-url "https://official-source.example/path" \
  --output /secure/local/manifests/PG62-2026-10-15.json
```

上記のURL・日付・ファイル名はコマンド形式の説明用プレースホルダーであり、実在する取得先や実データを示さない。実行時は公式の取得元と原本表示に基づく値へ置き換える。`--edition` は原本上で確認した版種を明示する。ツールはファイル名から版種を推定しない。既存の出力ファイルは上書きせず、エラーにする。

同じbulletin種別・日付の前版マニフェストを指定すると、前版のSHA-256を親として記録する。

```sh
python scripts/register_pdf_revision.py /secure/local/PG62-revised.pdf \
  --type PG62 \
  --date 2026-10-15 \
  --edition REVISED \
  --source-url "https://official-source.example/path" \
  --parent-manifest /secure/local/manifests/PG62-2026-10-15.json \
  --output /secure/local/manifests/PG62-2026-10-15-revised.json
```

- 親マニフェストとbulletin種別・日付が一致しなければ拒否する。
- 同じSHA-256のファイルは新しいリビジョンとして登録しない。
- PDFが壊れている、暗号化されている、またはページ数を読み取れない場合は登録しない。
- `RAW_REGISTERED_LOCAL_ONLY` はローカルでの登録を意味し、検証済み・権利確認済み・公開承認済みを意味しない。
- 登録後も、抽出、独立照合、版差分レビュー、公開権利審査は別々に必要。


## ローカルレビュー用テンプレートの作成

手作業レビューの記録を始める場合は、[`docs/pdf-review-worksheet.md`](pdf-review-worksheet.md) と `scripts/create_pdf_review_worksheet.py` を参照する。生成されるJSONは未完成テンプレートであり、ページ確認・独立転記・レビュー者情報を自動で補完しない。空のテンプレートをそのまま検証ゲートに通すことはできない。
