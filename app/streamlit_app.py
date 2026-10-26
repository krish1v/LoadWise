"""LoadWise prototype UI (Streamlit) — strength & conditioning console.

Thin presentation layer only; all computation lives in the reusable ``loadwise``
package (data layer) and ``loadwise.forecast`` (Option B prediction bridge).

The app auto-loads the bundled example dataset on startup. The demo story runs
left to right across the tabs: what came in (Overview) -> next week's training
load (Forecast) -> the daily history behind it (Daily) -> the data-quality
rigor (Validation).

Run:  streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loadwise import Config, process_workbook  # noqa: E402
from loadwise.config import Thresholds  # noqa: E402
from loadwise.dates import rollover_preview  # noqa: E402
from loadwise.ingest import IngestError, SheetStructureError  # noqa: E402
from loadwise.pipeline import SeasonYearRequired, apply_override  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO_WORKBOOK = os.path.join(REPO_ROOT, "Data Set Georgia Tech_anonymized.xlsx")
DEFAULT_SEASON_YEAR = 2025

st.set_page_config(page_title="LoadWise", page_icon="🏀", layout="wide",
                   initial_sidebar_state="expanded")

# Detect the Streamlit fit-to-container kwarg (renamed use_container_width->width).
import inspect as _inspect  # noqa: E402
try:
    _STRETCH = ({"width": "stretch"} if "width" in _inspect.signature(st.dataframe).parameters
                else {"use_container_width": True})
except (ValueError, TypeError):
    _STRETCH = {"use_container_width": True}


# --------------------------------------------------------------------------- #
# Design system
# --------------------------------------------------------------------------- #
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600;700&family=Barlow+Semi+Condensed:wght@500;600;700&display=swap');

:root {
  --ink:#0F1A2B; --ink-soft:#38465E; --muted:#6A7589;
  --line:#E4E8F0; --mist:#F2F4F8; --paper:#FFFFFF;
  --court:#E0531C; --court-soft:#FBE7DC; --lane:#1C9A68; --flag:#C7821A;
}

html, body, [class*="css"], .stMarkdown, p, span, div, label, input, button {
  font-family: 'Barlow', system-ui, sans-serif;
}
.block-container { padding-top: 2rem; padding-bottom: 3.5rem; max-width: 1360px; }

/* Strip Streamlit's fixed top chrome so it never overlaps the hero */
header[data-testid="stHeader"] { background: transparent; height: 0; }
[data-testid="stDecoration"] { display: none; }
[data-testid="stToolbar"] { right: .4rem; top: .2rem; }

h1, h2, h3, h4 { font-family: 'Barlow Semi Condensed', sans-serif; color: var(--ink); letter-spacing: -.01em; }

/* ---- Hero ---- */
.hero { padding: 2px 0 16px; margin-bottom: 20px; border-bottom: 2px solid var(--ink);
  display: flex; justify-content: space-between; align-items: flex-end; flex-wrap: wrap; gap: 16px; }
.hero-left { display: flex; align-items: center; gap: 15px; min-width: 300px; }
.hero-badge { width: 46px; height: 46px; border-radius: 13px; flex: none;
  background: var(--court); color: #fff; display: flex; align-items: center; justify-content: center;
  font-size: 1.5rem; box-shadow: 0 4px 12px rgba(224,83,28,.32); }
.hero-name { font-family: 'Barlow Semi Condensed'; font-weight: 700; font-size: 2.15rem;
  line-height: .98; color: var(--ink); }
.hero-lede { font-size: .98rem; color: var(--ink-soft); font-weight: 500; margin-top: 3px; max-width: 64ch; }
.hero-chips { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; padding-bottom: 3px; }
.chip { display: inline-flex; align-items: center; gap: 6px; background: var(--mist);
  border: 1px solid var(--line); color: var(--ink-soft); border-radius: 8px;
  padding: 5px 11px; font-size: .78rem; font-weight: 600; }
.chip.ok { background: #e9f8f1; border-color: #bfe8d4; color: #167a50; }
.chip.warn { background: #fcf3e2; border-color: #f0d9a3; color: #a66e16; }

/* ---- Section heading: sentence case + court tick (no all-caps eyebrow) ---- */
.lw-section { font-family: 'Barlow Semi Condensed'; font-size: 1.12rem; font-weight: 600;
  color: var(--ink); margin: 22px 0 9px; display: flex; align-items: center; gap: 9px; }
.lw-section::before { content: ""; width: 9px; height: 18px; border-radius: 3px;
  background: var(--court); flex: none; }

/* ---- Stat tiles: border-led, no uniform drop shadow ---- */
.lw-metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(146px, 1fr));
  gap: 12px; margin: 4px 0 18px; }
.lw-card { background: var(--paper); border: 1px solid var(--line); border-radius: 12px;
  padding: 13px 16px 15px; }
.lw-card .k { color: var(--muted); font-size: .82rem; font-weight: 600; }
.lw-card .v { font-family: 'Barlow Semi Condensed'; color: var(--ink); font-size: 2rem;
  font-weight: 700; line-height: 1.1; margin-top: 3px; font-variant-numeric: tabular-nums; }
.lw-card .s { color: var(--muted); font-size: .76rem; font-weight: 500; margin-top: 1px; }
.lw-card.accent { border-top: 3px solid var(--court); }
.lw-card.warn  { border-top: 3px solid var(--flag); }
.lw-card.good  { border-top: 3px solid var(--lane); }

/* ---- Forecast scoreboard ---- */
.score-card { background: var(--ink); color: #fff; border-radius: 16px; padding: 22px 26px;
  display: flex; flex-direction: column; justify-content: center; }
.score-num { font-family: 'Barlow Semi Condensed'; font-weight: 700; font-size: 4.6rem;
  line-height: .9; color: #fff; font-variant-numeric: tabular-nums; }
.score-num .unit { font-size: 1.2rem; color: var(--court); font-weight: 600; margin-left: 8px; }
.score-lab { font-size: .95rem; color: #c3cde0; font-weight: 600; margin-top: 6px; }
.score-sub { font-size: .82rem; color: #8a98b5; margin-top: 2px; }

.bars { display: flex; flex-direction: column; gap: 7px; margin-top: 4px; }
.bar-row { display: grid; grid-template-columns: 34px 1fr 52px 44px; align-items: center; gap: 10px; }
.bar-lab { font-family: 'Barlow Semi Condensed'; font-weight: 600; color: var(--ink-soft); font-size: .9rem; }
.bar-track { background: var(--mist); border-radius: 6px; height: 20px; overflow: hidden; border: 1px solid var(--line); }
.bar-fill { height: 100%; background: linear-gradient(90deg, var(--court), #f1793f); border-radius: 6px 0 0 6px; }
.bar-val { font-family: 'Barlow Semi Condensed'; font-weight: 700; color: var(--ink);
  text-align: right; font-variant-numeric: tabular-nums; }
.bar-min { color: var(--muted); font-size: .8rem; text-align: right; }

/* ---- Callout ---- */
.lw-scope { background: var(--mist); border: 1px solid var(--line); border-left: 4px solid var(--court);
  border-radius: 10px; padding: 12px 15px; font-size: .86rem; color: var(--ink-soft);
  margin-bottom: 12px; line-height: 1.5; }

/* ---- Tabs ---- */
.stTabs [data-baseweb="tab-list"] { gap: 2px; border-bottom: 1px solid var(--line); }
.stTabs [data-baseweb="tab"] { font-family: 'Barlow Semi Condensed'; font-weight: 600;
  font-size: 1.02rem; padding: 9px 18px; color: var(--muted); }
.stTabs [aria-selected="true"] { color: var(--ink); border-bottom: 2.5px solid var(--court); }

[data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 11px; overflow: hidden; }
section[data-testid="stSidebar"] { background: var(--mist); border-right: 1px solid var(--line); }
section[data-testid="stSidebar"] h3 { font-family: 'Barlow Semi Condensed'; font-weight: 600; }
.stButton button, .stDownloadButton button { border-radius: 9px; font-weight: 600; }
.stDownloadButton button { border: 1px solid var(--court); color: var(--court); }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def _fmt_int(n):
    return f"{n:,}" if isinstance(n, int) else n


def metric_cards(cards):
    """cards: list of (label, value, sub, variant)."""
    html = ['<div class="lw-metrics">']
    for label, value, sub, variant in cards:
        cls = f"lw-card {variant}" if variant else "lw-card"
        html.append(f'<div class="{cls}"><div class="k">{label}</div>'
                    f'<div class="v">{_fmt_int(value)}</div><div class="s">{sub or ""}</div></div>')
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Data loading (auto-runs; reprocesses only when source/settings change)
# --------------------------------------------------------------------------- #
def _signature(source_kind, label, year, thresholds):
    return (source_kind, label, year, tuple(sorted(thresholds.to_dict().items())))


def ensure_processed(source, source_kind, label, config):
    """Process into session_state once per unique (source, settings) signature."""
    sig = _signature(source_kind, label, config.season_start_year, config.thresholds)
    if st.session_state.get("signature") == sig and st.session_state.get("result") is not None:
        return st.session_state["result"], None
    try:
        res = process_workbook(source, config, file_label=label,
                               generated_at=_dt.datetime.now().isoformat(timespec="seconds"))
        st.session_state["result"] = res
        st.session_state["signature"] = sig
        return res, None
    except (SeasonYearRequired, SheetStructureError, IngestError) as e:
        st.session_state["result"] = None
        return None, str(e)


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
def sidebar():
    with st.sidebar:
        st.markdown("### Data source")
        demo_ok = os.path.exists(DEMO_WORKBOOK)
        mode = st.radio("Workbook", ["Example dataset", "Upload .xlsx"],
                        index=0, label_visibility="collapsed")
        source = source_kind = label = None
        if mode == "Example dataset":
            if demo_ok:
                source, source_kind, label = DEMO_WORKBOOK, "demo", os.path.basename(DEMO_WORKBOOK)
                st.caption(f"📄 {label}")
            else:
                st.error("Example workbook not found in the project root.")
        else:
            up = st.file_uploader("Upload a Full-Day .xlsx", type=["xlsx"])
            if up is not None:
                source, source_kind, label = up.getvalue(), f"upload:{up.name}:{len(up.getvalue())}", up.name
                st.caption(f"📄 {label}")
            else:
                st.info("Choose an .xlsx file, or switch to the example dataset.")

        st.markdown("### Season")
        year = st.number_input("Season start year", min_value=2000, max_value=2100,
                               value=DEFAULT_SEASON_YEAR, step=1,
                               help="The year the September records belong to. January rolls over "
                                    "to the next year. LoadWise never guesses this.")

        t = Thresholds()
        with st.expander("Screening thresholds"):
            t.max_duration_min = st.number_input("Max session duration (min)", value=float(t.max_duration_min))
            t.min_duration_min = st.number_input("Min session duration (min)", value=float(t.min_duration_min))
            t.hr_max_bpm = st.number_input("Max HR (bpm)", value=float(t.hr_max_bpm))
            t.hr_min_bpm = st.number_input("Min HR (bpm)", value=float(t.hr_min_bpm))
            t.hit_tolerance_min = st.number_input("HIT > duration tolerance (min)", value=float(t.hit_tolerance_min))

        st.markdown("<div class='lw-scope'>Data layer owns ingestion, validation and daily "
                    "aggregation. The Forecast tab connects the Option B prediction model. "
                    "Source ACWR/ATL/CTL are preserved as reported, not recalculated.</div>",
                    unsafe_allow_html=True)
        return source, source_kind, label, Config(season_start_year=int(year), thresholds=t)


# --------------------------------------------------------------------------- #
# Hero
# --------------------------------------------------------------------------- #
def hero(res, label):
    chips = [f'<span class="chip">📄 {label}</span>']
    if res is not None:
        s = res.output["summary"]
        rng = s["date_range"]
        if rng["first"]:
            chips.append(f'<span class="chip">{rng["first"]} → {rng["last"]}</span>')
        chips.append(f'<span class="chip">{s["athletes"]} athletes</span>')
        errs = s["flag_severity_counts"]["error"]
        chips.append(f'<span class="chip {"warn" if errs else "ok"}">'
                     f'{"Ready" if not errs else f"{errs} errors"}</span>')
    st.markdown(
        '<div class="hero"><div class="hero-left"><div class="hero-badge">🏀</div>'
        '<div><div class="hero-name">LoadWise</div>'
        '<div class="hero-lede">Clean a season of Firstbeat workload exports into a daily '
        'training history, then forecast each athlete&rsquo;s next seven days of training load.</div>'
        '</div></div>'
        f'<div class="hero-chips">{"".join(chips)}</div></div>',
        unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Tab: Overview & import
# --------------------------------------------------------------------------- #
def tab_overview(res, config):
    s = res.output["summary"]
    metric_cards([
        ("Records in", s["full_day_records"], "measurement rows", "accent"),
        ("Athletes", s["athletes"], "anonymized", None),
        ("Daily records", s["daily_records"], "athlete-days built", None),
        ("Dates", s["resolved_dates"], f'{s["date_range"]["first"]} → {s["date_range"]["last"]}', None),
        ("Warnings", s["flag_severity_counts"]["warning"], "flagged for review", "warn"),
        ("Errors", s["flag_severity_counts"]["error"], "blocking", "good" if not s["flag_severity_counts"]["error"] else "warn"),
    ])
    st.markdown("<div class='lw-scope'>Every record keeps its source row, dates resolve against "
                "the configured season year, and duplicates are caught before aggregation. Head to "
                "<b>Forecast</b> for next week&rsquo;s predicted training load.</div>",
                unsafe_allow_html=True)

    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown("<div class='lw-section'>Year rollover</div>", unsafe_allow_html=True)
        st.caption("Day/month dates carry no year. Sep–Dec stay in the season start year; "
                   "Jan–Aug roll to the next.")
        rp = pd.DataFrame(rollover_preview(config))[["month_name", "year", "in_start_year"]]
        rp.columns = ["Month", "Year", "In start year"]
        st.dataframe(rp, hide_index=True, **_STRETCH, height=250)
    with c2:
        st.markdown("<div class='lw-section'>Detected sheets</div>", unsafe_allow_html=True)
        meta = res.output["importMetadata"]
        raw = {"Full Day": res.raw_full_day, "Wellness": res.raw_wellness}
        for key, info in (("full_day_sheet", meta["full_day_sheet"]),
                          ("wellness_sheet", meta["wellness_sheet"])):
            status = "present" if info.get("present", True) else "missing"
            st.markdown(f"**{info['name']}** — {status}, header row "
                        f"`{info['header_row']}`, {info['detected_records']} records")
            recs = raw.get(info["name"]) or []
            if recs:
                hdrs = list(recs[0].cells.keys())
                more = f" … (+{len(hdrs)-10} more)" if len(hdrs) > 10 else ""
                st.caption(", ".join(hdrs[:10]) + more)
            if info.get("note"):
                st.info(info["note"])

    di = res.output["configuration"].get("day_index_issues") or []
    if di:
        st.markdown("<div class='lw-section'>Date / study-day conflicts</div>", unsafe_allow_html=True)
        st.warning(f"{len(di)} record(s) where the resolved date disagrees with the study-day "
                   "index. These are flagged, never silently re-assigned.")
        st.dataframe(pd.DataFrame(di), hide_index=True, **_STRETCH)


# --------------------------------------------------------------------------- #
# Tab: Forecast (Option B prediction layer) — the showcase
# --------------------------------------------------------------------------- #
def _observed_median_rate(res, athlete_id):
    """LoadWise's own observed median training TRIMP/min (independent of the model)."""
    rates = []
    for d in res.daily_records:
        if d["athlete_id"] != athlete_id:
            continue
        tr = d["breakdown"]["training"]
        trimp, dur = tr["trimp"], tr["duration_min"]
        if (trimp["value"] and dur["value"] and dur["value"] > 0
                and trimp["completeness"] == "complete" and dur["completeness"] == "complete"):
            rates.append(trimp["value"] / dur["value"])
    if not rates:
        return None
    rates.sort()
    n = len(rates)
    return rates[n // 2] if n % 2 else (rates[n // 2 - 1] + rates[n // 2]) / 2


def _bars_html(days):
    mx = max((d["predicted_trimp"] for d in days), default=1) or 1
    rows = []
    for d in days:
        pct = max(2, int(round(100 * d["predicted_trimp"] / mx))) if d["predicted_trimp"] else 0
        rows.append(
            f'<div class="bar-row"><div class="bar-lab">D{d["day_index"]}</div>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{pct}%"></div></div>'
            f'<div class="bar-val">{d["predicted_trimp"]:.0f}</div>'
            f'<div class="bar-min">{d["planned_minutes"]:.0f}′</div></div>')
    return '<div class="bars">' + "".join(rows) + "</div>"


def tab_forecast(res):
    try:
        from loadwise.forecast import Forecaster, ForecastUnavailable
        fc = Forecaster()
    except Exception as e:  # ForecastUnavailable or import error
        st.error(f"Forecast layer unavailable: {e}")
        st.caption("The trained model lives in `forecast/loadwise_model.joblib`; "
                   "install `scikit-learn joblib` if missing.")
        return

    st.markdown(
        "<div class='lw-scope'>Enter the minutes you plan to monitor for an athlete over the next "
        "week. One athlete-aware Ridge regression turns their own training history into a predicted "
        "<b>training TRIMP</b> per day. It does not predict games, injury, readiness or high-speed "
        "running — and it feeds the optimizer&rsquo;s expected-baseline-workload input.</div>",
        unsafe_allow_html=True)

    athletes = sorted({(d["athlete_id"], d["athlete_label"]) for d in res.daily_records})
    if not athletes:
        st.warning("No athletes in the processed dataset to forecast.")
        return

    left, right = st.columns([1, 1.15], gap="large")
    with left:
        st.markdown("<div class='lw-section'>Plan the week</div>", unsafe_allow_html=True)
        sel = st.selectbox("Athlete", athletes,
                           format_func=lambda a: f"{a[1]}" + ("" if fc.is_known(a[1]) else "  (new athlete)"))
        aid, alabel = sel
        if not fc.is_known(alabel):
            st.warning(f"{alabel} wasn't in model training — using the global fallback rate "
                       f"({fc.global_rate:.3f} TRIMP/min). Treat this forecast with caution.")
        st.caption("Planned monitored minutes per day (0 = rest).")
        default_minutes = [90, 90, 75, 0, 90, 60, 0]
        minutes, mcols = [], st.columns(7)
        for i, col in enumerate(mcols):
            minutes.append(col.number_input(f"D{i+1}", min_value=0, max_value=300,
                                            value=default_minutes[i], step=5, key=f"fc_min_{i}"))

    forecast = fc.forecast(alabel, minutes)
    observed = _observed_median_rate(res, aid)

    with right:
        st.markdown("<div class='lw-section'>Next seven days</div>", unsafe_allow_html=True)
        st.markdown(
            f'<div class="score-card"><div class="score-num">{forecast["horizon_total_trimp"]:.0f}'
            f'<span class="unit">TRIMP</span></div>'
            f'<div class="score-lab">predicted training load · 7-day total</div>'
            f'<div class="score-sub">{alabel} · model rate {forecast["model_trimp_per_min"]:.3f} TRIMP/min'
            + (f' · LoadWise history {observed:.3f}' if observed else "") + '</div></div>',
            unsafe_allow_html=True)
        st.markdown(_bars_html(forecast["days"]), unsafe_allow_html=True)

    st.markdown("<div class='lw-section'>How good is the prediction?</div>", unsafe_allow_html=True)
    r = fc.results
    reg, ah, pooled = r.get("regression", {}), r.get("athlete_history", {}), r.get("pooled_history", {})
    metric_cards([
        ("Ridge model MAE", reg.get("mae", "—"), "TRIMP · held-out", "accent"),
        ("Athlete-history MAE", ah.get("mae", "—"), "baseline", None),
        ("Pooled-history MAE", pooled.get("mae", "—"), "baseline", None),
        ("Tested on", r.get("test_n", "—"), f'later sessions · {r.get("train_n","?")} trained', None),
    ])
    ev1, ev2 = st.columns([1.1, 1], gap="large")
    with ev1:
        charts = os.path.join(REPO_ROOT, "forecast", "validation_charts.png")
        if os.path.exists(charts):
            st.image(charts, caption="Held-out predictions and out-of-sample error", **_STRETCH)
        st.caption(f'Lower MAE is better. The model underpredicts by ~{abs(reg.get("bias", 0)):.1f} '
                   "TRIMP on average, so treat forecasts as expectations, not ceilings.")
    with ev2:
        gd = forecast["comparable_day_rates"]
        st.caption("Historical intensity by game-relative day (context only — test records had no "
                   "game-day labels, so this is not a validated predictor).")
        if gd:
            st.dataframe(pd.DataFrame([{"Game-day": k, "Hist. TRIMP/min": round(v, 3)}
                                       for k, v in sorted(gd.items())]),
                         hide_index=True, **_STRETCH, height=300)
        else:
            st.caption("No comparable-day history for this athlete.")

    st.markdown("<div class='lw-section'>Hand-off to the optimizer</div>", unsafe_allow_html=True)
    export = fc.baseline_export(alabel, minutes, start_date=None)
    st.caption("A standardized expected-baseline-workload object — the contract this prediction "
               "layer passes to the optimization layer.")
    st.download_button("⬇ Baseline workload JSON", data=json.dumps(export, indent=2),
                       file_name=f"loadwise_baseline_{aid}.json", mime="application/json")


# --------------------------------------------------------------------------- #
# Tab: Daily dataset
# --------------------------------------------------------------------------- #
def _r(v, n=2):
    return None if v is None else round(v, n)


def _daily_df(daily):
    rows = []
    for d in daily:
        t = d["totals"]
        rows.append({
            "⚠": "⚠" if d["completeness"]["any_partial"] else "",
            "Athlete": d["athlete_id"], "Date": d["date"], "Sessions": d["included_session_count"],
            "Duration (min)": _r(t["duration_min"]["value"]),
            "TRIMP": _r(t["trimp"]["value"]), "Movement Load": _r(t["movement_load"]["value"]),
            "HI min": _r(t["high_intensity_min"]["value"]),
            "Train TRIMP": _r(d["breakdown"]["training"]["trimp"]["value"]),
            "Game TRIMP": _r(d["breakdown"]["game"]["trimp"]["value"]),
            "Efficiency": _r(d["derived"]["efficiency_calculated"]["value"], 3),
            "TRIMP/min": _r(d["derived"]["trimp_per_min_calculated"]["value"], 3),
            "Game": "●" if d["schedule_context"]["has_game"] else "",
            "GD": "|".join(d["schedule_context"]["gd_labels"]),
            "Wellness": len(d["wellness_observations"]), "Flags": len(d["quality_flag_ids"]),
        })
    return pd.DataFrame(rows)


def tab_daily(res):
    daily = res.daily_records
    if not daily:
        st.warning("No daily records (no records had a usable athlete + date).")
        return
    athletes = sorted({d["athlete_id"] for d in daily})
    labels = {d["athlete_id"]: d["athlete_label"] for d in daily}
    all_dates = sorted({d["date"] for d in daily})
    dmin, dmax = _dt.date.fromisoformat(all_dates[0]), _dt.date.fromisoformat(all_dates[-1])

    c1, c2, c3 = st.columns([2, 1, 1])
    chosen = c1.multiselect("Athletes", athletes, format_func=lambda a: f"{a} · {labels.get(a,'')}")
    start = c2.date_input("From", dmin, min_value=dmin, max_value=dmax)
    end = c3.date_input("To", dmax, min_value=dmin, max_value=dmax)
    filt = [d for d in daily if (not chosen or d["athlete_id"] in chosen)
            and start.isoformat() <= d["date"] <= end.isoformat()]

    partial = sum(1 for d in filt if d["completeness"]["any_partial"])
    metric_cards([
        ("Daily records", len(filt), "in view", "accent"),
        ("Athletes", len({d["athlete_id"] for d in filt}), "", None),
        ("Multi-session days", sum(1 for d in filt if d["included_session_count"] > 1), "", None),
        ("Partial totals", partial, "incomplete", "warn" if partial else "good"),
    ])
    st.caption("⚠ marks days with a partial total (a metric missing on some sessions). "
               "Game-only days often have no Movement Load in the source.")
    st.dataframe(_daily_df(filt), hide_index=True, **_STRETCH, height=400,
                 column_config={"⚠": st.column_config.TextColumn("⚠", width="small"),
                                "Game": st.column_config.TextColumn("Game", width="small")})

    st.markdown("<div class='lw-section'>Drill into a day</div>", unsafe_allow_html=True)
    if filt:
        sel = st.selectbox("Daily record", [d["daily_id"] for d in filt], label_visibility="collapsed")
        d = next(x for x in filt if x["daily_id"] == sel)
        st.write(f"**{d['athlete_label']}** · {d['date']} · {d['included_session_count']} session(s) "
                 f"· study-day {d['day_index']}")
        dd1, dd2 = st.columns(2)
        with dd1:
            st.caption("Totals & completeness")
            st.json(d["totals"], expanded=False)
            st.caption("Derived (calculated independently of the source)")
            st.json(d["derived"], expanded=False)
        with dd2:
            st.caption("Contributing source records")
            sess = [r for r in res.cleaned_records if r["record_id"] in d["source_record_ids"]]
            st.dataframe(pd.DataFrame([{
                "record_id": r["record_id"], "excel_row": r["provenance"]["excel_row"],
                "type": r["measurement_type"], "start": r["start_time"], "end": r["end_time"],
                "TRIMP": _r(r["normalized"]["trimp"]), "ML": _r(r["normalized"]["movement_load"]),
                "dur_min": _r(r["normalized"]["duration_min"]),
            } for r in sess]), hide_index=True, **_STRETCH)
            if d["wellness_observations"]:
                st.caption("Same-day wellness (scale/direction unknown)")
                st.json(d["wellness_observations"], expanded=False)
            st.caption("Schedule context (observed, not a full schedule)")
            st.json(d["schedule_context"], expanded=False)

    st.markdown("<div class='lw-section'>Export</div>", unsafe_allow_html=True)
    e1, e2, e3 = st.columns([1.3, 1, 1])
    include_raw = e1.checkbox("Include raw per-cell records in JSON (large)", value=False)
    e2.download_button("⬇ JSON output", data=res.to_json(include_raw=include_raw),
                       file_name="loadwise_output.json", mime="application/json", **_STRETCH)
    e3.download_button("⬇ Daily CSV", data=res.to_daily_csv(),
                       file_name="loadwise_daily.csv", mime="text/csv", **_STRETCH)


# --------------------------------------------------------------------------- #
# Tab: Validation
# --------------------------------------------------------------------------- #
def _flag_code(res, fid):
    return next((f["rule_code"] for f in res.quality_flags if f["flag_id"] == fid), None)


def tab_validation(res):
    s = res.output["summary"]
    metric_cards([
        ("Records", s["full_day_records"], "", "accent"),
        ("Errors", s["flag_severity_counts"]["error"], "", "good" if not s["flag_severity_counts"]["error"] else "warn"),
        ("Warnings", s["flag_severity_counts"]["warning"], "", "warn"),
        ("Info", s["flag_severity_counts"]["info"], "", None),
        ("Excluded duplicates", s["excluded_duplicates"], "", None),
        ("Partial daily", s["partial_daily_records"], "incomplete totals", None),
    ])

    st.markdown("<div class='lw-section'>Quality flags</div>", unsafe_allow_html=True)
    flags = res.quality_flags
    if not flags:
        st.success("No quality flags raised.")
    else:
        fdf = pd.DataFrame(flags)
        c1, c2 = st.columns(2)
        sev = c1.multiselect("Severity", sorted(fdf["severity"].unique()),
                             default=list(sorted(fdf["severity"].unique())))
        codes = c2.multiselect("Rule code", sorted(fdf["rule_code"].unique()))
        view = fdf[fdf["severity"].isin(sev)]
        if codes:
            view = view[view["rule_code"].isin(codes)]
        st.caption(f"Showing {len(view):,} of {len(fdf):,} flags")
        st.dataframe(
            view[["rule_code", "severity", "record_id", "field", "excel_row",
                  "original_value", "explanation", "effect"]],
            hide_index=True, **_STRETCH, height=330,
            column_config={
                "rule_code": st.column_config.TextColumn("Rule", width="medium"),
                "severity": st.column_config.TextColumn("Sev.", width="small"),
                "excel_row": st.column_config.NumberColumn("Row", width="small"),
                "explanation": st.column_config.TextColumn("Explanation", width="large"),
                "effect": st.column_config.TextColumn("Effect on aggregation", width="large"),
            })

    st.markdown("<div class='lw-section'>Inspect a record — source vs normalized</div>", unsafe_allow_html=True)
    rec_ids = [r["record_id"] for r in res.cleaned_records]
    sel = st.selectbox("Record", rec_ids, label_visibility="collapsed")
    rec = next(r for r in res.cleaned_records if r["record_id"] == sel)
    ic1, ic2 = st.columns(2)
    with ic1:
        st.caption("Normalized")
        st.json({"athlete_id": rec["athlete_id"], "date_resolved": rec["date_resolved"],
                 "measurement_type": rec["measurement_type"], "status": rec["status"],
                 **rec["normalized"]}, expanded=False)
    with ic2:
        st.caption("Source (raw, preserved)")
        st.json({"date_raw": str(rec["date_raw"]), "provenance": rec["provenance"],
                 **rec["source"]}, expanded=False)

    st.markdown("<div class='lw-section'>Duplicate review — include / exclude</div>", unsafe_allow_html=True)
    dup = [r for r in res.cleaned_records
           if r["status"] == "excluded" or r["duplicate_of"]
           or any(_flag_code(res, f) == "POSSIBLE_DUPLICATE_OVERLAP" for f in r["flags"])]
    if not dup:
        st.caption("No duplicate candidates to review in this workbook.")
    else:
        for r in dup:
            with st.container(border=True):
                a, b, c = st.columns([3, 2, 2])
                a.write(f"**{r['record_id']}** · {r['athlete_label']} · {r['date_resolved']} · "
                        f"{r['measurement_type']} · `{r['status']}`"
                        + (f" · dup of {r['duplicate_of']}" if r["duplicate_of"] else ""))
                reason = b.text_input("Reason", key=f"reason_{r['record_id']}",
                                      label_visibility="collapsed", placeholder="reason for override")
                action = c.radio("Action", ["include", "exclude"],
                                 index=0 if r["status"] == "included" else 1,
                                 horizontal=True, key=f"act_{r['record_id']}")
                if c.button("Apply", key=f"apply_{r['record_id']}"):
                    apply_override(res, r["record_id"], action, reason=reason)
                    st.rerun()


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    source, source_kind, label, config = sidebar()
    if source is None:
        hero(None, label or "no workbook selected")
        st.info("Select the example dataset or upload a workbook in the sidebar to begin.")
        return

    res, err = ensure_processed(source, source_kind, label, config)
    hero(res, label)
    if err:
        st.error(err)
        return

    t_over, t_fc, t_daily, t_val = st.tabs(
        ["Overview", "Forecast", "Daily dataset", "Validation"])
    with t_over:
        tab_overview(res, config)
    with t_fc:
        tab_forecast(res)
    with t_daily:
        tab_daily(res)
    with t_val:
        tab_validation(res)


main()
