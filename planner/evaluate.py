"""Predict outcomes for a week a coach has edited by hand.

Used by the coach feedback flow ("Modify"): the coach sets each day's activity and minutes,
and this reuses the existing models to predict those exact days. Nothing is optimised or
refitted. Limits are reported as warnings, because the coach has the final say.
"""
import copy

from .features import day_date
from .predict import TARGETS, evaluate
from .scenarios import FITTING_DATA, week_dates

KINDS = ('training', 'game', 'rest')


def _whole(value):
    """Whole numbers may arrive as 90 or 90.0 (JSON); anything else is None."""
    if type(value) is int or (type(value) is float and value.is_integer()):
        return int(value)
    return None


def _minutes(value, name):
    value = _whole(value)
    if value is None or not 0 <= value <= 1440:
        raise ValueError(f'{name} must be whole minutes between 0 and 1440.')
    return value


def evaluate_plan(context, config, days):
    """-> dict(plan=[PlanDay...], weekly_ml, weekly_trimp, warnings=[...], ...)."""
    checked = copy.deepcopy(config)
    context.validate_week(checked)              # the proposal's own inputs must be valid
    start, athlete, planning = checked['start'], checked['athlete'], checked['planning']
    overrides = checked.get('overrides', {})

    if not isinstance(days, list) or len(days) != 7:
        raise ValueError('Provide all seven days of the plan.')
    by_day = {}
    for d in days:
        day = _whole(d.get('day')) if isinstance(d, dict) else None
        if day not in range(1, 8) or d.get('kind') not in KINDS:
            raise ValueError('Each day needs a day number (1-7) and an activity (training, game or rest).')
        by_day[day] = d
    if len(by_day) != 7:
        raise ValueError('Each of the seven days must appear once.')

    _, history, reason = context.athlete_state(athlete, start)
    if reason and checked.get('allow_pooled') is not True:
        raise ValueError(reason + ' Confirm the pooled scenario to continue.')
    model_athlete = None if reason else athlete

    dates = week_dates(start)
    rows, warnings = [], []
    ml_buffers = trimp_buffers = 0.0
    for day in range(1, 8):
        d, inputs = by_day[day], {**planning, **overrides.get(str(day), {})}
        row = dict(day=day, date=dates[day - 1], kind=d['kind'], team=0, extra=0, duration=None,
                   mip1=None, movement_load=None, training_trimp=None, spline=None, supported=None)
        if d['kind'] == 'training':
            team = _minutes(d.get('team'), f'Day {day}: team minutes')
            extra = _minutes(d.get('extra'), f'Day {day}: individual minutes')
            duration = team + extra + inputs['other_recorded']
            if duration > 1440:
                raise ValueError(f'Day {day}: recording duration exceeds 1440 minutes.')
            row.update(team=team, extra=extra, duration=duration)
            pred = evaluate(history, [duration], FITTING_DATA, model_athlete)
            row['supported'] = not pred.empty
            if pred.empty:
                warnings.append(dict(day=day, code='unsupported',
                                     message=f'Day {day}: {duration} min is outside the durations the model was trained on, so it has no prediction.'))
            else:
                p = pred.iloc[0]
                row.update({t: float(p[t]) for t in TARGETS}, spline=float(p['spline']))
                ml_buffers += inputs['ml_buffer']
                trimp_buffers += inputs['trimp_buffer']
                if row['movement_load'] + inputs['ml_buffer'] > inputs['ml_limit']:
                    warnings.append(dict(day=day, code='daily_ml',
                                         message=f'Day {day}: predicted Movement Load is above the daily limit.'))
                if row['training_trimp'] + inputs['trimp_buffer'] > inputs['trimp_limit']:
                    warnings.append(dict(day=day, code='daily_trimp',
                                         message=f'Day {day}: predicted TRIMP is above the daily limit.'))
        rows.append(row)

    predicted = [r for r in rows if r['mip1'] is not None]
    weekly_ml = sum(r['movement_load'] for r in predicted)
    weekly_trimp = sum(r['training_trimp'] for r in predicted)
    ml_margin = planning['weekly_ml_limit'] - weekly_ml - ml_buffers
    trimp_margin = planning['weekly_trimp_limit'] - weekly_trimp - trimp_buffers
    if ml_margin < 0:
        warnings.append(dict(day=None, code='weekly_ml', message='Predicted weekly Movement Load is above the weekly limit.'))
    if trimp_margin < 0:
        warnings.append(dict(day=None, code='weekly_trimp', message='Predicted weekly TRIMP is above the weekly limit.'))
    last = rows[-1]
    return dict(start=day_date(start), plan=rows, weekly_ml=weekly_ml, weekly_trimp=weekly_trimp,
                ml_margin=ml_margin, trimp_margin=trimp_margin,
                day7_mip=last['mip1'], mip_sum=sum(r['mip1'] for r in predicted),
                pooled=bool(reason), warnings=warnings)
