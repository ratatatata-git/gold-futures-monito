# ローカルPDF独立レビュー・ワークシート生成

このツールは、手元のPG62/PG64 PDFから**未記入のレビュー用JSON**を作ります。PDFのページ数とSHA-256を記録し、全ページのチェック欄を用意します。数値を自動で「独立確認済み」にする機能ではありません。

## 実行例

取得日時は実際に取得した時刻を指定してください。ファイル名から日付・版種を推測しません。

```sh
python -m pip install "pypdf>=5,<7"
python scripts/create_pdf_review_worksheet.py \
  data/cme-pg62/PG62_2026-10-14.pdf \
  --type PG62 \
  --date 2026-10-14 \
  --edition FINAL \
  --source-url "https://www.cmegroup.com/market-data/daily-bulletin.html" \
  --retrieved-at "2026-10-14T23:00:00Z" \
  --output /secure/local-review/PG62-2026-10-14-review.json
```

PG64の場合は入力PDF、`--type PG64`、原本で確認した日付・版種に変更します。上記の取得日時はコマンド形式の例です。実際の取得時刻が不明なら推測せず、取得記録を確認してください。

## 生成後の手順

1. PDFをレンダリングして、ページを実際に目視します。
2. 各ページのレイアウト、表、行、セル位置を記録します。
3. 原本を見て raw token を独立転記し、パーサーの raw token と別々に入力します。期待値をパーサー出力からコピーしないでください。
4. 代表的な通常行に加え、空欄、ゼロ、符号、小数、High/Low、TOTAL、ページ境界などのケースを照合します。
5. すべてのページを確認し、確認者・確認日時・確認済みページを記録します。
6. `python scripts/validate_pdf_reconciliation.py /secure/local-review/PG62-2026-10-14-review.json` を実行します。

初期テンプレートは意図的に未完成です。ページ確認はすべて false、`pages_reviewed` は空、各項目はプレースホルダーで、レビュー者・レビュー日時も空です。未編集テンプレートが合格することはありません。ページチェックリストを埋めただけでも、全行・全セルの網羅性は証明されません。

PDF、数値を含むレビューJSON、抽出データはローカルの適切な保管先に置き、権利確認なしに公開リポジトリへコミットしないでください。このツールは正確性・権利・公開可否を認定しません。PG64は別途昇格審査が完了するまで診断専用です。
