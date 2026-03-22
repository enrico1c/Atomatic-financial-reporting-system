"""
Financial Data Automation System — Main Entry Point

Usage:
  python main.py               # full run (fetch + clean + report)
  python main.py --no-fetch    # skip fetching; use cached raw data
  python main.py --report-only # skip fetch+transform; rebuild Excel + insights only

Pipeline steps:
  1. Ingest  → pull from Yahoo Finance, FRED, ECB, World Bank
  2. Merge   → clean + normalise + merge into unified datasets
  3. Compute → KPIs and monthly report aggregation
  4. Insights→ rule-based text insight generation
  5. Export  → write Excel workbook
"""

import argparse
import sys
import traceback
from datetime import datetime

import pandas as pd

from config.settings import OUTPUT_DIR
from ingestion.yahoo_finance import YahooFinanceIngestion
from ingestion.fred_data     import FREDIngestion
from ingestion.ecb_data      import ECBIngestion
from ingestion.worldbank_data import WorldBankIngestion
from transformation.merger   import DataMerger
from reporting.kpi_calculator import KPICalculator
from reporting.monthly_report import MonthlyReportBuilder
from reporting.insights_engine import InsightsEngine
from excel.workbook_builder  import WorkbookBuilder
from utils.logger import get_logger

log = get_logger("main")


def parse_args():
    p = argparse.ArgumentParser(description="Financial automation system")
    p.add_argument("--no-fetch",    action="store_true", help="Use cached raw data")
    p.add_argument("--report-only", action="store_true", help="Skip fetch+transform, rebuild reports")
    return p.parse_args()


def ingest(skip_fetch: bool) -> dict[str, pd.DataFrame]:
    """Step 1: Data ingestion from all sources."""
    raw: dict[str, pd.DataFrame] = {}

    if skip_fetch:
        log.info("--no-fetch: loading raw data from disk")
        for src in ["yahoo", "fred", "ecb", "worldbank"]:
            from ingestion.base_ingestion import BaseIngestion
            from config.settings import RAW_DIR
            src_dir = RAW_DIR / src
            if src_dir.exists():
                for f in src_dir.glob("*.csv"):
                    try:
                        raw[f"{src}_{f.stem}"] = pd.read_csv(f, index_col=0, parse_dates=True)
                    except Exception as e:
                        log.warning(f"Could not load {f}: {e}")
        return raw

    # Yahoo Finance
    log.info("=== Ingesting Yahoo Finance ===")
    try:
        yf_data = YahooFinanceIngestion().fetch()
        raw.update(yf_data)
        log.info(f"Yahoo Finance: {list(yf_data.keys())}")
    except Exception as e:
        log.error(f"Yahoo Finance ingestion failed: {e}")

    # FRED
    log.info("=== Ingesting FRED ===")
    try:
        fred_ingest = FREDIngestion()
        fred_combined = fred_ingest.fetch_combined()
        if not fred_combined.empty:
            raw["fred_combined"] = fred_combined
        log.info(f"FRED: {fred_combined.shape if not fred_combined.empty else 'empty'}")
    except Exception as e:
        log.error(f"FRED ingestion failed: {e}")

    # ECB
    log.info("=== Ingesting ECB ===")
    try:
        ecb_ingest = ECBIngestion()
        ecb_combined = ecb_ingest.fetch_combined()
        if not ecb_combined.empty:
            raw["ecb_combined"] = ecb_combined
        log.info(f"ECB: {ecb_combined.shape if not ecb_combined.empty else 'empty'}")
    except Exception as e:
        log.error(f"ECB ingestion failed (non-fatal, continuing): {e}")

    # World Bank
    log.info("=== Ingesting World Bank ===")
    try:
        wb_ingest = WorldBankIngestion()
        wb_results = wb_ingest.fetch()
        if wb_results:
            # Use first available indicator as combined placeholder
            # (World Bank data is per-indicator, per-country; kept separate)
            raw["worldbank_combined"] = pd.concat(
                list(wb_results.values()), axis=0
            ) if wb_results else pd.DataFrame()
        log.info(f"World Bank indicators fetched: {list(wb_results.keys())}")
    except Exception as e:
        log.error(f"World Bank ingestion failed (non-fatal, continuing): {e}")

    return raw


def transform(raw: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Step 2: Clean, normalise, and merge all raw data."""
    log.info("=== Transformation layer ===")
    merger = DataMerger(raw)
    clean = merger.run()
    return clean


def compute(clean: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Step 3: Compute KPIs and build monthly report."""
    log.info("=== Computing KPIs ===")
    kpi_calc = KPICalculator(clean)
    kpis = kpi_calc.compute_all()

    log.info("=== Building monthly report ===")
    monthly_report = MonthlyReportBuilder(clean).build()

    clean["kpi_summary"]    = kpis.get("kpi_summary", pd.DataFrame())
    clean["monthly_report"] = monthly_report

    return clean, kpis


def generate_insights(clean: dict, kpis: dict) -> list[str]:
    """Step 4: Generate rule-based text insights."""
    log.info("=== Generating insights ===")
    macro = clean.get("macro_monthly", pd.DataFrame())
    engine = InsightsEngine(kpis, macro)
    return engine.generate()


def export(clean: dict, insights: list[str]) -> None:
    """Step 5: Write Excel workbook."""
    log.info("=== Exporting to Excel ===")
    builder = WorkbookBuilder(clean, insights)
    path = builder.build()
    log.info(f"Excel report saved: {path}")
    print(f"\n✓ Report ready: {path}\n")


def run(args):
    start = datetime.now()
    log.info(f"Pipeline started at {start.isoformat()}")

    try:
        # -- Ingest
        if args.report_only:
            log.info("--report-only: loading clean data from disk")
            clean = DataMerger.load_clean()
            if not clean:
                log.error("No clean data found. Run without --report-only first.")
                sys.exit(1)
        else:
            raw   = ingest(skip_fetch=args.no_fetch)
            clean = transform(raw)

        # -- Compute
        clean, kpis = compute(clean)

        # -- Insights
        insights = generate_insights(clean, kpis)

        # -- Export
        export(clean, insights)

    except Exception as e:
        log.error(f"Pipeline failed: {e}")
        log.debug(traceback.format_exc())
        sys.exit(1)

    elapsed = (datetime.now() - start).total_seconds()
    log.info(f"Pipeline completed in {elapsed:.1f}s")


if __name__ == "__main__":
    run(parse_args())
