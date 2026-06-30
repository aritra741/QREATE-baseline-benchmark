from __future__ import annotations

import csv
import gzip
import html
import json
import random
import re
import shutil
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "source_data" / "SEC"
DATA_ROOT = ROOT / "Data" / "SEC"
QUERY_ROOT = ROOT / "Query" / "SEC"

USER_AGENT = "UDA-Bench research aritra@example.com"
SEED = 42
START_YEAR = 2022
END_YEAR = 2025
TARGET_FORMS = {"10-K", "10-Q"}
TARGET_TICKERS = [
    "AAPL",
    "MSFT",
    "AMZN",
    "GOOGL",
    "JPM",
    "XOM",
    "JNJ",
    "WMT",
    "NVDA",
    "TSLA",
]

METRIC_SPECS = {
    "revenue_usd": {
        "concepts": [
            ("us-gaap", "Revenues"),
            ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
            ("us-gaap", "SalesRevenueNet"),
        ],
        "unit": "USD",
        "kind": "duration",
    },
    "assets_usd": {"concepts": [("us-gaap", "Assets")], "unit": "USD", "kind": "instant"},
    "liabilities_usd": {"concepts": [("us-gaap", "Liabilities")], "unit": "USD", "kind": "instant"},
    "net_income_usd": {
        "concepts": [("us-gaap", "NetIncomeLoss"), ("us-gaap", "ProfitLoss")],
        "unit": "USD",
        "kind": "duration",
    },
    "operating_cash_flow_usd": {
        "concepts": [("us-gaap", "NetCashProvidedByUsedInOperatingActivities")],
        "unit": "USD",
        "kind": "duration",
    },
    "investing_cash_flow_usd": {
        "concepts": [("us-gaap", "NetCashProvidedByUsedInInvestingActivities")],
        "unit": "USD",
        "kind": "duration",
    },
    "financing_cash_flow_usd": {
        "concepts": [("us-gaap", "NetCashProvidedByUsedInFinancingActivities")],
        "unit": "USD",
        "kind": "duration",
    },
    "shares_outstanding": {
        "concepts": [("dei", "EntityCommonStockSharesOutstanding")],
        "unit": "shares",
        "kind": "instant",
    },
    "market_cap_usd": {"concepts": [], "unit": "USD", "kind": "derived"},
}


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_response_text(response) -> str:
    payload = response.read()
    if response.headers.get("Content-Encoding", "").lower() == "gzip" or payload[:2] == b"\x1f\x8b":
        payload = gzip.decompress(payload)
    return payload.decode("utf-8", errors="replace")


def fetch_json(url: str, dest: Path) -> dict:
    ensure_dir(dest.parent)
    if dest.exists():
        return json.loads(dest.read_text(encoding="utf-8"))
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"})
    with urlopen(request) as response:
        payload = read_response_text(response)
    dest.write_text(payload, encoding="utf-8")
    return json.loads(payload)


def fetch_text(url: str, dest: Path) -> str:
    ensure_dir(dest.parent)
    if dest.exists():
        return dest.read_text(encoding="utf-8", errors="replace")
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"})
    with urlopen(request) as response:
        payload = read_response_text(response)
    dest.write_text(payload, encoding="utf-8")
    return payload


class FilingHTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style"}:
            self.skip_depth += 1
        if self.skip_depth == 0 and tag in {"p", "div", "br", "tr", "li", "table", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self.skip_depth > 0:
            self.skip_depth -= 1
        if self.skip_depth == 0 and tag in {"p", "div", "br", "tr", "li", "table"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip_depth == 0:
            cleaned = data.strip()
            if cleaned:
                self.parts.append(cleaned)
                self.parts.append(" ")

    def get_text(self) -> str:
        text = html.unescape("".join(self.parts))
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def html_to_text(content: str) -> str:
    parser = FilingHTMLStripper()
    parser.feed(content)
    text = parser.get_text()
    if text:
        return text
    fallback = re.sub(r"<[^>]+>", " ", content)
    fallback = html.unescape(fallback)
    fallback = re.sub(r"\s+", " ", fallback)
    return fallback.strip()


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value[:10])


def duration_days(start: str | None, end: str | None) -> int | None:
    if not start or not end:
        return None
    try:
        return (date.fromisoformat(end) - date.fromisoformat(start)).days
    except ValueError:
        return None


def to_decimal(value) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def serialize_decimal(value: Decimal | None) -> str:
    if value is None:
        return ""
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def sql_quote(value: str) -> str:
    return value.replace("'", "''")


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def write_json(path: Path, payload) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_archive_url(cik: str, accession_number: str, primary_document: str) -> str:
    accession_nodash = accession_number.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_nodash}/{primary_document}"


def fetch_company_universe() -> dict[str, dict]:
    payload = fetch_json("https://www.sec.gov/files/company_tickers.json", SOURCE_ROOT / "api_cache" / "company_tickers.json")
    out = {}
    for row in payload.values():
        out[row["ticker"].upper()] = {
            "ticker": row["ticker"].upper(),
            "cik": f"{int(row['cik_str']):010d}",
            "title": row["title"],
        }
    return out


