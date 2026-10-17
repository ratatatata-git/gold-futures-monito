# PG62／PG64 パーサー出力の原本来歴チェック

このローカル専用チェックは、登録済みPDFのマニフェストとパーサー出力の間で、原本SHA-256、資料種別、日付、版種、取得ページ数などの来歴情報が一致するかを確認する。

## 対象と制約

- PG62：`scripts/parse_pg62.py` が生成したGC先物MASTER JSON。
- PG64：`scripts/parse_pg64.py` が生成した診断AUDIT JSON。PG64は診断専用であり、本ツールによって本番MASTERへ昇格しない。
- 入力・出力はローカルに保持し、実PDF・実数値・監査ファイルを公開リポジトリへコミットしない。
- `PROVENANCE_MATCH` は来歴の一致だけを意味する。抽出精度、ページ・行の網羅性、履歴更新、公開権利を認定しない。

## 実行

1. 公式の取得条件に従って原本PDFを取得する。
2. 原本上の日付・版種を確認し、`scripts/register_pdf_revision.py` でローカルマニフェストを作成する。
3. PG62またはPG64の既存パーサーを実行し、出力JSONを生成する。
4. マニフェストとパーサー出力を突き合わせる。

例：

```sh
python scripts/validate_pdf_parser_provenance.py \
  --manifest /secure/local/manifests/PG62-2026-10-15.json \
  --artifact /secure/local/parser-output/PG62-master.json \
  --output /secure/local/reports/PG62-provenance-check.json
```

PG64の場合は`--artifact`にAUDIT JSONを指定する。実際のパスはローカル環境に合わせる。

## ブロック条件

- マニフェストがローカル登録状態ではない、または公開承認フラグがtrue
- 資料種別とパーサー出力のdatasetが不一致
- SHA-256または取引日が不一致
- PG62の版種が一致しない
- PG64の版種候補がマニフェストの版種と一意に一致しない
- 出力側にページ数がある場合、マニフェストと一致しない
- 出力先ファイルがすでに存在する

## 次の品質ゲート

来歴チェックが成功しても、次の作業は別途必要：

1. PDFの全ページを確認し、抽出範囲の欠落を確認する。
2. 原本から独立に転記したraw tokenと抽出値を`validate_pdf_reconciliation.py`で照合する。
3. PG62はMASTERの合計・構造チェックに加えて、原本の値・符号・列対応を確認する。
4. PG64は診断状態のまま、未知商品・満期・CALL/PUT・行構造等の未解決項目を解消する。来歴一致だけで本番化しない。
5. 版差分を確認し、権利審査・履歴更新・ロールバックは独立したゲートとして扱う。

実PDFによる独立照合が完了するまで、Phase 2は未完了とする。
