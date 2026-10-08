#!/usr/bin/env python3
"""PG64 v5 diagnostic-stage parser with product-master driven identification.

This command reads the PDF and reconstructs candidate main-chain structure, but
intentionally does NOT emit a production MASTER yet.

Product identification is deliberately split into:

PDF raw product header
    -> PG64 alias master
    -> canonical product master

The product master is a normalization dictionary, not a source of missing PDF
facts. CALL/PUT and contract month are still taken from the PDF itself.

Unknown product codes are never guessed; they block promotion to production.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber

VERSION = "pg64-gold-v5.0.4-product-master-diagnostic"
DIAGNOSTIC_SCHEMA = "pg64.audit.v5"

DEFAULT_PRODUCT_MASTER = Path(
    "data/master/product/comex_metals_options_product_master_v2.csv"
)

DEFAULT_ALIAS_MASTER = Path(
    "data/master/product/pg64_product_alias_master_v1.csv"
)

MONTH = r"(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\d{2}"
STRIKE = re.compile(r"^\d{2,5}(?:\.\d+)?$")

# Do NOT maintain a hard-coded list such as OG1-OG5 here.
#
# Examples of source headers:
#   OG CALL COMEX GOLD OPTIONS
#   OG5 PUT GOLD OPTIONS
#   GMW MON GOLD WEEKLY MONDAY OPTION Week1
#
# The first token is the raw PG64 display code.
# The master decides whether that code is actually known.
PRODUCT_HEADER = re.compile(
    r"^(?P<code>[A-Z0-9]+)\b"
    r"(?P<rest>.*\bGOLD\b.*\bOPTION(?:S)?\b.*)$",
    re.I,
)

STATUS_TOKENS = {"FINAL", "PRELIMINARY"}

# These are the only product-master status values treated as current.
# CURRENT_OFFICIAL is the status used by the current canonical product master.
CURRENT_PRODUCT_STATUSES = {
    "ACTIVE",
    "CURRENT",
    "CURRENT_OFFICIAL",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def lines(page):
    words = page.extract_words(
        x_tolerance=1,
        y_tolerance=2,
        keep_blank_chars=False,
    )

    out = []
    for w in sorted(words, key=lambda q: (q["top"], q["x0"])):
        g = next(
            (
                z
                for z in reversed(out)
                if abs(w["top"] - z["top"]) < 2.5
            ),
            None,
        )
        if g is None:
            out.append(
                {
                    "top": w["top"],
                    "words": [w],
                }
            )
        else:
            g["words"].append(w)
            g["top"] = (
                sum(x["top"] for x in g["words"])
                / len(g["words"])
            )

    for g in out:
        g["words"].sort(key=lambda q: q["x0"])

    return out


def normalize_header_code(value: str) -> str:
    return norm(value).upper()


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(
            f"Product master file not found: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(
                f"CSV has no header: {path}"
            )
        return [dict(row) for row in reader]


def require_columns(
    rows: list[dict[str, str]],
    path: Path,
    required: set[str],
) -> None:
    if not rows:
        raise ValueError(
            f"CSV is empty: {path}"
        )

    missing = required - set(rows[0].keys())
    if missing:
        raise ValueError(
            f"Missing columns in {path}: "
            f"{', '.join(sorted(missing))}"
        )


def load_product_master(
    path: Path,
) -> dict[str, dict[str, str]]:
    rows = load_csv(path)

    require_columns(
        rows,
        path,
        {
            "canonical_product_code",
            "product_name",
            "product_family",
            "instrument",
            "weekly",
            "status",
        },
    )

    out: dict[str, dict[str, str]] = {}

    for row in rows:
        code = normalize_header_code(
            row["canonical_product_code"]
        )

        if not code:
            raise ValueError(
                f"Blank canonical product code in {path}"
            )

        if code in out:
            raise ValueError(
                "Duplicate canonical product code "
                f"in {path}: {code}"
            )

        out[code] = row

    return out


def load_alias_master(
    path: Path,
) -> dict[tuple[str, str], dict[str, str]]:
    """Load PG64 aliases.

    Key:
        (PG64 display code, PG64 week number)

    Direct products normally use week number "".
    Weekly products use Week1..Week5 semantics from the PDF header.
    """

    rows = load_csv(path)

    require_columns(
        rows,
        path,
        {
            "pg64_display_code",
            "pg64_week_number",
            "canonical_product_code",
            "product_family",
            "weekly_day",
            "mapping_basis",
        },
    )

    out: dict[tuple[str, str], dict[str, str]] = {}

    for row in rows:
        display = normalize_header_code(
            row["pg64_display_code"]
        )
        week = norm(row["pg64_week_number"])

        if not display:
            raise ValueError(
                f"Blank PG64 display code in {path}"
            )

        key = (display, week)

        if key in out:
            raise ValueError(
                "Duplicate PG64 alias rule in "
                f"{path}: "
                f"display_code={display!r}, "
                f"week={week!r}"
            )

        out[key] = row

    return out


class ProductResolver:
    """Resolve PDF product headers through the masters.

    Resolution rules are deliberately fail-closed.

    1. If the PDF explicitly contains WEEK1..WEEK5, use the exact
       weekly alias (display_code, week).
    2. If the PDF does not contain WEEK1..WEEK5, use the exact direct
       alias (display_code, "").
    3. If the alias master represents a non-weekly canonical product
       using a legacy numeric pg64_week_number, that master-declared
       direct mapping may be used. This is NOT inference from the
       display-code suffix.
    4. Never infer a week number from the product code itself.
    5. Never fall back from a requested weekly alias to a direct alias.
    6. Once an alias resolves to a canonical product, the canonical
       product must exist in the product master.
    7. CURRENT_OFFICIAL is a valid current product-master status.
    """

    def __init__(
        self,
        product_master_path: Path,
        alias_master_path: Path,
    ):
        self.product_master_path = product_master_path
        self.alias_master_path = alias_master_path

        self.products = load_product_master(
            product_master_path
        )
        self.aliases = load_alias_master(
            alias_master_path
        )

        self.unknown_headers: list[dict[str, str]] = []

    @staticmethod
    def _week_from_header(header: str) -> str:
        m = re.search(
            r"\bWEEK\s*([1-5])\b",
            header,
            re.I,
        )
        return m.group(1) if m else ""

    def _find_master_declared_direct_alias(
        self,
        display: str,
    ) -> dict[str, str] | None:
        """Find a direct mapping explicitly represented by the masters.

        Some existing PG64 alias-master rows for OG/OG1..OG5 carry a
        numeric pg64_week_number even though the source header itself
        contains no WEEKn token. We do not convert that number from the
        display code. Instead, we accept the row only when the alias
        itself points to the same canonical code and that canonical
        product is marked non-weekly in the product master.

        This keeps the resolver master-driven and prevents GMW/GWT/etc.
        from silently falling back to a direct product.
        """

        candidates = []

        for (alias_display, _week), alias in self.aliases.items():
            if alias_display != display:
                continue

            canonical = normalize_header_code(
                alias.get("canonical_product_code", "")
            )

            if not canonical or canonical != display:
                continue

            product = self.products.get(canonical)
            if product is None:
                continue

            weekly = norm(
                product.get("weekly")
            ).upper()

            if weekly in {"TRUE", "YES", "Y", "1"}:
                continue

            candidates.append(alias)

        if len(candidates) == 1:
            return candidates[0]

        # Ambiguous master data is fail-closed.
        return None

    def _unknown_result(
        self,
        *,
        display: str,
        header: str,
        week: str,
        page: int,
        top: float,
        reason: str,
        canonical: str | None = None,
        alias: dict[str, str] | None = None,
    ) -> dict[str, object]:
        unknown = {
            "page": page,
            "top": round(top, 3),
            "raw_product_code": display,
            "raw_product_header": header,
            "pg64_week_number": week,
            "reason": reason,
        }

        if canonical:
            unknown["canonical_product_code"] = canonical

        self.unknown_headers.append(unknown)

        return {
            "status": "UNKNOWN_PRODUCT",
            "raw_product_code": display,
            "raw_product_header": header,
            "pg64_week_number": week,
            "canonical_product_code": canonical,
            "product_family": (
                alias.get("product_family")
                if alias
                else None
            ),
            "weekly_day": (
                alias.get("weekly_day")
                if alias
                else None
            ),
            "mapping_basis": (
                alias.get("mapping_basis")
                if alias
                else None
            ),
        }

    def resolve(
        self,
        raw_code: str,
        raw_header: str,
        *,
        page: int,
        top: float,
    ) -> dict[str, object]:
        display = normalize_header_code(raw_code)
        header = norm(raw_header)

        # ----------------------------------------------------------
        # Resolve the week ONLY from explicit PDF header evidence.
        # ----------------------------------------------------------
        week = self._week_from_header(header)

        # ----------------------------------------------------------
        # Alias lookup.
        #
        # Weekly PDF header:
        #     GMW ... Week1
        #     -> (GMW, "1")
        #
        # Direct PDF header:
        #     OG4 PUT GOLD OPTIONS
        #     -> first try (OG4, "")
        #
        # No OG4 -> week 4 inference is performed.
        # ----------------------------------------------------------
        alias_key = (display, week)
        alias = self.aliases.get(alias_key)

        if alias is None and not week:
            # Compatibility with the current alias-master representation:
            # accept only a master-declared direct mapping, never a
            # display-code-derived week.
            alias = self._find_master_declared_direct_alias(
                display
            )

        if alias is None:
            return self._unknown_result(
                display=display,
                header=header,
                week=week,
                page=page,
                top=top,
                reason="NO_PG64_ALIAS_RULE",
            )

        canonical = normalize_header_code(
            alias["canonical_product_code"]
        )

        # ----------------------------------------------------------
        # Canonical product lookup.
        # ----------------------------------------------------------
        product = self.products.get(canonical)

        if product is None:
            return self._unknown_result(
                display=display,
                header=header,
                week=week,
                page=page,
                top=top,
                reason=(
                    "ALIAS_POINTS_TO_UNKNOWN_"
                    "CANONICAL_PRODUCT"
                ),
                canonical=canonical,
                alias=alias,
            )

        # ----------------------------------------------------------
        # Product master status.
        #
        # CURRENT_OFFICIAL is explicitly valid.
        # ----------------------------------------------------------
        product_status = norm(
            product.get("status")
        ).upper()

        if (
            product_status
            and product_status
            not in CURRENT_PRODUCT_STATUSES
        ):
            return {
                "status": "PRODUCT_MASTER_NONCURRENT",
                "raw_product_code": display,
                "raw_product_header": header,
                "pg64_week_number": week,
                "canonical_product_code": canonical,
                "product_name": (
                    product.get("product_name")
                    or None
                ),
                "product_family": (
                    product.get("product_family")
                    or None
                ),
                "instrument": (
                    product.get("instrument")
                    or None
                ),
                "weekly": (
                    product.get("weekly")
                    or None
                ),
                "weekly_day": (
                    alias.get("weekly_day")
                    or None
                ),
                "mapping_basis": (
                    alias.get("mapping_basis")
                    or None
                ),
                "product_master_status": (
                    product_status
                ),
            }

        # ----------------------------------------------------------
        # Fully resolved.
        #
        # CALL/PUT and expiry are intentionally NOT supplied here.
        # They remain source-observed PDF facts.
        # ----------------------------------------------------------
        return {
            "status": "KNOWN_PRODUCT",
            "raw_product_code": display,
            "raw_product_header": header,
            "pg64_week_number": week,
            "canonical_product_code": canonical,
            "product_name": (
                product.get("product_name")
                or None
            ),
            "product_family": (
                product.get("product_family")
                or None
            ),
            "instrument": (
                product.get("instrument")
                or None
            ),
            "weekly": (
                product.get("weekly")
                or None
            ),
            "weekly_day": (
                alias.get("weekly_day")
                or None
            ),
            "mapping_basis": (
                alias.get("mapping_basis")
                or None
            ),
            "product_master_status": (
                product_status
            ),
        }


def parse_bulletin_metadata(
    alltext: str,
    first_pages_text: str,
):
    m = re.search(
        r"PG64\s+BULLETIN\s*#\s*(\d+)\s*@?.?"
        r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+"
        r"([A-Z][a-z]{2})\s+"
        r"(\d{1,2}),\s"
        r"(\d{4})",
        alltext,
        re.I | re.S,
    )

    if not m:
        raise ValueError(
            "PG64 bulletin/date metadata not found"
        )

    trade_date = datetime.strptime(
        (
            f"{m.group(2)} "
            f"{m.group(3)} "
            f"{m.group(4)}"
        ),
        "%b %d %Y",
    ).date().isoformat()

    statuses = {
        x.upper()
        for x in re.findall(
            r"\b(FINAL|PRELIMINARY)\b",
            first_pages_text,
            re.I,
        )
    }

    invalid_statuses = statuses - STATUS_TOKENS

    if invalid_statuses:
        raise ValueError(
            "Unexpected bulletin status tokens: "
            f"{sorted(invalid_statuses)}"
        )

    return (
        int(m.group(1)),
        trade_date,
        sorted(statuses),
    )


def audit(
    path: Path,
    product_master_path: Path = DEFAULT_PRODUCT_MASTER,
    alias_master_path: Path = DEFAULT_ALIAS_MASTER,
):
    digest = sha(path)

    resolver = ProductResolver(
        product_master_path=product_master_path,
        alias_master_path=alias_master_path,
    )

    pages = []
    main_pages = []
    candidate_rows = []
    totals = []
    unresolved = []
    product_headers = []

    with pdfplumber.open(path) as pdf:
        all_page_texts = [
            p.extract_text() or ""
            for p in pdf.pages
        ]

        alltext = "\n".join(
            all_page_texts
        )

        first_pages_text = "\n".join(
            all_page_texts[:3]
        )

        (
            bulletin_number,
            trade_date,
            statuses,
        ) = parse_bulletin_metadata(
            alltext,
            first_pages_text,
        )

        for pno, page in enumerate(
            pdf.pages,
            1,
        ):
            page_text = page.extract_text() or ""
            u = page_text.upper()

            has_table_header = (
                "VOLUME" in u
                and "INTEREST" in u
                and "DELTA" in u
                and "HIGH/LOW" in u
                and "SETT.PRICE" in u
            )

            page_info = {
                "page": pno,
                "main_chain_header": (
                    has_table_header
                ),
                "gold_mentions": len(
                    re.findall(
                        r"\bGOLD\b",
                        u,
                    )
                ),
                "eoo_blocks_section": (
                    "OPTIONS EOO" in u
                    and "BLOCKS" in u
                ),
            }

            if has_table_header:
                main_pages.append(pno)
                cur_product = None
                cur_type = None
                cur_expiry = None

                for g in lines(page):
                    ws = g["words"]

                    text = norm(
                        " ".join(
                            w["text"]
                            for w in ws
                        )
                    )

                    up = text.upper()

                    if not text:
                        continue

                    if (
                        "OPEN OUTCRY VOLUME"
                        in up
                        or up == "OPEN INTEREST"
                    ):
                        continue

                    # --------------------------------------------------
                    # PRODUCT HEADER
                    # --------------------------------------------------
                    #
                    # No hard-coded OG1-OG5 list.
                    #
                    # Any GOLD + OPTION(S) header is treated as source
                    # evidence and resolved through the product masters.
                    #
                    pm = PRODUCT_HEADER.match(up)

                    if pm:
                        raw_code = (
                            pm.group("code")
                            .upper()
                        )

                        resolution = (
                            resolver.resolve(
                                raw_code,
                                text,
                                page=pno,
                                top=g["top"],
                            )
                        )

                        product_headers.append(
                            {
                                "page": pno,
                                "top": round(
                                    g["top"],
                                    3,
                                ),
                                "raw_product_code": (
                                    raw_code
                                ),
                                "raw_product_header": (
                                    text
                                ),
                                "resolution": (
                                    resolution
                                ),
                            }
                        )

                        cur_product = resolution

                        # CALL/PUT comes ONLY from the
                        # source product heading.
                        cur_type = (
                            "CALL"
                            if re.search(
                                r"\bCALL\b",
                                up,
                            )
                            else (
                                "PUT"
                                if re.search(
                                    r"\bPUT\b",
                                    up,
                                )
                                else "UNSPECIFIED"
                            )
                        )

                        cur_expiry = None
                        continue

                    # --------------------------------------------------
                    # CONTRACT MONTH
                    # --------------------------------------------------
                    #
                    # Contract month is source-observed.
                    # Product master never supplies it.
                    #
                    em = re.fullmatch(
                        MONTH,
                        up,
                    )

                    if em:
                        cur_expiry = up
                        continue

                    # --------------------------------------------------
                    # TOTAL
                    # --------------------------------------------------
                    if up.startswith("TOTAL"):
                        totals.append(
                            {
                                "page": pno,
                                "product": (
                                    cur_product.get(
                                        "canonical_product_code"
                                    )
                                    if cur_product
                                    else None
                                ),
                                "raw_product_code": (
                                    cur_product.get(
                                        "raw_product_code"
                                    )
                                    if cur_product
                                    else None
                                ),
                                "option_type": cur_type,
                                "contract_month": (
                                    cur_expiry
                                ),
                                "raw_line": text,
                                "product_resolution_status": (
                                    cur_product.get(
                                        "status"
                                    )
                                    if cur_product
                                    else "NO_PRODUCT_STATE"
                                ),
                            }
                        )
                        continue

                    # --------------------------------------------------
                    # STRIKE CANDIDATE
                    # --------------------------------------------------
                    if (
                        ws
                        and re.fullmatch(
                            STRIKE,
                            ws[0]["text"],
                        )
                        and float(
                            ws[0]["text"].replace(
                                ",",
                                "",
                            )
                        ) >= 1000
                    ):
                        row = {
                            "page": pno,
                            "top": round(
                                g["top"],
                                3,
                            ),
                            "product": (
                                cur_product.get(
                                    "canonical_product_code"
                                )
                                if cur_product
                                else None
                            ),
                            "raw_product_code": (
                                cur_product.get(
                                    "raw_product_code"
                                )
                                if cur_product
                                else None
                            ),
                            "product_resolution_status": (
                                cur_product.get(
                                    "status"
                                )
                                if cur_product
                                else "NO_PRODUCT_STATE"
                            ),
                            "option_type": cur_type,
                            "contract_month": (
                                cur_expiry
                            ),
                            "strike_raw": (
                                ws[0]["text"]
                            ),
                            "raw_line": text,
                            "token_count": len(ws),
                        }

                        candidate_rows.append(
                            row
                        )

                        if (
                            not cur_product
                            or cur_product.get(
                                "status"
                            ) != "KNOWN_PRODUCT"
                            or not cur_expiry
                            or not cur_type
                        ):
                            unresolved.append(
                                {
                                    "page": pno,
                                    "top": round(
                                        g["top"],
                                        3,
                                    ),
                                    "reason": (
                                        "unresolved "
                                        "product/type/"
                                        "expiry state"
                                    ),
                                    "raw_line": text,
                                    "product_resolution_status": (
                                        cur_product.get(
                                            "status"
                                        )
                                        if cur_product
                                        else "NO_PRODUCT_STATE"
                                    ),
                                }
                            )

            pages.append(page_info)

    unknown_count = len(
        resolver.unknown_headers
    )

    noncurrent_headers = [
        x
        for x in product_headers
        if x["resolution"].get("status")
        == "PRODUCT_MASTER_NONCURRENT"
    ]

    if unknown_count:
        production_status = (
            "BLOCKED_UNKNOWN_PRODUCT"
        )
    elif noncurrent_headers:
        production_status = (
            "BLOCKED_NONCURRENT_PRODUCT_MASTER"
        )
    else:
        production_status = (
            "BLOCKED_DIAGNOSTIC_ONLY"
        )

    return {
        "diagnostic_schema": (
            DIAGNOSTIC_SCHEMA
        ),
        "parser_version": VERSION,
        "dataset": "PG64_GOLD_OPTIONS",
        "trade_date": trade_date,
        "bulletin": {
            "number": bulletin_number,
            "status_candidates": statuses,
        },
        "source": {
            "file": path.name,
            "sha256": digest,
            "ingested_at": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),
        },
        "product_master": {
            "product_master_file": (
                str(product_master_path)
            ),
            "pg64_alias_master_file": (
                str(alias_master_path)
            ),
            "product_master_sha256": (
                sha(product_master_path)
            ),
            "pg64_alias_master_sha256": (
                sha(alias_master_path)
            ),
            "canonical_product_count": (
                len(resolver.products)
            ),
            "pg64_alias_rule_count": (
                len(resolver.aliases)
            ),
        },
        "page_count": len(pages),
        "pages_with_main_chain_header": (
            main_pages
        ),
        "product_headers_seen": (
            len(product_headers)
        ),
        "known_product_headers": sum(
            1
            for x in product_headers
            if x["resolution"].get(
                "status"
            )
            == "KNOWN_PRODUCT"
        ),
        "unknown_product_headers": (
            unknown_count
        ),
        "noncurrent_product_headers": (
            len(noncurrent_headers)
        ),
        "candidate_strike_rows": (
            len(candidate_rows)
        ),
        "candidate_total_rows": (
            len(totals)
        ),
        "unresolved_state_rows": (
            len(unresolved)
        ),
        "known_unhandled_risks": [
            (
                "Character/content-stream reconstruction "
                "for overlapping H/L cells is not implemented."
            ),
            (
                "No production cell extraction or mandatory "
                "expiry TOTAL reconciliation is performed."
            ),
            (
                "Rows without explicit CALL/PUT are retained "
                "as UNSPECIFIED; delta is never used to infer type."
            ),
            (
                "Candidate counts are diagnostic only and must "
                "not be treated as complete parsed data."
            ),
            (
                "Product master normalization does not supply "
                "missing PDF facts such as option type or expiry."
            ),
        ],
        "production_master_status": (
            production_status
        ),
        "pages": pages,
        "product_headers": product_headers,
        "unknown_product_examples": (
            resolver.unknown_headers[:100]
        ),
        "totals_candidates": totals,
        "unresolved_examples": (
            unresolved[:100]
        ),
        "candidate_examples": (
            candidate_rows[:30]
        ),
    }


def main():
    ap = argparse.ArgumentParser()

    ap.add_argument(
        "pdf",
        type=Path,
    )

    ap.add_argument(
        "--product-master",
        type=Path,
        default=DEFAULT_PRODUCT_MASTER,
        help=(
            "Canonical product master CSV "
            f"(default: {DEFAULT_PRODUCT_MASTER})"
        ),
    )

    ap.add_argument(
        "--alias-master",
        type=Path,
        default=DEFAULT_ALIAS_MASTER,
        help=(
            "PG64 alias master CSV "
            f"(default: {DEFAULT_ALIAS_MASTER})"
        ),
    )

    ap.add_argument(
        "--audit-dir",
        type=Path,
        default=Path(
            "data/audit/pg64"
        ),
    )

    a = ap.parse_args()

    try:
        d = audit(
            a.pdf,
            product_master_path=(
                a.product_master
            ),
            alias_master_path=(
                a.alias_master
            ),
        )
    except Exception as e:
        print(
            f"AUDIT FAILED: {e}",
            file=sys.stderr,
        )
        raise SystemExit(2)

    statuses = d["bulletin"][
        "status_candidates"
    ]

    status = (
        statuses[0]
        if len(statuses) == 1
        else "AMBIGUOUS"
    )

    out = (
        a.audit_dir
        / d["trade_date"]
        / (
            f"{d['trade_date']}_"
            f"{status}_AUDIT.json"
        )
    )

    out.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    out.write_text(
        json.dumps(
            d,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "PG64 AUDIT ONLY: "
        f"{out} "
        f"pages={len(d['pages_with_main_chain_header'])} "
        f"product_headers={d['product_headers_seen']} "
        f"known_products={d['known_product_headers']} "
        f"unknown_products={d['unknown_product_headers']} "
        f"strike_candidates={d['candidate_strike_rows']} "
        f"totals={d['candidate_total_rows']} "
        f"unresolved={d['unresolved_state_rows']}"
    )

    print(
        "Production gate: "
        f"{d['production_master_status']}"
    )

    print(
        "No production MASTER written "
        "(intentional fail-closed gate)."
    )


if __name__ == "__main__":
    main()
