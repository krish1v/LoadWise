"""Turn the selected training scenarios into a seven-day plan report.

Adapted from SamuelO12/createx-loadwise, prototype/recommendation/recommend.py (commit e5ec641).
`recommend` takes the PlanningContext and adds calendar dates; the summary is unchanged.
"""
import pandas as pd
from .optimize import optimize_week
from .features import day_date
from .scenarios import week_dates


def summarize(plan, schedule, planning):
    rows = []
    for day, kind in enumerate(schedule, 1):
        if kind == 'training':
            row = plan[plan.day == day].iloc[0].to_dict()
            row['duration'] = row.pop('actual_duration_min')
            rows.append(dict(row, kind=kind))
        else:
            rows.append(dict(day=day, kind=kind, team=0, extra=0, duration=None,
                             mip1=None, movement_load=None, training_trimp=None, spline=None))
    weekly_movement_load = float(plan.movement_load.sum())
    weekly_trimp = float(plan.training_trimp.sum())
    terminal = plan[plan.day == 7]
    return dict(plan=rows, weekly_ml=weekly_movement_load, weekly_trimp=weekly_trimp,
                ml_margin=float(planning['weekly_ml_limit'] - weekly_movement_load - plan.ml_buffer.sum()),
                trimp_margin=float(planning['weekly_trimp_limit'] - weekly_trimp - plan.trimp_buffer.sum()),
                day7_mip=float(terminal.mip1.iloc[0]) if len(terminal) else None,
                mip_sum=float(plan.mip1.sum()))


def recommend(context, config):
    primary_plan, alternative_plan, original_plan, reason = optimize_week(context, config)
    result = summarize(primary_plan, config['schedule'], config['planning'])
    result.update(athlete=config['athlete'], start=config['start'], pooled=bool(reason),
                  objective=config['objective'], original=original_plan,
                  alternative=None if alternative_plan is None else summarize(alternative_plan, config['schedule'], config['planning']),
                  explanation=('Maximize predicted Day 7 MIP. Ties favor higher total training-day MIP, then smaller changes to the original plan.' if config['objective'] == 'terminal' else 'Maximize total predicted training-day MIP. Ties favor smaller changes to the original plan.'),
                  limitation='History stays fixed throughout the week. Recording duration includes other monitored time. Predicted workload is not a safety guarantee. Game and rest exposure is not modeled.')
    dates = week_dates(config['start'])
    for row in result['plan'] + result['original'] + (result['alternative'] or {}).get('plan', []):
        row['date'] = dates[int(row['day']) - 1]
    result['start'] = day_date(config['start'])
    result['reason'] = reason or None
    result['csv'] = pd.DataFrame(result['plan']).to_csv(index=False)
    return result