def load_submission_bundle(cik: str) -> tuple[dict, list[dict]]:
    base = fetch_json(
        f"https://data.sec.gov/submissions/CIK{cik}.json",
        SOURCE_ROOT / "api_cache" / "submissions" / f"CIK{cik}.json",
    )
    bundles = [base.get("filings", {}).get("recent", {})]
    for meta in base.get("filings", {}).get("files", []):
        extra = fetch_json(
            f"https://data.sec.gov/submissions/{meta['name']}",
            SOURCE_ROOT / "api_cache" / "submissions" / meta["name"],
        )
        bundles.append(extra)
    return base, bundles


def rows_from_submission_arrays(block: dict) -> list[dict]:
    keys = [
        "accessionNumber",
        "filingDate",
        "reportDate",
        "acceptanceDateTime",
        "form",
        "primaryDocument",
        "primaryDocDescription",
        "isXBRL",
        "isInlineXBRL",
    ]
    rows = []
    size = len(block.get("accessionNumber", []))
    for idx in range(size):
        row = {}
        for key in keys:
            values = block.get(key, [])
            row[key] = values[idx] if idx < len(values) else None
        rows.append(row)
    return rows


def select_filings_for_company(company_meta: dict, submission_payload: dict, bundles: list[dict]) -> list[dict]:
    selected = {}
    for bundle in bundles:
        for row in rows_from_submission_arrays(bundle):
            accession = row.get("accessionNumber")
            form = row.get("form")
            filing_date = row.get("filingDate")
            primary_document = row.get("primaryDocument")
            if not accession or form not in TARGET_FORMS or not filing_date or not primary_document:
                continue
            year = parse_date(filing_date).year
            if year < START_YEAR or year > END_YEAR:
                continue
            selected[accession] = {
                "company_id": company_meta["cik"],
                "cik": company_meta["cik"],
                "ticker": company_meta["ticker"],
                "company_name": submission_payload.get("name") or company_meta["title"],
                "accession_number": accession,
                "accession_nodash": accession.replace("-", ""),
                "form_type": form,
                "filing_date": filing_date,
                "report_date": row.get("reportDate") or "",
                "acceptance_datetime": row.get("acceptanceDateTime") or "",
                "primary_document": primary_document,
                "primary_doc_description": row.get("primaryDocDescription") or "",
                "source_url": build_archive_url(company_meta["cik"], accession, primary_document),
                "is_xbrl": int(row.get("isXBRL") or 0),
                "is_inline_xbrl": int(row.get("isInlineXBRL") or 0),
                "sic": submission_payload.get("sic") or "",
                "sic_description": submission_payload.get("sicDescription") or "",
                "state_of_incorporation": submission_payload.get("stateOfIncorporation") or "",
                "fiscal_year_end": submission_payload.get("fiscalYearEnd") or "",
            }
    return sorted(selected.values(), key=lambda item: (item["filing_date"], item["accession_number"]))


def concept_id(taxonomy: str, concept_name: str) -> str:
    return f"{taxonomy}:{concept_name}"


def infer_quarter(fp: str | None) -> str:
    return {"Q1": "1", "Q2": "2", "Q3": "3", "FY": "4"}.get((fp or "").upper(), "")


@dataclass
class FactRow:
    fact_id: str
    company_id: str
    filing_id: str
    accession_number: str
    concept_id: str
    concept_name: str
    taxonomy: str
    value: Decimal
    unit_id: str
    period_id: str
    period_start: str
    period_end: str
    period_type: str
    fiscal_year: str
    fiscal_period: str
    fiscal_quarter: str
    form_type: str
    filed_date: str
    frame: str
    source_api_url: str


