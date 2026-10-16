# PG62／PG64 ローカル版差分ゲート

この手順は、同じ bulletin 種別・日付について、2つの原本マニフェストと各版の独立照合レポートを比較する。原本PDF、マニフェスト、照合レポート、差分JSONはローカルの管理対象保管先に置き、公開リポジトリへ追加しない。

## 前提

1. 各原本を `scripts/register_pdf_revision.py` で登録し、版種をPDF本体で確認する。
2. 各版について `scripts/validate_pdf_reconciliation.py` が `PASS` となる照合レポートを作成する。
3. レポートのSHA-256、ページ数、bulletin種別・日付、版種がそれぞれの原本マニフェストと一致していることを確認する。
4. 旧版と新版の照合範囲・項目IDをできるだけ揃える。追加／削除された項目は差分で明示されるが、網羅性の判断は担当者が行う。

## 実行

```sh
python scripts/compare_pdf_revisions.py \
  --old-manifest /secure/local/manifests/PG62-old.json \
  --old-report /secure/local/reports/PG62-old-reconciliation.json \
  --new-manifest /secure/local/manifests/PG62-new.json \
  --new-report /secure/local/reports/PG62-new-reconciliation.json \
  --output /secure/local/diffs/PG62-revision-diff.json
```

出力先は新規ファイルでなければならない。既存ファイルは上書きしない。差分レポートには原本ハッシュ、版種、ページ数、照合ゲート、項目ごとの raw 値・位置・フィールドの変更、追加／削除されたチェックIDを記録する。

## ブロック条件

- マニフェストまたは照合レポートの形式が不正
- どちらかの照合レポートが未達、または全ページの独立照合が記録されていない
- マニフェストと照合レポートのSHA-256、ページ数、日付、版種が一致しない
- 2つの資料の bulletin 種別または日付が異なる
- SHA-256が同一であり、別版として比較できない
- 公開承認状態が未承認以外になっている

## 終了コードと意味

- `0`：差分を作成できた（`DIFF_READY`）。変更内容が妥当、網羅的、公開可能であることまでは保証しない。
- `1`：検証ゲート未達または入力の不整合。
- `2`：出力先が既存、またはCLIの入出力準備段階でエラー。

## 差分後の必須レビュー

- 変更・追加・削除された各項目を原本上で確認する。
- ページ数や表レイアウトの変化により、照合範囲が欠落していないか確認する。
- FINAL／REVISEDなどの版種を原本の表示で確かめ、同じ日付の履歴を無条件に上書きしない。
- 更新前後の抽出を再実行し、履歴のバックアップとロールバック手順を確認する。
- CFTC／FRED／CMEなどの権利・利用条件と公開可否は、品質検証とは独立して審査する。

`DIFF_READY` は公開承認を意味しない。実PDFと独立確認済みレポートを実行するまでは、Phase 2の実データ検証ゲートは未達のまま扱う。
