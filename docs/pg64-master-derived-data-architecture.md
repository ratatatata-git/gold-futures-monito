# PG64マスター／派生データ設計案

- ステータス：設計レビュー用ドラフト。実装・本番データはまだ変更しない。
- 原則：PDF原本と抽出証拠を保持し、正規化・判定・分析は再生成可能な派生データとして分離する。

## 1. データ層と依存関係

~~~text
公式PDF原本 + 出典メタデータ
        |
        v
PG64 Master（全ページ／全セクション／全表の抽出証拠）
        |
        +--> Options Normalized（満期・CALL/PUT・ストライク・掲載指標）
        |         +--> OI集中帯・IV・ガンマ関連推定
        |
PG62等の先物原資料
        |
        v
Contract Daily（取引日・商品・限月別の価格／出来高／OI）
        |
        v
Active Contract Decisions（中心限月判定履歴）
        |
        v
Continuous Series（未調整／調整済み価格）
        |
        v
Webアプリ
~~~

PG64はオプション系のデータ源、PG62等は先物の限月別データ源として扱う。PG64からGC先物のOHLCやOIを推測しない。共通日付・商品情報を使って分析段階で必要なデータを結合する。

派生データには入力マスターのSHA-256、生成コードのバージョン、スキーマ／ルールのバージョンを記録する。ロジックを変えた際に影響範囲を特定し、該当する派生データを再生成できるようにする。

## 2. ファイル構成案

既存の構成を確認したうえで採用する。これは論理案であり、すべてのディレクトリを直ちに新設する指示ではない。

~~~text
data/
  cme-pg64/
    raw/             # 公式PDF原本
    master/          # 日付単位の抽出マスター
  cme-pg62/
    raw/
    master/
  derived/
    options-analysis/
    contract-daily/
    active-contract/
    continuous-series/
  schemas/
    pg64-master.schema.json
    options-analysis.schema.json
    contract-daily.schema.json
    active-contract.schema.json
    continuous-series.schema.json
~~~

マスターは監査・再処理用、派生データは分析・表示用とする。公開Webアプリに巨大なマスター全体を直接読み込ませることは前提にしない。Git管理容量や公開データサイズを確認し、必要なら保管先や分割方法を見直す。

## 3. PG64マスターの基本構造

マスターは文書→ページ→セクション→表→行→セル／トークンの階層を保持する。抽出できなかった情報や意味を確定できない情報も捨てず、未解決状態として残す。

以下は構造例であり、実際のCMEデータではない。

~~~json
{
  "schema_version": "pg64-master-v1",
  "document": {
    "source": "CME Daily Bulletin",
    "bulletin_type": "PG64",
    "bulletin_date": "YYYY-MM-DD",
    "bulletin_number": null,
    "publication_status": "unknown",
    "original_filename": "PG64_YYYY-MM-DD.pdf",
    "sha256": "<sha256>",
    "page_count": 0
  },
  "extraction": {
    "parser_name": "pg64-parser",
    "parser_version": "<version-or-commit>",
    "extracted_at": "<ISO-8601 timestamp>",
    "status": "diagnostic_only",
    "warnings": []
  },
  "pages": [
    {
      "page_number": 1,
      "sections": [
        {
          "section_id": "p1-s1",
          "heading_raw": null,
          "semantic_type": "unresolved",
          "tables": [
            {
              "table_id": "p1-s1-t1",
              "headers": [],
              "rows": [
                {
                  "row_id": "p1-s1-t1-r1",
                  "row_key_raw": null,
                  "row_status": "unresolved",
                  "cells": [
                    {
                      "column_label_raw": null,
                      "raw_tokens": [
                        {
                          "text": "----",
                          "bbox": [0, 0, 0, 0],
                          "token_order": 0
                        }
                      ],
                      "normalized_value": null,
                      "value_type": "unresolved",
                      "parse_status": "not_parsed"
                    }
                  ],
                  "issues": []
                }
              ],
              "issues": []
            }
          ],
          "issues": []
        }
      ]
    }
  ],
  "audit": {
    "pages_seen": 0,
    "sections_seen": 0,
    "tables_seen": 0,
    "rows_seen": 0,
    "resolved_rows": 0,
    "unresolved_rows": 0,
    "issues": []
  }
}
~~~

### 3.1 保存ルール

- 文書の同一性はファイル名だけで判断せず、SHA-256で識別する。
- PDF内の日付とファイル名の日付が異なる場合、片方に黙って寄せず警告する。
- ページ番号は原本への追跡用であり、限月・行の意味を決めるキーにしない。
- raw_tokensの文字列は抽出時のまま保存し、正規化で上書きしない。
- bboxは位置の証拠として保存する。絶対座標だけで全ページ共通の列や限月を決めない。座標系と単位はスキーマで明記する。
- 列見出しや行の意味が確定できない場合はnull／unresolvedとし、隣の値や並び順から推測して埋めない。
- 0、空欄、----、UNCH、符号付き値を同じ状態に潰さない。
- parse_statusは少なくともparsed、not_parsed、ambiguous、not_applicableを区別する。
- auditの件数一致は抽出正確性の証明ではない。実PDFとの照合状況を別に記録する。

