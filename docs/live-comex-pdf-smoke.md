# 実PDFスモークテスト

`scripts/test_live_comex_pdfs.py` は、リポジトリに保存済みの実PDFを使い、PG62 parser と PG64 diagnostic audit、および PDF SHA-256 と parser output の provenance gate を実行します。CMEサイトからの再ダウンロードは不要です。

## Run locally

```sh
python -m pip install -r pg64-requirements.txt
python scripts/test_live_comex_pdfs.py
```

既定では `data/cme-pg62/` と `data/cme-pg64/` の両方に存在する日付のうち、最も新しい共通日付を自動選択します。現在のリポジトリでは両ディレクトリにある 2026-10-14 の組を選びます。別のPDFを明示する場合:

```sh
python scripts/test_live_comex_pdfs.py \
  --pg62-pdf data/cme-pg62/PG62_2026-10-14.pdf \
  --pg64-pdf data/cme-pg64/PG64_2026-10-14.pdf
```

両方のパスは同時に指定してください。入力PDFはその場で読み込み、コピーや書き換えは行いません。GitHub Actions はPDFとparser関連ファイルが変更された pull request でこのテストを実行します。

## Data handling and interpretation

- PDFのSHA-256、ページ数、日付、版情報と parser の来歴を照合します。
- PG62 は既存の構造・TOTAL検証が PASS であることを要求します。
- PG64 は版ステータスが一意に特定できることを要求し、出力は診断専用のままです。
- 成功は、格納済みの実PDFに対する parser/provenance smoke test の成功を意味します。独立した全ページ確認、セル単位の独立転記照合、再配布権の判断、公開承認を意味しません。
- 実PDFそのものはリポジトリに既に存在しますが、COT/FREDなどの派生データを新たに公開する判断は別途必要です。

Phase 2 は、実PDFの全ページ確認と独立転記値による照合が完了するまで未完了です。
