"""LoadWise HTTP API (FastAPI). Thin layer over the `loadwise` library and its SQLite store.

Run:  uvicorn api.main:app --reload      (serves the built React app from web/dist too)
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import threading
from collections import defaultdict
from typing import Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from loadwise import Config, LoadWiseInputError, SeasonYearRequired, preview_workbook
from loadwise.pipeline import ProcessResult, build, ingest_all, now_iso, preview_ingest
from loadwise.store import Store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO_PATH = os.path.join(ROOT, "Data Set Georgia Tech_anonymized.xlsx")
DEMO_YEAR = 2025          # the season year chosen for the supplied workbook (2025–26 season)
DIST = os.path.join(ROOT, "web", "dist")
METRICS = ("trimp", "movement_load", "hit_min", "duration_min")


class OverrideIn(BaseModel):
    record_id: str
    action: str
    reason: str


class EvaluateIn(BaseModel):
    config: dict
    days: List[dict]


class FeedbackIn(BaseModel):
    config: dict
    proposal: dict
    decision: str
    rating: Optional[int] = None
    comment: Optional[str] = None
    modified: Optional[dict] = None     # {"days": [{day, kind, team, extra}, ...]}


class State:
    """Holds the store plus a cached ProcessResult, rebuilt only when inputs change."""

    def __init__(self, db_path: str):
        self.store = Store(db_path)
        self.lock = threading.Lock()
        self._ingests: Dict[str, object] = {}
        self._result: Optional[ProcessResult] = None
        self._generated_at: Optional[str] = None

    def invalidate(self):
        self._result = None

    def result(self) -> Optional[ProcessResult]:
        with self.lock:
            if self._result is not None:
                return self._result
            sources = self.store.sources()
            if not sources:
                return None
            ingests = []
            for name, data in sources:
                sha = hashlib.sha256(data).hexdigest()
                if sha not in self._ingests:
                    self._ingests[sha] = ingest_all((name, data))[0]
                ingests.append(self._ingests[sha])
            cfg = Config(season_start_year=self.store.season_start_year())
            self._generated_at = now_iso()
            self._result = build(ingests, cfg, self.store.overrides(), generated_at=self._generated_at)
            return self._result


def _err(e: Exception, status: int = 422):
    code = "season_year_required" if isinstance(e, SeasonYearRequired) else "input_error"
    return JSONResponse(status_code=status, content={"detail": str(e), "code": code})


# ---------------------------------------------------------------- shaping --

def slim_daily(d: dict) -> dict:
    row = {
        "daily_id": d["daily_id"], "athlete_id": d["athlete_id"], "athlete_label": d["athlete_label"],
        "date": d["date"], "study_day_index": d["study_day_index"], "session_count": d["session_count"],
        "sessions_by_type": d["session_counts_by_type"],
        "efficiency": d["derived"]["efficiency"]["value"],
        "efficiency_reason": d["derived"]["efficiency"]["reason"],
        "trimp_per_min": d["derived"]["trimp_per_min"]["value"],
        "trimp_per_min_reason": d["derived"]["trimp_per_min"]["reason"],
        "gd_labels": d["schedule"]["gd_labels"], "gd_conflict": d["schedule"]["gd_conflict"],
        "has_game": d["schedule"]["has_game_session"], "wellness_count": len(d["wellness"]),
        "flag_counts": d["quality"]["flag_counts"], "excluded_count": len(d["excluded_record_ids"]),
    }
    for m in METRICS:
        row[m] = d["totals"][m]
        row[f"training_{m}"] = d["breakdown"]["training"][m]["value"]
        row[f"game_{m}"] = d["breakdown"]["game"][m]["value"]
        row[f"other_{m}"] = d["breakdown"]["other"][m]["value"]
    return row


def _window(daily: List[dict], end: dt.date, days: int, metric: str) -> dict:
    start = end - dt.timedelta(days=days - 1)
    rows = [d for d in daily if start <= dt.date.fromisoformat(d["date"]) <= end]
    vals = [d["totals"][metric] for d in rows]
    known = [v["value"] for v in vals if v["value"] is not None]
    return {"value": sum(known) if known else None, "observed_days": len(rows),
            "incomplete_days": sum(v["completeness"] != "complete" for v in vals)}


def squad_overview(res: ProcessResult, ref_date: Optional[str] = None) -> dict:
    daily = res.daily_records
    if not daily:
        return {"reference_date": None, "athletes": []}
    last = max(d["date"] for d in daily)
    ref = dt.date.fromisoformat(min(ref_date, last) if ref_date else last)
    by_a: Dict[str, List[dict]] = defaultdict(list)
    for d in daily:
        by_a[d["athlete_id"]].append(d)
    flag_by_rec = defaultdict(lambda: {"error": 0, "warning": 0, "info": 0})
    for f in res.quality_flags:
        if f["record_id"]:
            flag_by_rec[f["record_id"]][f["severity"]] += 1
    rec_athlete = {r["record_id"]: r["athlete_id"] for r in res.cleaned_records}
    flags_by_a = defaultdict(lambda: {"error": 0, "warning": 0, "info": 0})
    for rid, c in flag_by_rec.items():
        aid = rec_athlete.get(rid)
        if aid:
            for k, v in c.items():
                flags_by_a[aid][k] += v
    spark_start = ref - dt.timedelta(days=27)
    out = []
    for a in res.output["athletes"]:
        ds = by_a.get(a["athlete_id"], [])
        spark = {d["date"]: d["totals"]["trimp"]["value"] for d in ds
                 if dt.date.fromisoformat(d["date"]) >= spark_start}
        out.append({
            "athlete_id": a["athlete_id"], "label": a["label"],
            "first_date": a["history"]["first_date"], "last_date": a["history"]["last_date"],
            "observed_days": a["history"]["observed_days"],
            "sessions": sum(d["session_count"] for d in ds),
            "games": sum(d["session_counts_by_type"]["game"] for d in ds),
            "last7": {m: _window(ds, ref, 7, m) for m in METRICS},
            "last28": {m: _window(ds, ref, 28, m) for m in METRICS},
            "sparkline": [{"date": (spark_start + dt.timedelta(days=i)).isoformat(),
                           "trimp": spark.get((spark_start + dt.timedelta(days=i)).isoformat())}
                          for i in range(28)],
            "flags": flags_by_a[a["athlete_id"]],
            "incomplete_days": sum(bool(d["quality"]["incomplete_metrics"]) for d in ds),
        })
    return {"reference_date": ref.isoformat(), "last_date": last, "first_date": min(d["date"] for d in daily),
            "window_note": "Sums over the last 7/28 calendar days ending on the latest date in the data. "
                           "Display only; not ACWR. Days without data are not counted as zero load.",
            "athletes": out}


# -------------------------------------------------------------------- app --

def create_app(db_path: Optional[str] = None, autoload_demo: Optional[bool] = None) -> FastAPI:
    """autoload_demo: import the bundled demo workbook when the store is empty at startup
    (default on; set LOADWISE_AUTOLOAD_DEMO=0 to disable)."""
    db_path = db_path or os.environ.get("LOADWISE_DB", os.path.join(ROOT, "data", "loadwise.db"))
    if autoload_demo is None:
        autoload_demo = os.environ.get("LOADWISE_AUTOLOAD_DEMO", "1") != "0"
    state = State(db_path)
    if autoload_demo and not state.store.imports() and os.path.exists(DEMO_PATH):
        with open(DEMO_PATH, "rb") as fh:
            state.store.add_import(os.path.basename(DEMO_PATH), fh.read(), DEMO_YEAR)
    app = FastAPI(title="LoadWise API", version="1.0.0")
    app.state.lw = state
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["*"], allow_headers=["*"])

    def need() -> ProcessResult:
        try:
            res = state.result()
        except LoadWiseInputError as e:
            raise HTTPException(422, str(e))
        if res is None:
            raise HTTPException(404, "No data imported yet. Upload a workbook or load the demo.")
        return res

    # -- import ----------------------------------------------------------
    @app.get("/api/status")
    def status():
        imps = state.store.imports()
        res = state.result() if imps else None
        return {"imports": imps, "season_start_year": state.store.season_start_year(),
                "summary": res.output["summary"] if res else None,
                "generated_at": res.generated_at if res else None,
                "demo_available": os.path.exists(DEMO_PATH), "demo_season_year": DEMO_YEAR}

    @app.post("/api/preview")
    async def preview(file: UploadFile = File(...), season_start_year: Optional[int] = Form(None)):
        data = await file.read()
        try:
            return preview_workbook((file.filename or "upload.xlsx", data),
                                    Config(season_start_year=season_start_year))
        except LoadWiseInputError as e:
            return _err(e)

    @app.get("/api/preview/demo")
    def preview_demo(season_start_year: Optional[int] = None):
        with open(DEMO_PATH, "rb") as fh:
            return preview_workbook((os.path.basename(DEMO_PATH), fh.read()),
                                    Config(season_start_year=season_start_year))

    def _import(name: str, data: bytes, year: Optional[int]):
        # Validate fully before storing so a bad file never enters the history.
        try:
            ing = ingest_all((name, data))[0]
            prev = preview_ingest(ing, Config(season_start_year=year))
            if prev["needs_season_year"]:
                raise SeasonYearRequired([s["raw"] for s in prev["date_samples"]])
            status_, sha = state.store.add_import(name, data, year)
            state._ingests.setdefault(sha, ing)
        except LoadWiseInputError as e:
            return _err(e)
        state.invalidate()
        res = state.result()
        return {"status": status_, "sha256": sha, "summary": res.output["summary"]}

    @app.post("/api/imports")
    async def import_file(file: UploadFile = File(...), season_start_year: Optional[int] = Form(None)):
        return _import(file.filename or "upload.xlsx", await file.read(), season_start_year)

    @app.post("/api/imports/demo")
    def import_demo(season_start_year: int = DEMO_YEAR):
        with open(DEMO_PATH, "rb") as fh:
            return _import(os.path.basename(DEMO_PATH), fh.read(), season_start_year)

    @app.delete("/api/imports/{sha256}")
    def remove_import(sha256: str):
        state.store.remove_import(sha256)
        state.invalidate()
        return {"ok": True}

    @app.delete("/api/store")
    def reset():
        state.store.reset()
        state.invalidate()
        return {"ok": True}

    # -- data ------------------------------------------------------------
    @app.get("/api/summary")
    def summary(ref: Optional[str] = None):
        res = need()
        try:
            if ref:
                dt.date.fromisoformat(ref)
        except ValueError:
            raise HTTPException(400, "ref must be a date (YYYY-MM-DD)")
        return {"summary": res.output["summary"], "squad": squad_overview(res, ref),
                "schedule": res.output["scheduleContext"]}

    @app.get("/api/athletes")
    def athletes():
        return need().output["athletes"]

    @app.get("/api/daily")
    def daily(athlete: Optional[str] = None, date_from: Optional[str] = None,
              date_to: Optional[str] = None):
        rows = [d for d in need().daily_records
                if (not athlete or d["athlete_id"] == athlete)
                and (not date_from or d["date"] >= date_from) and (not date_to or d["date"] <= date_to)]
        return [slim_daily(d) for d in rows]

    @app.get("/api/daily/{athlete_id}/{date}")
    def daily_detail(athlete_id: str, date: str):
        res = need()
        d = next((x for x in res.daily_records if x["athlete_id"] == athlete_id and x["date"] == date), None)
        if d is None:
            raise HTTPException(404, "No sessions recorded for this athlete on this date (unobserved, "
                                     "not a confirmed rest day).")
        ids = d["source_record_ids"] + d["excluded_record_ids"]
        recs = {r["record_id"]: r for r in res.cleaned_records if r["record_id"] in ids}
        raw = {r["record_id"]: r for r in res.output["rawRecords"] if r["record_id"] in ids}
        flags = [f for f in res.quality_flags if f["record_id"] in ids]
        return {"daily": d, "sessions": [{**recs[i], "raw": raw.get(i)} for i in ids], "flags": flags}

    @app.get("/api/calendar")
    def calendar(metric: str = "trimp"):
        if metric not in METRICS:
            raise HTTPException(400, f"metric must be one of {', '.join(METRICS)}")
        res = need()
        sched = res.output["scheduleContext"]["observed_range"]
        if not sched["first"]:
            return {"dates": [], "athletes": []}
        start, end = dt.date.fromisoformat(sched["first"]), dt.date.fromisoformat(sched["last"])
        dates = [(start + dt.timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]
        idx = {(d["athlete_id"], d["date"]): d for d in res.daily_records}
        rows = []
        for a in res.output["athletes"]:
            cells = []
            for date in dates:
                d = idx.get((a["athlete_id"], date))
                cells.append(None if d is None else {
                    "value": d["totals"][metric]["value"], "completeness": d["totals"][metric]["completeness"],
                    "has_game": d["schedule"]["has_game_session"], "sessions": d["session_count"]})
            rows.append({"athlete_id": a["athlete_id"], "label": a["label"], "cells": cells})
        return {"metric": metric, "dates": dates, "athletes": rows,
                "gd_labels_by_date": res.output["scheduleContext"]["gd_labels_by_date"]}

    @app.get("/api/flags")
    def flags(severity: Optional[str] = None, rule: Optional[str] = None, athlete: Optional[str] = None):
        res = need()
        recs = {r["record_id"]: r for r in res.cleaned_records + res.output["wellnessRecords"]}
        out = []
        for f in res.quality_flags:
            r = recs.get(f["record_id"]) if f["record_id"] else None
            if severity and f["severity"] != severity:
                continue
            if rule and f["rule_code"] != rule:
                continue
            if athlete and (r is None or r["athlete_id"] != athlete):
                continue
            out.append({**f, "athlete_id": r["athlete_id"] if r else None,
                        "athlete_label": r["athlete_label"] if r else None, "date": r["date"] if r else None})
        return out

    @app.get("/api/records/{record_id:path}")
    def record(record_id: str):
        res = need()
        rec = next((r for r in res.cleaned_records + res.output["wellnessRecords"]
                    if r["record_id"] == record_id), None)
        if rec is None:
            raise HTTPException(404, "Unknown record")
        raw = next((r for r in res.output["rawRecords"] if r["record_id"] == record_id), None)
        return {"record": rec, "raw": raw,
                "flags": [f for f in res.quality_flags if f["record_id"] == record_id]}

    @app.get("/api/review")
    def review():
        """Duplicate review queue: exact copies, possible duplicates and manual decisions."""
        res = need()
        items = []
        for r in res.cleaned_records:
            kind = ("exact_duplicate" if r["duplicate_of"] else
                    "possible_duplicate" if r.get("possible_duplicate_of") else
                    "manual_override" if r["override"] else None)
            if kind:
                items.append({"kind": kind, "record_id": r["record_id"], "athlete_id": r["athlete_id"],
                              "athlete_label": r["athlete_label"], "date": r["date"],
                              "excel_row": r["provenance"]["excel_row"], "file": r["provenance"]["file"],
                              "measurement_type": r["measurement_type"], "start_time": r["start_time"],
                              "end_time": r["end_time"], "metrics": r["metrics"], "status": r["status"],
                              "status_reason": r["status_reason"], "override": r["override"],
                              "related": [r["duplicate_of"]] if r["duplicate_of"]
                              else r.get("possible_duplicate_of", [])})
        return items

    @app.post("/api/overrides")
    def set_override(body: OverrideIn):
        res = need()
        if not any(r["record_id"] == body.record_id for r in res.cleaned_records):
            raise HTTPException(404, "Unknown record")
        try:
            state.store.set_override(body.record_id, body.action, body.reason)
        except LoadWiseInputError as e:
            return _err(e)
        state.invalidate()
        res = need()
        rec = next(r for r in res.cleaned_records if r["record_id"] == body.record_id)
        day = next((d for d in res.daily_records
                    if d["athlete_id"] == rec["athlete_id"] and d["date"] == rec["date"]), None)
        return {"record": rec, "daily": slim_daily(day) if day else None}

    @app.delete("/api/overrides/{record_id:path}")
    def clear_override(record_id: str):
        state.store.clear_override(record_id)
        state.invalidate()
        return {"ok": True}

    # -- export ----------------------------------------------------------
    @app.get("/api/export.json")
    def export_json(include_raw: bool = True):
        return Response(need().to_json(include_raw=include_raw), media_type="application/json",
                        headers={"Content-Disposition": "attachment; filename=loadwise_output.json"})

    @app.get("/api/export.csv")
    def export_csv():
        return Response(need().to_daily_csv(), media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=loadwise_daily.csv"})

    # -- training planner (modelling team's models, see planner/) ---------
    plan_lock = threading.Lock()

    def planning():
        from planner import PlanningContext
        res = need()
        cached = getattr(state, "planning", None)
        if cached is None or cached[0] is not res:
            state.planning = (res, PlanningContext(res.daily_records))
        return res, state.planning[1]

    def plan_label(res, athlete_id: str) -> str:
        a = next((a for a in res.output["athletes"] if a["athlete_id"] == athlete_id), None)
        if a is None:
            raise HTTPException(404, "Unknown athlete")
        return a["label"]

    @app.get("/api/plan/meta")
    def plan_meta():
        from planner import FITTING_PERIOD, REFERENCE_DEMO, SCHEDULE
        from planner.features import day_date, day_number
        res, ctx = planning()
        counts = ctx.daily.groupby("athlete_id").agg(training_days=("day", "size"),
                                                      measured_mip_days=("mip1", "count"))
        roster = []
        for a in res.output["athletes"]:
            if a["label"] in counts.index:
                c = counts.loc[a["label"]]
                roster.append({"athlete_id": a["athlete_id"], "label": a["label"],
                               "training_days": int(c.training_days),
                               "measured_mip_days": int(c.measured_mip_days),
                               "last_date": a["history"]["last_date"]})
        demo = None
        demo_id = next((r["athlete_id"] for r in roster if r["label"] == REFERENCE_DEMO["athlete"]), None)
        if demo_id and ctx.first_day <= day_number(REFERENCE_DEMO["start"]) <= ctx.last_day:
            demo = {**REFERENCE_DEMO, "athlete": demo_id}
        return {
            "roster": roster,
            "first_start": day_date(ctx.first_day) if ctx.first_day else None,
            "last_start": day_date(ctx.last_day) if ctx.last_day else None,
            "schedule": SCHEDULE,
            "fitting_period": FITTING_PERIOD,
            "demo": demo,
            "scope": "Predicts next-day training outcomes (MIP 1min, Movement Load, TRIMP) from the "
                     "athlete's history and planned recording duration, then picks training minutes "
                     "within coach-set workload limits. Training days only: games and rest are not "
                     "modelled. Not an injury, readiness or safety prediction.",
        }

    @app.get("/api/plan/history")
    def plan_history(athlete: str, start: str):
        from planner import jsonable
        from planner.features import day_date
        from planner.scenarios import in_fitting_period, week_dates
        res, ctx = planning()
        label = plan_label(res, athlete)
        try:
            day = ctx.start_day(start)
            planning_inputs, reason, past, history = ctx.defaults(label, day)
        except ValueError as e:
            raise HTTPException(400, str(e))
        cols = ["date", "mip1", "movement_load", "training_trimp", "recorded_duration_min"]
        return jsonable({
            "athlete_id": athlete, "label": label, "start": day_date(day),
            "week_dates": week_dates(day),
            "planning": planning_inputs, "reason": reason, "personalized": reason is None,
            "in_fitting_period": in_fitting_period(day),
            "features": history,
            "history": past[cols].astype(object).where(past[cols].notna(), None).to_dict("records"),
        })

    @app.post("/api/plan/optimize")
    def plan_optimize(config: dict):
        from planner import jsonable, recommend
        res, ctx = planning()
        if not isinstance(config.get("athlete"), str):
            raise HTTPException(400, "Select an athlete.")
        config = {**config, "athlete": plan_label(res, config["athlete"])}
        if not plan_lock.acquire(blocking=False):
            raise HTTPException(409, "An optimization is already running. Try again when it finishes.")
        try:
            result = recommend(ctx, config)
        except ValueError as e:
            raise HTTPException(400, str(e))
        finally:
            plan_lock.release()
        result.pop("csv", None)
        return jsonable(result)

    # -- coach feedback on a proposed plan (stored for later evaluation; models unchanged) --
    def evaluate_days(config: dict, days: list) -> dict:
        from planner import jsonable
        from planner.evaluate import evaluate_plan
        res, ctx = planning()
        if not isinstance(config.get("athlete"), str):
            raise HTTPException(400, "Select an athlete.")
        config = {**config, "athlete": plan_label(res, config["athlete"])}
        try:
            return jsonable(evaluate_plan(ctx, config, days))
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.post("/api/plan/evaluate")
    def plan_evaluate(body: EvaluateIn):
        return evaluate_days(body.config, body.days)

    @app.post("/api/plan/feedback")
    def plan_feedback_create(body: FeedbackIn):
        res = need()
        athlete = body.config.get("athlete")
        if not isinstance(athlete, str):
            raise HTTPException(400, "Select an athlete.")
        label = plan_label(res, athlete)
        start = body.proposal.get("start") or body.config.get("start")
        modified = None
        if body.decision == "modified":
            days = (body.modified or {}).get("days")
            if not days:
                raise HTTPException(400, "A modified plan needs the edited days.")
            # Store predictions computed here, not whatever the browser sent.
            modified = {"days": days, "evaluation": evaluate_days(body.config, days)}
        elif body.modified is not None:
            raise HTTPException(400, "Only a modified plan carries edited days.")
        try:
            return state.store.add_feedback(
                athlete_id=athlete, athlete_label=label, start=str(start), decision=body.decision,
                rating=body.rating, comment=body.comment, config=body.config,
                proposal=body.proposal, modified=modified)
        except LoadWiseInputError as e:
            return _err(e)

    @app.get("/api/plan/feedback")
    def plan_feedback_list(athlete: Optional[str] = None):
        return state.store.feedback(athlete)

    @app.get("/api/plan/feedback/{feedback_id}")
    def plan_feedback_get(feedback_id: int):
        rec = state.store.feedback_record(feedback_id)
        if rec is None:
            raise HTTPException(404, "No saved feedback with that id.")
        return rec

    @app.get("/api/plan/models")
    def plan_models():
        from planner import model_evidence
        return model_evidence()

    # -- static frontend -------------------------------------------------
    if os.path.isdir(DIST):
        app.mount("/assets", StaticFiles(directory=os.path.join(DIST, "assets")), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str, request: Request):
            if path.startswith("api/"):
                raise HTTPException(404)
            f = os.path.join(DIST, path)
            if path and os.path.isfile(f):
                return FileResponse(f)
            return FileResponse(os.path.join(DIST, "index.html"))

    return app


app = create_app() if os.environ.get("LOADWISE_NO_DEFAULT_APP") != "1" else None