### 3.2 値の表現

各値は可能な範囲で以下を分けて保持する。

- raw_tokens：PDFから抽出した文字列と位置情報。
- normalized_value：定義済み規則で変換した値。未確定ならnull。
- value_type：整数、十進数、文字列、複合値、未解決など。
- parse_status：変換の成否や曖昧さ。
- issues：未知の表記、列ずれ候補、複数解釈など。

High／LowのB/A表記など複合値の可能性があるものは、検証済みの規則がない限り単一数値へ無理に分割しない。

## 4. 派生データの責務

### 4.1 Options Normalized

PG64マスターから、分析用の正規化オプションレコードを生成する。候補項目は基準日、商品コード、CALL／PUT、満期、ストライク、PDFに実際に掲載されたOI・OI変化・出来高・IV等、各値のraw token／正規化値／解析状態、抽出元ページ・表・行参照、入力マスターのハッシュ。掲載項目・単位・意味は実PDFの見出しで確認してから確定する。

### 4.2 Contract Daily

PG62等の先物データ源から、取引日＋商品コード＋限月コードをキーに価格、出来高、OI等を保存する。OHLC、Settlement、Volume、OI、OI Changeは原資料で確認できる項目に限る。

### 4.3 Active Contract Decisions

日付ごとの中心限月選択と判定理由を保存する。選択限月、比較候補、各候補の出来高・OI、受渡し関連日付などの制約、判定ルールID／バージョン、判定状態、理由、警告、入力データ参照を含める。

出来高最大だけで確定しない。出来高・OIの移行、受渡し関連日付、複数日の持続性を組み合わせるルールを実データで評価する。根拠不足ならunresolvedとする。判定履歴は後日訂正されても過去の判定を追跡できるようにする。

### 4.4 Continuous Series

中心限月判定からチャート用時系列を生成する。取引日、採用限月、選択限月の実価格、ロールイベント、旧限月／新限月、ロール時の価格差、調整方式、調整後価格、入力判定データIDとルールバージョンを保存する。

未調整価格と調整済み価格を区別する。出来高・OIを価格と同じ方法で調整しない。限月ごとのOIと市場全体のOI、ロールによる建玉移動を区別する。

## 5. 再生成・更新ルール

1. 原本PDFは変更せず保存し、SHA-256で同一性を確認する。
2. パーサー変更時は同じ原本からマスターを再生成し、旧出力との差分を確認する。
3. 派生データに入力ハッシュとコード／ルールのバージョンを記録する。
4. 重大な未解決問題があるマスターは診断用として保持しても、確定済み分析データや本番履歴へ昇格させない。
5. 中心限月ルールや価格調整方法の変更時は、該当する派生データを再生成し、変更前後を比較する。
6. 同一入力・同一コード・同一設定で、生成時刻などを除く内容が再現することを確認する。
7. 件数やTOTALの一致だけで個別レコードの正しさを保証しない。

## 6. 実装フェーズと最初の受け入れ条件

### M1：スキーマと保存契約
- [ ] 実PG64 PDFを見て文書・セクション・表・行・セルのモデルを調整する。
- [ ] pg64-master-v1のJSON Schemaを作成する。
- [ ] 元トークン、位置情報、解決状態、出典参照の必須ルールを決める。

### M2：実PDF 1件のマスター生成
- [ ] 1件の実PDFについて全ページ・全セクションを処理する。
- [ ] 未解決レコードを失わず記録する。
- [ ] ページ／セクション別の件数と問題一覧を出す。
- [ ] 人手で確認した対象範囲と比較できるレポートを作る。
- [ ] 同じPDFを再処理した結果が再現することを確認する。

### M3：派生データ
- [ ] PG64マスターからオプション分析用データを生成する。
- [ ] PG62等から限月別先物データを生成する。
- [ ] 中心限月判定を独立して生成・保存する。
- [ ] 中心限月判定から連続チャート用データを生成する。

### M4：履歴・Web連携
- [ ] 複数日のマスターと派生データを管理する。
- [ ] Webアプリは必要な派生データを読み込み、巨大なマスター全体を直接読み込まない。
- [ ] 基準日、診断／確定状態、ロールマーカー、価格調整方式を表示する。

初期実装はテスト件数ではなく、実PG64 PDF 1件を全ページ対象でマスター化し、抽出トークンから原本箇所へ追跡でき、未解決項目を隠さず、確認済み範囲と比較でき、そこからオプション派生データを生成できることをもって評価する。中心限月判定と連続チャートはPG64の合格条件に混ぜず、PG62等の先物データ層を使って別段階で検証する。
