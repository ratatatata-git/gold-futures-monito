name: Validate COMEX PDFs

on:
  push:
    paths:
      - "data/cme-pg62/**/*.pdf"
      - "data/cme-pg64/**/*.pdf"
      - "scripts/**/*.py"
      - "tests/test_comex_v5.py"
      - ".github/workflows/validate_comex.yml"

  pull_request:
    paths:
      - "data/cme-pg62/**/*.pdf"
      - "data/cme-pg64/**/*.pdf"
      - "scripts/**/*.py"
      - "tests/test_comex_v5.py"
      - ".github/workflows/validate_comex.yml"

  workflow_dispatch:

permissions:
  contents: read

jobs:
  validate-comex:
    name: Validate COMEX PG62 / PG64
    runs-on: ubuntu-latest

    steps:

      # ------------------------------------------------------------
      # Checkout
      # ------------------------------------------------------------

      - name: Checkout repository
        uses: actions/checkout@v4

      # ------------------------------------------------------------
      # Python
      # ------------------------------------------------------------

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      # ------------------------------------------------------------
      # Install dependencies
      # ------------------------------------------------------------

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip

          if [ -f requirements.txt ]; then
            pip install -r requirements.txt
          fi

          if [ -f pg64-requirements.txt ]; then
            pip install -r pg64-requirements.txt
          fi

          pip install pytest pdfplumber

      # ------------------------------------------------------------
      # Repository structure
      # ------------------------------------------------------------

      - name: Show repository structure
        run: |
          echo "========================================"
          echo "Repository"
          echo "========================================"
          pwd
          find . -maxdepth 3 -type f | sort

          echo ""
          echo "========================================"
          echo "PG62 PDFs"
          echo "========================================"
          find data/cme-pg62 \
            -maxdepth 1 \
            -type f \
            -name "*.pdf" \
            -print \
            2>/dev/null || true

          echo ""
          echo "========================================"
          echo "PG64 PDFs"
          echo "========================================"
          find data/cme-pg64 \
            -maxdepth 1 \
            -type f \
            -name "*.pdf" \
            -print \
            2>/dev/null || true

          echo ""
          echo "========================================"
          echo "Parser scripts"
          echo "========================================"
          find scripts \
            -maxdepth 1 \
            -type f \
            -name "*.py" \
            -print \
            2>/dev/null || true

      # ------------------------------------------------------------
      # Required files
      # ------------------------------------------------------------

      - name: Check required parser files
        run: |
          set -e

          test -f scripts/parse_pg62_v5.py
          test -f scripts/parse_pg64_v5.py
          test -f tests/test_comex_v5.py

          echo "Required parser/test files exist."

      # ------------------------------------------------------------
      # Required fixture PDFs
      # ------------------------------------------------------------

      - name: Check COMEX fixture PDFs
        run: |
          set -e

          test -f data/cme-pg62/PG62_2026-09-23.pdf
          test -f data/cme-pg62/PG62_2026-09-25.pdf
          test -f data/cme-pg64/PG64_2026-09-25.pdf

          echo "Required COMEX fixture PDFs exist."

      # ------------------------------------------------------------
      # Python compile check
      # ------------------------------------------------------------

      - name: Compile parser and test files
        run: |
          python -m py_compile \
            scripts/parse_pg62_v5.py \
            scripts/parse_pg64_v5.py \
            tests/test_comex_v5.py

          echo "Python compilation passed."

      # ------------------------------------------------------------
      # v5 integration tests
      # ------------------------------------------------------------

      - name: Run COMEX v5 integration tests
        run: |
          pytest -q tests/test_comex_v5.py

      # ------------------------------------------------------------
      # Summary
      # ------------------------------------------------------------

      - name: Validation summary
        if: success()
        run: |
          echo "========================================"
          echo "COMEX VALIDATION PASSED"
          echo "========================================"
          echo "PG62:"
          echo "  2026-09-23 FINAL"
          echo "  2026-09-25 PRELIMINARY"
          echo ""
          echo "PG64:"
          echo "  2026-09-25 diagnostic/audit only"
          echo ""
          echo "Production MASTER:"
          echo "  PG62: validation target"
          echo "  PG64: BLOCKED_DIAGNOSTIC_ONLY"
          echo "========================================"
