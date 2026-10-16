"""BREADTH-CN-001 Track B5: dated CFFEX cost and rule table for IC (one row per change event).

Every row carries its primary notice (cffex.com.cn) or, where the value only lives in member-only notices, a
PRESS_REPORTED citation to contemporaneous coverage.  Rows that do not bind IC are kept for completeness and marked
binding_for_ic = N/A (value N/A).  ASSUMPTION rows are inputs the cost model needs but no notice supplies.

Statuses: VERIFIED_PRIMARY (value read from the notice text) | VERIFIED_PRIMARY_SNAPSHOT (read from a current page,
not dated by a change notice) | PRESS_REPORTED | ASSUMPTION | NOT_EXTRACTED.
effective_basis: trading_day (from that trading day) | settlement (from that day's settlement, i.e. positions held
after the close) | snapshot (as retrieved) | assumed_window_start.

Usage: python b5_build_table.py --out <csv>
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

C = "http://www.cffex.com.cn/cn/"
NBD18 = "https://www.nbd.com.cn/articles/2018-12-02/1278079.html"
NBD19 = "https://www.nbd.com.cn/articles/2019-04-21/1323655.html"
YICAI = "https://www.yicai.com/news/100071252.html"

COLUMNS = ["parameter", "products", "side", "hedge_class", "effective_from", "effective_basis", "event_type", "value",
           "value_kind", "unit", "binding_for_ic", "notice_title", "notice_date", "url", "status", "note"]  # fmt: skip
STATUSES = {
    "VERIFIED_PRIMARY",
    "VERIFIED_PRIMARY_SNAPSHOT",
    "PRESS_REPORTED",
    "ASSUMPTION",
    "NOT_EXTRACTED",
}
EVENT_TYPES = {"change", "restatement", "snapshot", "assumption"}
SIDES = {"both", "long", "short"}
HEDGE = {"all", "hedge", "non_hedge"}


def row(
    parameter,
    products,
    side,
    hedge,
    eff,
    basis,
    event,
    value,
    unit,
    title,
    ndate,
    url,
    status,
    note="",
    binding=None,
):
    ic = "IC" in products.split("|")
    b = binding or ("yes" if ic else "N/A")
    kind = "N/A" if value == "N/A" else ("number" if _isnum(value) else "text")
    return dict(zip(COLUMNS, [parameter, products, side, hedge, eff, basis, event, "N/A" if b == "N/A" and not ic else value, kind if not (b == "N/A" and not ic) else "N/A", unit, b, title, ndate, url, status, note], strict=True))  # fmt: skip


def _isnum(v) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


ANNOUNCED = {"2015-08-25": "2015-08-25", "2015-08-28": "2015-08-28", "2015-09-07": "2015-09-02", "2017-02-17": "2017-02-16",
             "2018-12-03": "2018-12-02", "2019-04-22": "2019-04-19"}  # fmt: skip


def build() -> list[dict]:
    r: list[dict] = []
    t_fee = "关于调整股指期货手续费标准的通知"
    t_mar = "关于调整沪深300、上证50、中证500股指期货交易保证金的通知"
    # ---- exchange fees
    r.append(row("trade_fee_bp", "IF|IH|IC", "both", "all", "2015-08-03", "trading_day", "change", "0.23", "bp of turnover", t_fee, "2015-07-31", C + "jystz/20150731/19201.html", "VERIFIED_PRIMARY", "applies to open and close; close-today rate set separately from 2015-08-26"))  # fmt: skip
    r.append(row("order_fee_yuan", "IF|IH|IC", "both", "all", "2015-08-03", "trading_day", "change", "1", "yuan per order (buy, sell, cancel)", t_fee, "2015-07-31", C + "jystz/20150731/19201.html", "VERIFIED_PRIMARY"))  # fmt: skip
    for eff, nd, val, nid, prods in [
        ("2015-08-26", "2015-08-25", "1.15", "20150825/19246", "IF|IH|IC"),
        ("2015-09-07", "2015-09-02", "23", "20150902/19269", "IF|IH|IC"),
        ("2017-02-17", "2017-02-16", "9.2", "20170216/20198", "IF|IH|IC"),
        ("2017-09-18", "2017-09-15", "6.9", "20170915/20369", "IF|IH|IC"),
        ("2018-12-03", "2018-12-02", "4.6", "20181202/23407", "IF|IH|IC"),
        ("2019-04-22", "2019-04-19", "3.45", "20190419/23719", "IF|IH|IC"),
        ("2023-03-20", "2023-03-17", "2.3", "20230317/31868", "IF|IH|IC|IM"),
    ]:
        note = "中金所发〔2023〕16号; adds CSI1000 (IM)" if eff == "2023-03-20" else ""
        r.append(row("close_today_fee_bp", prods, "both", "all", eff, "trading_day", "change", val, "bp of turnover", t_fee, nd, C + f"jystz/{nid}.html", "VERIFIED_PRIMARY", note))  # fmt: skip
    for p, v, u in [
        ("trade_fee_bp", "0.23", "bp of turnover"),
        ("close_today_fee_bp", "2.3", "bp of turnover"),
        ("order_fee_yuan", "1", "yuan per order"),
    ]:
        r.append(row(p, "IF|IH|IC|IM", "both", "all", "2024-07-01", "snapshot", "restatement", v, u, "中国金融期货交易所收费一览表 (更新时间 2024年7月)", "2024-07-01", C + "zjssf/20240701/39212.html", "VERIFIED_PRIMARY_SNAPSHOT", "current schedule; confirms no later change to these three"))  # fmt: skip
    # ---- margin (IC rows bind; IF|IH rows are the same notices' other products, kept as N/A)
    m = "margin_pct"
    r.append(row(m, "IC", "short", "non_hedge", "2015-07-08", "settlement", "change", "20", "% of contract value", "关于调整中证500股指期货交易保证金的通知", "2015-07-08", C + "jystz/20150708/19147.html", "VERIFIED_PRIMARY", "sell positions 10% -> 20%; hedging excepted"))  # fmt: skip
    r.append(row(m, "IC", "short", "non_hedge", "2015-07-09", "settlement", "change", "30", "% of contract value", "关于调整中证500股指期货交易保证金的通知", "2015-07-08", C + "jystz/20150708/19147.html", "VERIFIED_PRIMARY", "sell positions 20% -> 30%; hedging excepted"))  # fmt: skip
    steps = [("2015-08-26", "12"), ("2015-08-27", "15"), ("2015-08-28", "20")]
    for eff, v in steps:
        t = "关于调整沪深300、上证50、中证500股指期货非套期保值持仓交易保证金的通知"
        r.append(row(m, "IC", "long", "non_hedge", eff, "settlement", "change", v, "% of contract value", t, "2015-08-25", C + "jystz/20150825/19247.html", "VERIFIED_PRIMARY", "IC buy positions only; IC sell positions already 30%"))  # fmt: skip
        r.append(row(m, "IF|IH", "both", "non_hedge", eff, "settlement", "change", v, "% of contract value", t, "2015-08-25", C + "jystz/20150825/19247.html", "VERIFIED_PRIMARY", "other products of the same notice"))  # fmt: skip
    t = "关于调整沪深300、上证50、中证500股指期货非套期保值持仓交易保证金的通知"
    r.append(row(m, "IC", "long", "non_hedge", "2015-08-31", "settlement", "change", "30", "% of contract value", t, "2015-08-28", C + "jystz/20150828/19259.html", "VERIFIED_PRIMARY", "IC buy positions 20% -> 30%"))  # fmt: skip
    r.append(row(m, "IF|IH", "both", "non_hedge", "2015-08-31", "settlement", "change", "30", "% of contract value", t, "2015-08-28", C + "jystz/20150828/19259.html", "VERIFIED_PRIMARY", "other products of the same notice"))  # fmt: skip
    for hc, v in [("non_hedge", "40"), ("hedge", "20")]:
        r.append(row(m, "IC", "both", hc, "2015-09-07", "settlement", "change", v, "% of contract value", t_mar, "2015-09-02", C + "jystz/20150902/19270.html", "VERIFIED_PRIMARY"))  # fmt: skip
        r.append(row(m, "IF|IH", "both", hc, "2015-09-07", "settlement", "change", v, "% of contract value", t_mar, "2015-09-02", C + "jystz/20150902/19270.html", "VERIFIED_PRIMARY", "other products of the same notice"))  # fmt: skip
    r.append(row(m, "IC", "both", "non_hedge", "2017-02-17", "settlement", "change", "30", "% of contract value", t_mar, "2017-02-16", C + "jystz/20170216/20197.html", "VERIFIED_PRIMARY", "40% -> 30%; hedge stays 20%"))  # fmt: skip
    r.append(row(m, "IF|IH", "both", "non_hedge", "2017-02-17", "settlement", "change", "20", "% of contract value", t_mar, "2017-02-16", C + "jystz/20170216/20197.html", "VERIFIED_PRIMARY", "other products of the same notice"))  # fmt: skip
    r.append(row(m, "IF|IH", "both", "all", "2017-09-18", "settlement", "change", "15", "% of contract value", "关于调整沪深300、上证50股指期货交易保证金的通知", "2017-09-15", C + "jystz/20170915/20368.html", "VERIFIED_PRIMARY", "IF/IH only: IC unchanged by this notice"))  # fmt: skip
    r.append(row(m, "IC", "both", "all", "2018-12-03", "settlement", "change", "15", "% of contract value", t_mar, "2018-12-02", C + "jystz/20181202/23408.html", "VERIFIED_PRIMARY", "unified across hedge classes"))  # fmt: skip
    r.append(row(m, "IF|IH", "both", "all", "2018-12-03", "settlement", "change", "10", "% of contract value", t_mar, "2018-12-02", C + "jystz/20181202/23408.html", "VERIFIED_PRIMARY", "other products of the same notice"))  # fmt: skip
    r.append(row(m, "IC", "both", "all", "2019-04-22", "settlement", "change", "12", "% of contract value", "关于调整中证500股指期货交易保证金的通知", "2019-04-19", C + "jystz/20190419/23720.html", "VERIFIED_PRIMARY", "no later CFFEX notice changing IC margin found; vendor margin_ratio 0.12-0.15 unreconciled"))  # fmt: skip
    r.append(row("margin_cross_product_rule", "IF|IH|IC", "both", "all", "2019-06-03", "settlement", "change", "charged on the larger side only", "rule", "关于股指期货跨品种双向持仓按照交易保证金单边较大者收取交易保证金的通知", "2019-05-31", C + "jystz/20190531/23762.html", "VERIFIED_PRIMARY"))  # fmt: skip
    r.append(row("min_margin_pct", "IC", "both", "all", "2026-10-16", "snapshot", "snapshot", "8", "% of contract value", "中证500股指期货合约表 (current)", "2026-10-16", "http://www.cffex.com.cn/zz500/", "VERIFIED_PRIMARY_SNAPSHOT", "contract-table MINIMUM only; the exchange margin standard currently in force was not located"))  # fmt: skip
    # ---- order size, price limit, circuit breaker
    for p, v in [("max_order_lots_limit", "20"), ("max_order_lots_market", "10")]:
        r.append(row(p, "IF|IH|IC", "both", "all", "2017-04-05", "trading_day", "change", v, "lots per order", "关于调整股指期货、国债期货合约交易指令每次最大下单数量的通知", "2017-03-31", C + "jystz/20170331/20247.html", "VERIFIED_PRIMARY", "earlier values not located"))  # fmt: skip
    r.append(row("price_limit_pct", "IF|IH|IC", "both", "all", "2016-01-08", "trading_day", "change", "10", "+- % of previous settlement", "关于暂停实施股指期货熔断制度的通知", "2016-01-07", C + "jystz/20160107/19584.html", "VERIFIED_PRIMARY", "was +-7%"))  # fmt: skip
    r.append(row("index_futures_circuit_breaker", "IF|IH|IC", "both", "all", "2016-01-08", "trading_day", "change", "suspended", "rule", "关于暂停实施股指期货熔断制度的通知", "2016-01-07", C + "jystz/20160107/19584.html", "VERIFIED_PRIMARY"))  # fmt: skip
    # ---- daily opening limits (non-hedge): numeric history only in member-only notices -> PRESS_REPORTED
    t_over = "关于调整日内过度交易行为监管标准的通知 (member-only; dates listed in CFFEX's abolished-rules directory)"
    for eff, v, unit, src, note in [
        ("2015-08-25", "600", "lots per product per day", NBD18, "retrospective of the 2015 measures"),
        ("2015-08-28", "100", "lots per product per day", NBD18, "retrospective of the 2015 measures"),
        ("2015-09-07", "10", "lots per product per day", NBD18, "announced 2015-09-02; also in " + YICAI),
        ("2017-02-17", "20", "lots per product per day", NBD18, "quotes the 2017-02-16 CFFEX announcement"),
        ("2018-12-03", "50", "lots per contract per day", YICAI, "was 20 per product; also " + NBD18),
        ("2019-04-22", "500", "lots per contract per day", NBD19, "quotes the CFFEX announcement of 2019-04-19; the 500-lot limit therefore dates from 2019-04-22"),
    ]:  # fmt: skip
        r.append(row("open_limit_lots", "IF|IH|IC", "both", "non_hedge", eff, "trading_day", "change", v, unit, t_over, ANNOUNCED[eff], src, "PRESS_REPORTED", note))  # fmt: skip
    for eff, nd, ntitle, nid in [("2022-07-22", "2022-07-18", "中金所发〔2022〕39号 关于股指期货、股指期权合约交易限额的通知", "20220718/28853"),
                                 ("2022-12-19", "2022-12-14", "中金所发〔2022〕73号 关于股指期货和期权合约交易限额的通知", "20221214/30917")]:  # fmt: skip
        r.append(row("open_limit_lots", "IF|IH|IC|IM", "both", "non_hedge", eff, "trading_day", "restatement", "500", "lots per contract per day", ntitle, nd, C + f"jystz/{nid}.html", "VERIFIED_PRIMARY", "first public notice text; restates the 2019 value; hedging exempt"))  # fmt: skip
    # ---- contract specification (current page; launch-date constancy not checked)
    spec = "http://www.cffex.com.cn/zz500/"
    for p, v, u in [("tick_points", "0.2", "index points"), ("multiplier_yuan_per_point", "200", "yuan per point"),
                    ("last_trading_day_rule", "third Friday of the contract month; a holiday defers to the next trading day", "rule"),
                    ("trading_hours", "09:30-11:30,13:00-15:00", "local time")]:  # fmt: skip
        r.append(row(p, "IC", "both", "all", "2026-10-16", "snapshot", "snapshot", v, u, "中证500股指期货合约表 (current)", "2026-10-16", spec, "VERIFIED_PRIMARY_SNAPSHOT", "current contract table; unchanged-since-launch (2015-04-16) not checked against the 2015 text"))  # fmt: skip
    r.append(row("trading_hours", "IF|IH|IC", "both", "all", "2016-01-01", "trading_day", "change", "N/A", "local time", "关于修订《中国金融期货交易所交易规则》及相关实施细则的通知", "2015-12-04", C + "jystz/20151204/19371.html", "NOT_EXTRACTED", "revised rules take effect 2016-01-01; the hours clause is in the attachments and was not extracted", binding="N/A"))  # fmt: skip
    r.append(row("abnormal_trading_measures", "IF|IH|IC", "both", "all", "2019-06-03", "trading_day", "change", "N/A", "rule", "关于发布《中国金融期货交易所异常交易管理办法》...的通知", "2019-05-31", C + "jystz/20190531/23768.html", "NOT_EXTRACTED", "supersedes the 2015 standards; numeric text is in the attachments and was not extracted", binding="N/A"))  # fmt: skip
    # ---- assumptions the cost model needs (no notice supplies them)
    r.append(row("broker_addon_bp", "IC", "both", "all", "2016-10-17", "assumed_window_start", "assumption", "1", "bp of turnover per side, on top of the exchange fee", "no source: broker commission is not an exchange notice", "2016-10-17", "N/A", "ASSUMPTION", "frozen at 1 bp/side by the owner (2026-10-16); NOT a verified quote - the actual rate from 盈安 replaces it BEFORE freeze, never after"))  # fmt: skip
    r.append(row("broker_order_fee_addon_yuan", "IC", "both", "all", "2016-10-17", "assumed_window_start", "assumption", "0", "yuan per order", "no source", "2016-10-17", "N/A", "ASSUMPTION", "exchange order fee only"))  # fmt: skip
    r.append(row("slippage_ticks", "IC", "both", "all", "2016-10-17", "assumed_window_start", "assumption", "1", "ticks per side (tick = 0.2 points)", "SPEC v0.1 section 5", "2026-10-16", "N/A", "ASSUMPTION", "model assumption, not an observation"))  # fmt: skip
    r.append(row("stress_run_cost_multiplier", "IC", "both", "all", "2016-10-17", "assumed_window_start", "assumption", "2", "x (applied to broker_addon_bp and slippage_ticks only)", "SPEC A1 section 5", "2026-10-16", "N/A", "ASSUMPTION", "required stress run: broker add-on 2 bp/side and slippage 2 ticks; exchange and order fees stay as the notices say"))  # fmt: skip
    return sorted(
        r,
        key=lambda x: (
            x["parameter"],
            x["products"],
            x["side"],
            x["hedge_class"],
            x["effective_from"],
        ),
    )


def write(path: Path) -> list[dict]:
    rows = build()
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    n = len(write(Path(ap.parse_args().out)))
    print(f"{n} rows written")