def extract_companyfacts(company_id: str, selected_accessions: set[str]) -> tuple[list[FactRow], dict[str, dict], Counter, Counter]:
    payload = fetch_json(
        f"https://data.sec.gov/api/xbrl/companyfacts/CIK{company_id}.json",
        SOURCE_ROOT / "api_cache" / "companyfacts" / f"CIK{company_id}.json",
    )
    facts_out = []
    concepts = {}
    period_counter: Counter = Counter()
    filing_fp_counter: Counter = Counter()
    fact_index = 1
    for taxonomy, concepts_block in payload.get("facts", {}).items():
        for concept_name, concept_payload in concepts_block.items():
            cid = concept_id(taxonomy, concept_name)
            concepts[cid] = {
                "concept_id": cid,
                "taxonomy": taxonomy,
                "concept_name": concept_name,
                "label": concept_payload.get("label", ""),
                "description": concept_payload.get("description", ""),
            }
            for unit_id, entries in concept_payload.get("units", {}).items():
                for entry in entries:
                    accession = entry.get("accn")
                    if accession not in selected_accessions:
                        continue
                    value = to_decimal(entry.get("val"))
                    if value is None:
                        continue
                    start = entry.get("start") or ""
                    end = entry.get("end") or ""
                    fy = str(entry.get("fy") or "")
                    fp = str(entry.get("fp") or "")
                    form_type = str(entry.get("form") or "")
                    filed_date = str(entry.get("filed") or "")
                    frame = str(entry.get("frame") or "")
                    kind = "duration" if start else "instant"
                    period_counter[(start, end, fy, fp, frame, kind)] += 1
                    if fp:
                        filing_fp_counter[(accession, fy, fp)] += 1
                    facts_out.append(
                        FactRow(
                            fact_id=f"fact_{company_id}_{fact_index:06d}",
                            company_id=company_id,
                            filing_id=accession.replace("-", ""),
                            accession_number=accession,
                            concept_id=cid,
                            concept_name=concept_name,
                            taxonomy=taxonomy,
                            value=value,
                            unit_id=unit_id,
                            period_id="",
                            period_start=start,
                            period_end=end,
                            period_type=kind,
                            fiscal_year=fy,
                            fiscal_period=fp,
                            fiscal_quarter=infer_quarter(fp),
                            form_type=form_type,
                            filed_date=filed_date,
                            frame=frame,
                            source_api_url=f"https://data.sec.gov/api/xbrl/companyfacts/CIK{company_id}.json",
                        )
                    )
                    fact_index += 1
    deduped = []
    seen = set()
    for fact in facts_out:
        key = (
            fact.company_id, fact.filing_id, fact.concept_id, fact.unit_id,
            fact.period_start, fact.period_end, fact.value, fact.frame,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(fact)
    return deduped, concepts, period_counter, filing_fp_counter


def expected_duration_days(fp: str | None) -> int:
    return {"Q1": 95, "Q2": 185, "Q3": 275, "FY": 365}.get((fp or "").upper(), 365)


def choose_metric_fact(candidates: list[FactRow], metric_name: str, filing_row: dict) -> FactRow | None:
    if not candidates:
        return None
    filing_end = filing_row.get("report_date") or filing_row.get("filing_date") or ""
    filing_fp = filing_row.get("fiscal_period") or ""
    target_days = expected_duration_days(filing_fp)
    spec = METRIC_SPECS[metric_name]

    def score(fact: FactRow) -> tuple:
        same_end = int(bool(filing_end and fact.period_end == filing_end))
        same_fp = int(bool(filing_fp and fact.fiscal_period == filing_fp))
        same_form = int(fact.form_type == filing_row.get("form_type"))
        days = duration_days(fact.period_start or None, fact.period_end or None)
        if spec["kind"] == "duration":
            duration_score = -abs((days or target_days) - target_days)
        else:
            duration_score = 0 if fact.period_type == "instant" else -9999
        return (same_end, same_fp, same_form, duration_score, fact.period_end, fact.fact_id)

    return sorted(candidates, key=score, reverse=True)[0]


def build_metric_row(filing_row: dict, facts_by_filing: dict[str, list[FactRow]]) -> dict:
    row = {
        "filing_id": filing_row["filing_id"],
        "company_id": filing_row["company_id"],
        "ticker": filing_row["ticker"],
        "company_name": filing_row["company_name"],
        "form_type": filing_row["form_type"],
        "filing_date": filing_row["filing_date"],
        "report_date": filing_row["report_date"],
        "fiscal_year": filing_row["fiscal_year"],
        "fiscal_period": filing_row["fiscal_period"],
        "fiscal_quarter": filing_row["fiscal_quarter"],
        "sic": filing_row["sic"],
        "sic_description": filing_row["sic_description"],
        "state_of_incorporation": filing_row["state_of_incorporation"],
    }
    facts = facts_by_filing.get(filing_row["filing_id"], [])
    for metric_name, spec in METRIC_SPECS.items():
        row[metric_name] = ""
        row[f"{metric_name}_concept_id"] = ""
        row[f"{metric_name}_unit_id"] = spec["unit"]
        row[f"{metric_name}_period_start"] = ""
        row[f"{metric_name}_period_end"] = ""
        if metric_name == "market_cap_usd":
            continue
        candidates = [
            fact for fact in facts
            if (fact.taxonomy, fact.concept_name) in spec["concepts"]
            and fact.unit_id.upper() == spec["unit"].upper()
        ]
        chosen = choose_metric_fact(candidates, metric_name, filing_row)
        if chosen is None:
            continue
        row[metric_name] = serialize_decimal(chosen.value)
        row[f"{metric_name}_concept_id"] = chosen.concept_id
        row[f"{metric_name}_period_start"] = chosen.period_start
        row[f"{metric_name}_period_end"] = chosen.period_end
    return row


def format_doc_header(filing_row: dict) -> str:
    return (
        f"Document ID: {filing_row['filing_id']}\n"
        f"Company ID: {filing_row['company_id']}\n"
        f"Ticker: {filing_row['ticker']}\n"
        f"Company Name: {filing_row['company_name']}\n"
        f"Form Type: {filing_row['form_type']}\n"
        f"Filing Date: {filing_row['filing_date']}\n"
        f"Report Date: {filing_row['report_date']}\n"
        f"Source URL: {filing_row['source_url']}\n\n"
    )


def emit_corpus_docs(filing_rows: list[dict], texts_by_filing: dict[str, str]) -> list[dict]:
    manifest = []
    for folder in ("filing", "filing_metrics", "company"):
        ensure_dir(SOURCE_ROOT / folder)
    for filing in filing_rows:
        content = format_doc_header(filing) + texts_by_filing[filing["filing_id"]]
        for folder in ("filing", "filing_metrics", "company"):
            (SOURCE_ROOT / folder / f"{filing['filing_id']}.txt").write_text(content, encoding="utf-8")
        manifest.append(
            {
                "document_id": filing["filing_id"],
                "company_id": filing["company_id"],
                "ticker": filing["ticker"],
                "company_name": filing["company_name"],
                "filing_id": filing["filing_id"],
                "accession_number": filing["accession_number"],
                "filing_date": filing["filing_date"],
                "report_date": filing["report_date"],
                "form_type": filing["form_type"],
                "source_url": filing["source_url"],
                "raw_html_path": str((SOURCE_ROOT / "raw_html" / f"{filing['filing_id']}.html").relative_to(ROOT)),
                "canonical_text_path": str((SOURCE_ROOT / "filing" / f"{filing['filing_id']}.txt").relative_to(ROOT)),
                "corpus_views": "filing|filing_metrics|company",
            }
        )
    return manifest


def build_queries(filing_metrics_rows: list[dict], company_rows: list[dict], filing_rows: list[dict]) -> dict[str, list[str]]:
    metrics = [
        "revenue_usd", "assets_usd", "liabilities_usd", "net_income_usd",
        "operating_cash_flow_usd", "investing_cash_flow_usd", "financing_cash_flow_usd",
        "shares_outstanding",
    ]
    agg_only_groups = ["company_name", "ticker", "form_type", "fiscal_period", "sic_description", "state_of_incorporation"]
    industries = sorted({row["sic_description"] for row in company_rows if row["sic_description"]})[:6]
    states = sorted({row["state_of_incorporation"] for row in company_rows if row["state_of_incorporation"]})[:6]
    forms = sorted({row["form_type"] for row in filing_rows if row["form_type"]})
    periods = sorted({row["fiscal_period"] for row in filing_metrics_rows if row["fiscal_period"]})
    years = sorted({row["fiscal_year"] for row in filing_metrics_rows if row["fiscal_year"]})
    queries = defaultdict(list)

    for group in agg_only_groups:
        queries["agg_only"].append(f"SELECT {group}, COUNT(*) AS count_filings FROM filing_metrics GROUP BY {group};")
        for metric in metrics:
            for func in ["SUM", "AVG", "MIN", "MAX", "COUNT"]:
                target = "*" if func == "COUNT" else metric
                alias = f"{func.lower()}_{metric if target != '*' else 'all'}"
                queries["agg_only"].append(
                    f"SELECT {group}, {func}({target}) AS {alias} FROM filing_metrics GROUP BY {group};"
                )

    filters = []
    filters.extend([f"form_type = '{form}'" for form in forms])
    filters.extend([f"fiscal_period = '{period}'" for period in periods])
    filters.extend([f"sic_description = '{sql_quote(industry)}'" for industry in industries])
    filters.extend([f"state_of_incorporation = '{state}'" for state in states])
    filters.extend([
        "revenue_usd IS NOT NULL",
        "revenue_usd > 0",
        "net_income_usd > 0",
        "net_income_usd < 0",
        "assets_usd > liabilities_usd",
        "shares_outstanding IS NOT NULL",
    ])
    for group in ["company_name", "ticker", "sic_description", "fiscal_period"]:
        for metric in metrics:
            for func in ["SUM", "AVG", "MIN", "MAX"]:
                for predicate in filters:
                    queries["agg_filter"].append(
                        f"SELECT {group}, {func}({metric}) AS {func.lower()}_{metric} "
                        f"FROM filing_metrics WHERE {predicate} GROUP BY {group};"
                    )

    for group in ["company.ticker", "company.sic_description", "company.state_of_incorporation", "filing.form_type"]:
        for metric in metrics:
            for func in ["SUM", "AVG", "MIN", "MAX"]:
                queries["agg_join"].append(
                    f"SELECT {group}, {func}(filing_metrics.{metric}) AS {func.lower()}_{metric} "
                    f"FROM filing_metrics "
                    f"JOIN company ON filing_metrics.company_id = company.company_id "
                    f"JOIN filing ON filing_metrics.filing_id = filing.filing_id "
                    f"GROUP BY {group};"
                )

    join_filters = []
    join_filters.extend([f"company.sic_description = '{sql_quote(industry)}'" for industry in industries])
    join_filters.extend([f"company.state_of_incorporation = '{state}'" for state in states])
    join_filters.extend([f"filing.form_type = '{form}'" for form in forms])
    join_filters.extend([
        "filing_metrics.revenue_usd > 0",
        "filing_metrics.net_income_usd > 0",
        "filing_metrics.net_income_usd < 0",
        "filing_metrics.assets_usd > filing_metrics.liabilities_usd",
    ])
    for group in ["company.sic_description", "company.ticker", "filing.form_type"]:
        for metric in metrics:
            for func in ["SUM", "AVG", "MIN", "MAX"]:
                for predicate in join_filters:
                    queries["agg_filter_join"].append(
                        f"SELECT {group}, {func}(filing_metrics.{metric}) AS {func.lower()}_{metric} "
                        f"FROM filing_metrics "
                        f"JOIN company ON filing_metrics.company_id = company.company_id "
                        f"JOIN filing ON filing_metrics.filing_id = filing.filing_id "
                        f"WHERE {predicate} GROUP BY {group};"
                    )

    for metric in metrics:
        for func in ["SUM", "AVG", "MIN", "MAX"]:
            queries["agg_temporal"].append(
                f"SELECT fiscal_year, {func}({metric}) AS {func.lower()}_{metric} FROM filing_metrics GROUP BY fiscal_year;"
            )
            queries["agg_temporal"].append(
                f"SELECT fiscal_year, fiscal_period, {func}({metric}) AS {func.lower()}_{metric} "
                f"FROM filing_metrics GROUP BY fiscal_year, fiscal_period;"
            )
            queries["agg_temporal"].append(
                f"SELECT company.ticker, fiscal_year, {func}(filing_metrics.{metric}) AS {func.lower()}_{metric} "
                f"FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id "
                f"GROUP BY company.ticker, fiscal_year;"
            )
        for year in years:
            queries["agg_temporal"].append(
                f"SELECT fiscal_period, AVG({metric}) AS avg_{metric} FROM filing_metrics "
                f"WHERE fiscal_year = {year} GROUP BY fiscal_period;"
            )
            queries["agg_temporal"].append(
                f"SELECT company.sic_description, SUM(filing_metrics.{metric}) AS sum_{metric} "
                f"FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id "
                f"WHERE filing_metrics.fiscal_year = {year} GROUP BY company.sic_description;"
            )

    out = {}
    for slice_name, sqls in queries.items():
        seen = set()
        rows = []
        for sql in sqls:
            norm = " ".join(sql.lower().split())
            if norm in seen:
                continue
            seen.add(norm)
            rows.append(sql)
        out[slice_name] = rows
    return out


def sample_queries_for_splits(query_pool: dict[str, list[str]]) -> tuple[dict[str, list[dict]], dict]:
    rng = random.Random(SEED)
    split_rows = {"train": [], "dev": [], "test": []}
    manifest = {
        "dataset": "SEC",
        "split_targets_per_slice": {"train": 20, "dev": 5, "test": 5},
        "counts_per_slice": {},
        "holdout_policy": "Test is assigned first within each slice and reserved for final evaluation only.",
        "min_train_total": 100,
    }
    for slice_name, sqls in query_pool.items():
        rows = [{"query_id": f"{slice_name}_sec_{i}", "slice": slice_name, "sql": sql} for i, sql in enumerate(sqls, start=1)]
        rng.shuffle(rows)
        chosen = rows[:30]
        buckets = {"test": chosen[:5], "dev": chosen[5:10], "train": chosen[10:30]}
        manifest["counts_per_slice"][slice_name] = {k: len(v) for k, v in buckets.items()}
        for split_name, items in buckets.items():
            split_rows[split_name].extend(items)
    manifest["totals"] = {k: len(v) for k, v in split_rows.items()}
    manifest["train_met_minimum"] = manifest["totals"]["train"] >= manifest["min_train_total"]
    return split_rows, manifest


def write_query_file(path: Path, rows: Iterable[dict], split_name: str | None = None) -> None:
    ensure_dir(path.parent)
    lines = []
    for idx, row in enumerate(rows, start=1):
        label = split_name or row["slice"]
        lines.append(f"-- Query {idx}: {label} ({row['slice']}) id={row['query_id']}")
        lines.append(row["sql"])
        lines.append("")
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def write_slice_files(query_pool: dict[str, list[str]]) -> dict[str, list[dict]]:
    paths = {
        "agg_only": QUERY_ROOT / "Agg" / "agg_queries_SEC.sql",
        "agg_filter": QUERY_ROOT / "Filter" / "filter_queries_SEC.sql",
        "agg_join": QUERY_ROOT / "Join" / "join_queries_SEC.sql",
        "agg_filter_join": QUERY_ROOT / "Mixed" / "mixed_queries_SEC.sql",
        "agg_temporal": QUERY_ROOT / "Temporal" / "temporal_queries_SEC.sql",
    }
    out = {}
    for slice_name, sqls in query_pool.items():
        rows = [{"query_id": f"{slice_name}_sec_{i}", "slice": slice_name, "sql": sql} for i, sql in enumerate(sqls, start=1)]
        write_query_file(paths[slice_name], rows)
        out[slice_name] = rows
    return out


def write_sqlite_db(db_path: Path, table_rows: dict[str, list[dict]], table_fields: dict[str, list[str]]) -> None:
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    try:
        for table_name, fields in table_fields.items():
            conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
            conn.execute(f'CREATE TABLE "{table_name}" ({", ".join(f"""\"{field}\" TEXT""" for field in fields)})')
            rows = table_rows[table_name]
            if not rows:
                continue
            placeholders = ", ".join("?" for _ in fields)
            conn.executemany(
                f'INSERT INTO "{table_name}" ({", ".join(fields)}) VALUES ({placeholders})',
                [[row.get(field, "") for field in fields] for row in rows],
            )
        conn.commit()
    finally:
        conn.close()


def build_attribute_payload() -> dict:
    return {
        "company": {
            "company_id": {"value_type": "str", "description": "stable SEC company identifier, equal to zero-padded CIK."},
            "ticker": {"value_type": "str", "description": "public ticker symbol from SEC company_tickers.json."},
            "name": {"value_type": "str", "description": "issuer name from SEC submissions JSON."},
            "sic": {"value_type": "str", "description": "SEC standard industrial classification code."},
            "sic_description": {"value_type": "str", "description": "SEC industry description."},
            "state_of_incorporation": {"value_type": "str", "description": "issuer state of incorporation."},
            "fiscal_year_end": {"value_type": "str", "description": "fiscal year end from SEC submissions JSON."},
        },
        "filing": {
            "filing_id": {"value_type": "str", "description": "stable filing identifier, accession number without dashes."},
            "company_id": {"value_type": "str", "description": "foreign key to company.company_id."},
            "accession_number": {"value_type": "str", "description": "original SEC accession number with dashes."},
            "form_type": {"value_type": "str", "description": "SEC form type, restricted here to 10-K and 10-Q."},
            "filing_date": {"value_type": "str", "description": "EDGAR filing date in ISO format."},
            "report_date": {"value_type": "str", "description": "report period end date in ISO format when available."},
            "fiscal_year": {"value_type": "int", "description": "fiscal year inferred from companyfacts rows linked to the filing."},
            "fiscal_period": {"value_type": "str", "description": "fiscal period code such as Q1, Q2, Q3, or FY."},
            "source_url": {"value_type": "str", "description": "direct SEC archive URL for the raw filing HTML."},
        },
        "financial_fact": {
            "fact_id": {"value_type": "str", "description": "stable synthetic fact row identifier."},
            "company_id": {"value_type": "str", "description": "foreign key to company.company_id."},
            "filing_id": {"value_type": "str", "description": "foreign key to filing.filing_id."},
            "concept_id": {"value_type": "str", "description": "foreign key to concept.concept_id."},
            "value": {"value_type": "float", "description": "numeric fact value from SEC companyfacts."},
            "unit_id": {"value_type": "str", "description": "foreign key to unit.unit_id; units remain explicit."},
            "period_start": {"value_type": "str", "description": "start date for duration facts, empty for instant facts."},
            "period_end": {"value_type": "str", "description": "end date for the fact context."},
            "fiscal_year": {"value_type": "int", "description": "fiscal year supplied by SEC companyfacts when present."},
            "fiscal_period": {"value_type": "str", "description": "fiscal period supplied by SEC companyfacts when present."},
        },
        "filing_metrics": {
            "filing_id": {"value_type": "str", "description": "foreign key to filing.filing_id."},
            "company_id": {"value_type": "str", "description": "foreign key to company.company_id."},
            "revenue_usd": {"value_type": "float", "description": "canonical revenue fact selected from SEC companyfacts for the filing."},
            "assets_usd": {"value_type": "float", "description": "canonical total assets fact for the filing."},
            "liabilities_usd": {"value_type": "float", "description": "canonical total liabilities fact for the filing."},
            "net_income_usd": {"value_type": "float", "description": "canonical net income or profit/loss fact for the filing."},
            "operating_cash_flow_usd": {"value_type": "float", "description": "canonical operating cash flow fact for the filing."},
            "shares_outstanding": {"value_type": "float", "description": "canonical shares outstanding fact for the filing."},
            "market_cap_usd": {"value_type": "float", "description": "reserved column; null because SEC companyfacts does not provide a reliable filing-level market cap series across issuers."},
        },
    }


def write_data_dictionary(path: Path, table_fields: dict[str, list[str]]) -> None:
    descriptions = {
        "company": "One row per issuer. Stable key is company_id = zero-padded CIK.",
        "filing": "One row per selected 10-K or 10-Q filing.",
        "concept": "One row per SEC taxonomy concept observed in the retained facts.",
        "period": "One row per unique fact period context.",
        "unit": "One row per explicit SEC unit string.",
        "financial_fact": "Atomic numeric XBRL fact rows filtered to the selected companies and filings only.",
        "filing_metrics": "Derived filing-level metric table built strictly from the retained SEC facts for aggregation-heavy evaluation.",
    }
    lines = [
        "# SEC Benchmark Data Dictionary",
        "",
        "Official sources:",
        "- https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
        "- https://www.sec.gov/files/company_tickers.json",
        "",
        "The benchmark keeps raw filings on disk, preserves normalized SEC fact tables, and adds one derived `filing_metrics` table for workload construction.",
        "",
    ]
    for table_name, fields in table_fields.items():
        lines.append(f"## {table_name}")
        lines.append("")
        lines.append(descriptions.get(table_name, ""))
        lines.append("")
        for field in fields:
            lines.append(f"- `{field}`")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    random.seed(SEED)

    reset_dir(DATA_ROOT)
    reset_dir(QUERY_ROOT)
    reset_dir(SOURCE_ROOT / "raw_html")
    reset_dir(SOURCE_ROOT / "filing")
    reset_dir(SOURCE_ROOT / "filing_metrics")
    reset_dir(SOURCE_ROOT / "company")
    ensure_dir(SOURCE_ROOT / "api_cache" / "submissions")
    ensure_dir(SOURCE_ROOT / "api_cache" / "companyfacts")

    ticker_universe = fetch_company_universe()
    company_rows = []
    filing_rows = []
    texts_by_filing = {}
    raw_facts = []
    concept_map = {}
    period_counter: Counter = Counter()
    filing_fp_counter: Counter = Counter()

    for ticker in TARGET_TICKERS:
        company_meta = ticker_universe[ticker]
        submission_payload, bundles = load_submission_bundle(company_meta["cik"])
        company_rows.append(
            {
                "company_id": company_meta["cik"],
                "cik": company_meta["cik"],
                "ticker": ticker,
                "name": submission_payload.get("name") or company_meta["title"],
                "sic": submission_payload.get("sic") or "",
                "sic_description": submission_payload.get("sicDescription") or "",
                "state_of_incorporation": submission_payload.get("stateOfIncorporation") or "",
                "fiscal_year_end": submission_payload.get("fiscalYearEnd") or "",
                "entity_type": submission_payload.get("entityType") or "",
            }
        )
        selected_filings = select_filings_for_company(company_meta, submission_payload, bundles)
        accessions = {row["accession_number"] for row in selected_filings}
        facts, concepts, company_periods, filing_periods = extract_companyfacts(company_meta["cik"], accessions)
        raw_facts.extend(facts)
        concept_map.update(concepts)
        period_counter.update(company_periods)
        filing_fp_counter.update(filing_periods)
        for filing in selected_filings:
            filing["filing_id"] = filing["accession_nodash"]
            html_payload = fetch_text(
                filing["source_url"],
                SOURCE_ROOT / "raw_html" / f"{filing['filing_id']}.html",
            )
            texts_by_filing[filing["filing_id"]] = html_to_text(html_payload)
            filing_rows.append(filing)

    for filing in filing_rows:
        best = ("", "")
        best_count = -1
        for (accession, fy, fp), count in filing_fp_counter.items():
            if accession == filing["accession_number"] and count > best_count:
                best = (fy, fp)
                best_count = count
        filing["fiscal_year"], filing["fiscal_period"] = best
        filing["fiscal_quarter"] = infer_quarter(best[1])

    period_rows = []
    period_id_map = {}
    for idx, period_key in enumerate(sorted(period_counter), start=1):
        period_id = f"period_{idx:06d}"
        period_id_map[period_key] = period_id
        start, end, fy, fp, frame, kind = period_key
        period_rows.append(
            {
                "period_id": period_id,
                "period_start": start,
                "period_end": end,
                "fiscal_year": fy,
                "fiscal_period": fp,
                "fiscal_quarter": infer_quarter(fp),
                "frame": frame,
                "period_type": kind,
            }
        )

    concept_rows = sorted(concept_map.values(), key=lambda row: row["concept_id"])
    unit_rows = [{"unit_id": unit_id, "unit_name": unit_id} for unit_id in sorted({fact.unit_id for fact in raw_facts})]
    facts_by_filing = defaultdict(list)
    fact_rows_csv = []
    for fact in raw_facts:
        fact.period_id = period_id_map[(fact.period_start, fact.period_end, fact.fiscal_year, fact.fiscal_period, fact.frame, fact.period_type)]
        facts_by_filing[fact.filing_id].append(fact)
        fact_rows_csv.append(
            {
                "fact_id": fact.fact_id,
                "company_id": fact.company_id,
                "filing_id": fact.filing_id,
                "accession_number": fact.accession_number,
                "concept_id": fact.concept_id,
                "concept_name": fact.concept_name,
                "taxonomy": fact.taxonomy,
                "value": serialize_decimal(fact.value),
                "unit_id": fact.unit_id,
                "period_id": fact.period_id,
                "period_start": fact.period_start,
                "period_end": fact.period_end,
                "period_type": fact.period_type,
                "fiscal_year": fact.fiscal_year,
                "fiscal_period": fact.fiscal_period,
                "fiscal_quarter": fact.fiscal_quarter,
                "form_type": fact.form_type,
                "filed_date": fact.filed_date,
                "frame": fact.frame,
                "source_api_url": fact.source_api_url,
            }
        )

    filing_rows_csv = []
    for filing in filing_rows:
        filing_rows_csv.append(
            {
                "filing_id": filing["filing_id"],
                "company_id": filing["company_id"],
                "ticker": filing["ticker"],
                "company_name": filing["company_name"],
                "accession_number": filing["accession_number"],
                "accession_nodash": filing["accession_nodash"],
                "form_type": filing["form_type"],
                "filing_date": filing["filing_date"],
                "report_date": filing["report_date"],
                "acceptance_datetime": filing["acceptance_datetime"],
                "fiscal_year": filing["fiscal_year"],
                "fiscal_period": filing["fiscal_period"],
                "fiscal_quarter": filing["fiscal_quarter"],
                "sic": filing["sic"],
                "sic_description": filing["sic_description"],
                "state_of_incorporation": filing["state_of_incorporation"],
                "fiscal_year_end": filing["fiscal_year_end"],
                "primary_document": filing["primary_document"],
                "primary_doc_description": filing["primary_doc_description"],
                "source_url": filing["source_url"],
                "raw_html_path": str((SOURCE_ROOT / "raw_html" / f"{filing['filing_id']}.html").relative_to(ROOT)),
                "raw_text_path": str((SOURCE_ROOT / "filing" / f"{filing['filing_id']}.txt").relative_to(ROOT)),
                "is_xbrl": filing["is_xbrl"],
                "is_inline_xbrl": filing["is_inline_xbrl"],
            }
        )

    filing_metrics_rows = [build_metric_row(filing, facts_by_filing) for filing in filing_rows_csv]
    document_manifest_rows = emit_corpus_docs(filing_rows_csv, texts_by_filing)

    query_pool = build_queries(filing_metrics_rows, company_rows, filing_rows_csv)
    slice_rows = write_slice_files(query_pool)
    split_rows, split_manifest = sample_queries_for_splits(query_pool)
    write_query_file(QUERY_ROOT / "Splits" / "train.sql", split_rows["train"], "train")
    write_query_file(QUERY_ROOT / "Splits" / "dev.sql", split_rows["dev"], "dev")
    write_query_file(QUERY_ROOT / "Splits" / "test.sql", split_rows["test"], "test")
    write_json(QUERY_ROOT / "Splits" / "manifest.json", split_manifest)
    write_json(QUERY_ROOT / "SEC_attributes.json", build_attribute_payload())

    table_fields = {
        "company": ["company_id", "cik", "ticker", "name", "sic", "sic_description", "state_of_incorporation", "fiscal_year_end", "entity_type"],
        "filing": [
            "filing_id", "company_id", "ticker", "company_name", "accession_number", "accession_nodash",
            "form_type", "filing_date", "report_date", "acceptance_datetime", "fiscal_year",
            "fiscal_period", "fiscal_quarter", "sic", "sic_description", "state_of_incorporation",
            "fiscal_year_end", "primary_document", "primary_doc_description", "source_url",
            "raw_html_path", "raw_text_path", "is_xbrl", "is_inline_xbrl",
        ],
        "concept": ["concept_id", "taxonomy", "concept_name", "label", "description"],
        "period": ["period_id", "period_start", "period_end", "fiscal_year", "fiscal_period", "fiscal_quarter", "frame", "period_type"],
        "unit": ["unit_id", "unit_name"],
        "financial_fact": [
            "fact_id", "company_id", "filing_id", "accession_number", "concept_id", "concept_name",
            "taxonomy", "value", "unit_id", "period_id", "period_start", "period_end", "period_type",
            "fiscal_year", "fiscal_period", "fiscal_quarter", "form_type", "filed_date", "frame", "source_api_url",
        ],
        "filing_metrics": [
            "filing_id", "company_id", "ticker", "company_name", "form_type", "filing_date", "report_date",
            "fiscal_year", "fiscal_period", "fiscal_quarter", "sic", "sic_description", "state_of_incorporation",
            "revenue_usd", "revenue_usd_concept_id", "revenue_usd_unit_id", "revenue_usd_period_start", "revenue_usd_period_end",
            "assets_usd", "assets_usd_concept_id", "assets_usd_unit_id", "assets_usd_period_start", "assets_usd_period_end",
            "liabilities_usd", "liabilities_usd_concept_id", "liabilities_usd_unit_id", "liabilities_usd_period_start", "liabilities_usd_period_end",
            "net_income_usd", "net_income_usd_concept_id", "net_income_usd_unit_id", "net_income_usd_period_start", "net_income_usd_period_end",
            "operating_cash_flow_usd", "operating_cash_flow_usd_concept_id", "operating_cash_flow_usd_unit_id", "operating_cash_flow_usd_period_start", "operating_cash_flow_usd_period_end",
            "investing_cash_flow_usd", "investing_cash_flow_usd_concept_id", "investing_cash_flow_usd_unit_id", "investing_cash_flow_usd_period_start", "investing_cash_flow_usd_period_end",
            "financing_cash_flow_usd", "financing_cash_flow_usd_concept_id", "financing_cash_flow_usd_unit_id", "financing_cash_flow_usd_period_start", "financing_cash_flow_usd_period_end",
            "shares_outstanding", "shares_outstanding_concept_id", "shares_outstanding_unit_id", "shares_outstanding_period_start", "shares_outstanding_period_end",
            "market_cap_usd", "market_cap_usd_concept_id", "market_cap_usd_unit_id", "market_cap_usd_period_start", "market_cap_usd_period_end",
        ],
    }

    table_rows = {
        "company": company_rows,
        "filing": filing_rows_csv,
        "concept": concept_rows,
        "period": period_rows,
        "unit": unit_rows,
        "financial_fact": fact_rows_csv,
        "filing_metrics": filing_metrics_rows,
    }
    for table_name, rows in table_rows.items():
        write_csv(DATA_ROOT / f"{table_name}.csv", rows, table_fields[table_name])

    write_csv(DATA_ROOT / "document_manifest.csv", document_manifest_rows, list(document_manifest_rows[0].keys()))
    with (SOURCE_ROOT / "manifest.jsonl").open("w", encoding="utf-8") as handle:
        for row in document_manifest_rows:
            handle.write(json.dumps(row) + "\n")

    write_sqlite_db(DATA_ROOT / "sec_gold.sqlite", table_rows, table_fields)
    write_data_dictionary(DATA_ROOT / "data_dictionary.md", table_fields)

    validation = {
        "built_at": datetime.utcnow().isoformat() + "Z",
        "source_urls": [
            "https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
            "https://www.sec.gov/files/company_tickers.json",
        ],
        "date_range": {"start_year": START_YEAR, "end_year": END_YEAR},
        "tickers": TARGET_TICKERS,
        "counts": {
            "companies": len(company_rows),
            "filings": len(filing_rows_csv),
            "documents": len(document_manifest_rows),
            "gold_facts": len(fact_rows_csv),
            "queries": {name: len(rows) for name, rows in slice_rows.items()},
            "rows_per_table": {name: len(rows) for name, rows in table_rows.items()},
            "split_rows": {name: len(rows) for name, rows in split_rows.items()},
        },
        "example_queries": {name: rows[:3] for name, rows in slice_rows.items()},
        "data_quality_issues": [
            "10-Q duration facts are typically year-to-date in SEC companyfacts; filing_metrics selects the canonical filing-linked duration fact and preserves exact period bounds.",
            "Some filings do not expose every preferred metric concept, so filing_metrics keeps nulls instead of inferring missing values.",
            "Market capitalization is left null because SEC companyfacts does not provide a reliable filing-level market cap series across issuers.",
            "Corpus compatibility is achieved by exposing each raw filing text under filing-facing, company-facing, and filing_metrics-facing document views while preserving a canonical per-filing manifest.",
        ],
    }
    write_json(DATA_ROOT / "validation_report.json", validation)
    print(json.dumps(validation["counts"], indent=2))


if __name__ == "__main__":
    main()
