"""
Rule-based insights engine.

Generates plain-English sentences by evaluating KPIs against defined thresholds.
No AI/LLM required. All logic is explicit and auditable.

Output examples:
  "AAPL delivered a 1-year return of +18.3%, outperforming its 63d avg volatility of 22.1%."
  "The US 10Y-2Y yield spread is -0.45%, signalling an inverted yield curve — historically
   associated with recession risk within 12-18 months."
  "Fed Funds Rate rose 25bps to 5.50%, indicating continued monetary tightening."
  "ECB Main Refinancing Rate is 4.50%, up 0bps MoM, suggesting a pause in hike cycle."
"""

from datetime import datetime

import pandas as pd

from config.settings import THRESHOLDS
from utils.logger import get_logger

log = get_logger("reporting.insights_engine")


class InsightsEngine:
    def __init__(self, kpi_data: dict[str, pd.DataFrame], macro: pd.DataFrame):
        self.kpis  = kpi_data
        self.macro = macro

    # ── Public ─────────────────────────────────────────────────────────────────
    def generate(self) -> list[str]:
        insights = []
        insights += self._macro_insights()
        insights += self._equity_insights()
        insights += self._statement_insights()
        insights += self._risk_alerts()
        log.info(f"Generated {len(insights)} insights")
        return insights

    # ── Macro insights ─────────────────────────────────────────────────────────
    def _macro_insights(self) -> list[str]:
        out = []
        macro = self.macro
        if macro is None or macro.empty:
            return out

        latest_date = macro.dropna(how="all").index[-1].strftime("%b %Y")

        def last(col):
            if col in macro.columns:
                s = macro[col].dropna()
                return s.iloc[-1] if not s.empty else None
            return None

        def prev(col, n=1):
            s = macro[col].dropna() if col in macro.columns else pd.Series()
            return s.iloc[-1 - n] if len(s) > n else None

        # Fed Funds Rate
        ffr = last("fed_funds_rate")
        ffr_prev = prev("fed_funds_rate")
        if ffr is not None and ffr_prev is not None:
            delta = ffr - ffr_prev
            if abs(delta) >= THRESHOLDS["rate_rise_threshold"]:
                direction = "raised" if delta > 0 else "cut"
                out.append(
                    f"[RATES] Fed Funds Rate {direction} by {abs(delta)*100:.0f}bps "
                    f"to {ffr:.2f}% as of {latest_date}."
                )
            else:
                out.append(
                    f"[RATES] Fed Funds Rate held steady at {ffr:.2f}% as of {latest_date} "
                    f"(change: {delta*100:+.1f}bps)."
                )

        # Yield curve
        spread = last("yield_spread_10y_2y")
        if spread is not None:
            if spread < THRESHOLDS["yield_curve_inversion"]:
                out.append(
                    f"[YIELD CURVE] The 10Y-2Y spread is {spread:.2f}% — "
                    "inverted yield curve signals elevated recession risk."
                )
            elif spread < 0.5:
                out.append(
                    f"[YIELD CURVE] The 10Y-2Y spread is a thin {spread:.2f}% — "
                    "flattening curve warrants monitoring."
                )
            else:
                out.append(
                    f"[YIELD CURVE] The 10Y-2Y spread is {spread:.2f}% — "
                    "normal upward slope, no immediate inversion signal."
                )

        # CPI / Inflation
        cpi = last("cpi_all_urban")
        cpi_yoy = None
        if "cpi_all_urban" in macro.columns:
            cpi_s = macro["cpi_all_urban"].dropna()
            if len(cpi_s) >= 13:
                cpi_yoy = (cpi_s.iloc[-1] / cpi_s.iloc[-13] - 1) * 100
        if cpi_yoy is not None:
            if cpi_yoy > THRESHOLDS["inflation_high"]:
                out.append(
                    f"[INFLATION] US CPI is running at {cpi_yoy:.1f}% YoY — "
                    f"well above the {THRESHOLDS['inflation_target']}% target; "
                    "monetary tightening pressure remains elevated."
                )
            elif cpi_yoy > THRESHOLDS["inflation_target"]:
                out.append(
                    f"[INFLATION] US CPI is {cpi_yoy:.1f}% YoY — "
                    f"above the {THRESHOLDS['inflation_target']}% target but trending toward normalisation."
                )
            else:
                out.append(
                    f"[INFLATION] US CPI is {cpi_yoy:.1f}% YoY — "
                    f"at or below the {THRESHOLDS['inflation_target']}% target; "
                    "disinflationary environment."
                )

        # Unemployment
        unemp = last("unemployment_rate")
        if unemp is not None:
            if unemp > THRESHOLDS["unemployment_high"]:
                out.append(
                    f"[EMPLOYMENT] Unemployment at {unemp:.1f}% — above {THRESHOLDS['unemployment_high']}%, "
                    "indicating labour market stress."
                )
            else:
                out.append(
                    f"[EMPLOYMENT] Unemployment rate is {unemp:.1f}% — labour market remains robust."
                )

        # ECB
        ecb_rate = last("ecb_main_refi_rate")
        ecb_prev = prev("ecb_main_refi_rate")
        if ecb_rate is not None:
            if ecb_prev is not None:
                ecb_delta = ecb_rate - ecb_prev
                direction = "hiked" if ecb_delta > 0 else "cut" if ecb_delta < 0 else "held"
                out.append(
                    f"[ECB] Main Refinancing Rate {direction} to {ecb_rate:.2f}% "
                    f"(Δ {ecb_delta*100:+.0f}bps) as of {latest_date}."
                )
            else:
                out.append(f"[ECB] Main Refinancing Rate is {ecb_rate:.2f}% as of {latest_date}.")

        # Real rate
        real_r = last("real_fed_funds_rate")
        if real_r is not None:
            sign = "positive" if real_r > 0 else "negative"
            out.append(
                f"[REAL RATES] Estimated real Fed Funds Rate is {real_r:.2f}% ({sign}) — "
                + ("restrictive monetary conditions." if real_r > 1 else
                   "accommodative/neutral conditions." if real_r >= 0 else
                   "financial conditions remain loose in real terms.")
            )

        return out

    # ── Equity insights ────────────────────────────────────────────────────────
    def _equity_insights(self) -> list[str]:
        out = []
        price_kpis = self.kpis.get("price_kpis")
        if price_kpis is None or price_kpis.empty:
            return out

        for ticker, row in price_kpis.iterrows():
            ret_1y = row.get("return_1y_%")
            ret_1m = row.get("return_1m_%")
            vol_21 = row.get("vol_21d_%")
            vol_63 = row.get("vol_63d_%")
            sharpe = row.get("sharpe_1y")
            maxdd  = row.get("maxdd_1y_%")

            parts = []

            if pd.notna(ret_1y):
                direction = "gained" if ret_1y > 0 else "lost"
                parts.append(f"1Y return: {direction} {abs(ret_1y):.1f}%")

            if pd.notna(ret_1m):
                direction = "up" if ret_1m > 0 else "down"
                parts.append(f"1M: {direction} {abs(ret_1m):.1f}%")

            if pd.notna(vol_21) and pd.notna(vol_63):
                if vol_21 > vol_63 * THRESHOLDS["volatility_high_mult"]:
                    parts.append(
                        f"short-term volatility elevated ({vol_21:.1f}% vs {vol_63:.1f}% 63d avg)"
                    )
                else:
                    parts.append(f"vol stable ({vol_21:.1f}% / {vol_63:.1f}%)")

            if pd.notna(sharpe):
                quality = "strong" if sharpe > 1 else "moderate" if sharpe > 0.5 else "weak"
                parts.append(f"Sharpe {sharpe:.2f} ({quality})")

            if pd.notna(maxdd):
                parts.append(f"max drawdown {maxdd:.1f}%")

            if parts:
                out.append(f"[{ticker}] " + " | ".join(parts) + ".")

        return out

    # ── Financial statement insights ───────────────────────────────────────────
    def _statement_insights(self) -> list[str]:
        out = []
        stmt_kpis = self.kpis.get("statement_kpis")
        if stmt_kpis is None or stmt_kpis.empty:
            return out

        for ticker, row in stmt_kpis.iterrows():
            parts = []

            rev_yoy = row.get("revenue_yoy_%")
            if pd.notna(rev_yoy):
                if rev_yoy > THRESHOLDS["revenue_growth_high"] * 100:
                    parts.append(f"revenue grew strongly +{rev_yoy:.1f}% YoY")
                elif rev_yoy < THRESHOLDS["revenue_growth_low"] * 100:
                    parts.append(f"revenue declined {rev_yoy:.1f}% YoY — contraction signal")
                else:
                    parts.append(f"revenue {rev_yoy:+.1f}% YoY")

            gm = row.get("gross_margin_%")
            if pd.notna(gm):
                quality = "high" if gm > 50 else "moderate" if gm > 25 else "thin"
                parts.append(f"gross margin {gm:.1f}% ({quality})")

            nm = row.get("net_margin_%")
            if pd.notna(nm):
                parts.append(f"net margin {nm:.1f}%")

            dte = row.get("debt_to_equity")
            if pd.notna(dte):
                leverage = "highly leveraged" if dte > 2 else "moderate leverage" if dte > 1 else "low leverage"
                parts.append(f"D/E {dte:.2f} ({leverage})")

            if parts:
                out.append(f"[{ticker} FUNDAMENTALS] " + " | ".join(parts) + ".")

        return out

    # ── Risk alerts ────────────────────────────────────────────────────────────
    def _risk_alerts(self) -> list[str]:
        out = []
        price_kpis = self.kpis.get("price_kpis")
        macro_kpis = self.kpis.get("macro_kpis")

        # Broad market drawdown alert (SPY)
        if price_kpis is not None and "SPY" in price_kpis.index:
            spy_dd = price_kpis.loc["SPY", "maxdd_1y_%"]
            if pd.notna(spy_dd) and spy_dd < -15:
                out.append(
                    f"[ALERT] S&P 500 ETF (SPY) max 1Y drawdown is {spy_dd:.1f}% — "
                    "significant equity market stress detected."
                )

        # Macro inversion check (already handled above, add summary if inverted)
        if macro_kpis is not None and "yield_spread_10y_2y" in macro_kpis.index:
            spread_now = macro_kpis.loc["yield_spread_10y_2y", "latest"]
            if pd.notna(spread_now) and spread_now < 0:
                out.append(
                    "[ALERT] Yield curve is inverted — historically a leading recession indicator "
                    f"(spread: {spread_now:.2f}%)."
                )

        if not out:
            out.append(
                f"[STATUS] No critical risk alerts as of {datetime.now().strftime('%Y-%m-%d')}. "
                "Continue routine monitoring."
            )

        return out
