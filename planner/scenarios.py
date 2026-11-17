"""Athlete state, coaching inputs and daily candidate scenarios.

Adapted from SamuelO12/createx-loadwise, prototype/optimization/scenarios.py (commit e5ec641).
Changes from the original:
- The module-level globals (DAILY, GAME_DAYS, ROSTER, FIRST_DAY, LAST_DAY) built from the
  team's CSV files are replaced by a PlanningContext built from LoadWise daily records.
- The fitting reference (what the models were trained on) is loaded from the artifacts.
- Planning days are calendar-date ordinals. The start can be any day from the athlete's
  second observed day up to the day after the last observed day.
- The Player 01 demonstration is offered as `REFERENCE_DEMO` instead of being hidden
  inside `defaults`.
The candidate, validation and prediction logic is unchanged.
"""
import datetime as dt

import numpy as np
import pandas as pd

from .features import day_date, day_number, history_features, training_days
from .predict import ARTIFACTS, DURATION, evaluate, supported_durations

FITTING_DATA = pd.read_csv(ARTIFACTS / 'fitting_reference.csv')
# Study days 1-95 of the Bamberg workbook (2025-09-11 to 2025-12-14) were used to fit the models.
FITTING_PERIOD = {'first_date': '2025-09-11', 'last_date': '2025-12-14'}
SCHEDULE = ['training', 'training', 'training', 'game', 'training', 'rest', 'training']
DEMO = dict(original_team=100, original_extra=20, other_recorded=20,
            team_min=90, team_max=110, extra_min=0, extra_max=60,
            ml_limit=380, trimp_limit=170, ml_buffer=0, trimp_buffer=0,
            weekly_ml_limit=1700, weekly_trimp_limit=730)
REFERENCE_DEMO = dict(athlete='Player 01', start='2025-12-16', planning=DEMO, schedule=SCHEDULE,
                      step=5, objective='terminal', allow_pooled=False, overrides={})
MINUTE_FIELDS = ['original_team', 'original_extra', 'other_recorded',
                 'team_min', 'team_max', 'extra_min', 'extra_max']
DAILY_LIMITS = ['ml_limit', 'trimp_limit', 'ml_buffer', 'trimp_buffer']
WEEKLY_LIMITS = ['weekly_ml_limit', 'weekly_trimp_limit']


class PlanningContext:
    """The observed training history the planner works from."""

    def __init__(self, daily_records):
        self.daily, self.game_days = training_days(daily_records)
        self.roster = sorted(self.daily.athlete_id.unique())
        self.first_day = int(self.daily.day.min()) + 1 if len(self.daily) else None
        self.last_day = int(self.daily.day.max()) + 1 if len(self.daily) else None

    def start_day(self, start):
        """Accept an ISO date (or a day ordinal) and check it is a valid planning start."""
        try:
            day = day_number(start) if isinstance(start, str) else start
        except ValueError:
            raise ValueError('Planning start must be a date (YYYY-MM-DD).') from None
        if type(day) is not int or self.first_day is None or not self.first_day <= day <= self.last_day:
            raise ValueError(f'Select a planning start between {day_date(self.first_day)} and '
                             f'{day_date(self.last_day)}.' if self.first_day else 'No training data is loaded.')
        return day

    def athlete_state(self, athlete, start_day):
        if athlete not in self.roster:
            raise ValueError('Select a roster athlete.')
        past = self.daily[(self.daily.athlete_id == athlete) & (self.daily.day < start_day)].sort_values('day')
        measured = past.dropna(subset=['mip1'])
        reason = None
        if len(measured) < 3:
            reason = 'Fewer than three prior measured MIP days.'
        elif start_day - measured.day.iloc[-1] > 28:
            reason = 'No measured MIP in the previous 28 days.'
        elif not supported_durations(FITTING_DATA, athlete, np.arange(1, 1441)).any():
            reason = 'No supported individual recording duration (athlete not in the model training data).'
        history = None
        if reason is None:
            records = past.astype(object).where(past.notna(), None).to_dict('records')
            history = history_features(records, self.game_days, athlete, start_day)
        return past, history, reason

    def defaults(self, athlete, start_day):
        past, history, reason = self.athlete_state(athlete, start_day)
        reference_data = FITTING_DATA if reason else FITTING_DATA[FITTING_DATA.athlete_id == athlete]
        durations = np.arange(1, 1441)
        supported = durations[supported_durations(FITTING_DATA, None if reason else athlete, durations)]
        reference = reference_data[DURATION].median() if reason else history['last_recorded_duration_min']
        if reference is None or pd.isna(reference):
            reference = reference_data[DURATION].median()
        reference_minutes = int(supported[np.abs(supported - round(reference)).argmin()])
        team_minutes = min(90, reference_minutes)
        maximum_duration = int(supported.max())
        planning = dict(original_team=team_minutes, original_extra=reference_minutes - team_minutes,
                        other_recorded=0, team_min=0, team_max=min(120, maximum_duration),
                        extra_min=0, extra_max=maximum_duration, ml_buffer=0, trimp_buffer=0,
                        ml_limit=round(float(reference_data.target_movement_load.quantile(.9)), 2),
                        trimp_limit=round(float(reference_data.target_training_trimp.quantile(.9)), 2),
                        weekly_ml_limit=round(5 * float(reference_data.target_movement_load.quantile(.75)), 2),
                        weekly_trimp_limit=round(5 * float(reference_data.target_training_trimp.quantile(.75)), 2))
        return planning, reason, past, history

    def validate_week(self, config):
        if not isinstance(config, dict):
            raise ValueError('Provide a planning object.')
        required = {'athlete', 'start', 'planning', 'schedule', 'step', 'objective'}
        if not required <= config.keys():
            raise ValueError('Planning inputs are incomplete. Reset inputs and try again.')
        if not isinstance(config['athlete'], str) or config['athlete'] not in self.roster:
            raise ValueError('Select a roster athlete.')
        config['start'] = self.start_day(config['start'])
        planning = config['planning']
        fields = set(MINUTE_FIELDS + DAILY_LIMITS + WEEKLY_LIMITS)
        if not isinstance(planning, dict) or set(planning) != fields:
            raise ValueError('Planning inputs are incomplete or contain unknown fields.')
        for name in fields:
            validate_number(planning[name], name, name in MINUTE_FIELDS)
        schedule = config['schedule']
        if not isinstance(schedule, list) or len(schedule) != 7 or any(kind not in ['training', 'game', 'rest'] for kind in schedule):
            raise ValueError('Provide seven training, game or rest days.')
        if type(config['step']) is not int or config['step'] not in [1, 5, 10]:
            raise ValueError('Select a candidate resolution of 1, 5 or 10 minutes.')
        if config['objective'] not in ['terminal', 'cumulative']:
            raise ValueError('Select a valid planning objective.')
        if 'training' not in schedule:
            raise ValueError('Select at least one training day.')
        if config['objective'] == 'terminal' and schedule[-1] != 'training':
            raise ValueError('The Day 7 objective requires Day 7 to be training.')
        if type(config.get('allow_pooled', False)) is not bool:
            raise ValueError('Pooled model acknowledgment must be true or false.')
        overrides = config.get('overrides', {})
        if not isinstance(overrides, dict):
            raise ValueError('Day-specific restrictions must be an object.')
        for day, values in overrides.items():
            if day not in {str(i) for i in range(1, 8)} or not isinstance(values, dict) or not set(values) <= set(MINUTE_FIELDS + DAILY_LIMITS):
                raise ValueError('Invalid day-specific restriction.')
            for name, value in values.items():
                validate_number(value, f'Day {day}: {name}', name in MINUTE_FIELDS)
        for day, activity in enumerate(schedule, 1):
            if activity != 'training':
                continue
            inputs = {**planning, **overrides.get(str(day), {})}
            if inputs['team_min'] > inputs['team_max'] or inputs['extra_min'] > inputs['extra_max']:
                raise ValueError(f'Day {day}: minimum participation cannot exceed maximum participation.')
            if inputs['team_min'] + inputs['extra_min'] + inputs['other_recorded'] > 1440:
                raise ValueError(f'Day {day}: minimum recording duration exceeds 1440 minutes.')
            if inputs['original_team'] + inputs['original_extra'] + inputs['other_recorded'] > 1440:
                raise ValueError(f'Day {day}: original recording duration exceeds 1440 minutes.')


def in_fitting_period(start_day):
    return day_date(start_day) <= FITTING_PERIOD['last_date']


def week_dates(start_day):
    return [(dt.date.fromordinal(start_day) + dt.timedelta(days=i)).isoformat() for i in range(7)]


def validate_number(value, name, whole_minutes=False):
    # Reject booleans, missing values, infinity and oversized numbers before NumPy.
    if type(value) not in (int, float) or not 0 <= value <= (1440 if whole_minutes else 1e9):
        raise ValueError(f'{name} must be a finite nonnegative number within the allowed range.')
    if whole_minutes and int(value) != value:
        raise ValueError(f'{name} must be whole minutes.')


def candidates(planning, step):
    """Keep the closest operational allocation for each possible duration."""
    for name in MINUTE_FIELDS + DAILY_LIMITS:
        validate_number(planning[name], name, name in MINUTE_FIELDS)
    if planning['team_min'] > planning['team_max'] or planning['extra_min'] > planning['extra_max']:
        raise ValueError('Minimum participation cannot exceed maximum participation.')

    minimum_active = planning['team_min'] + planning['extra_min']
    maximum_active = min(planning['team_max'] + planning['extra_max'],
                         1440 - planning['other_recorded'])
    original_active = planning['original_team'] + planning['original_extra']
    allocations = []
    for active_minutes in range(int(minimum_active), int(maximum_active) + 1):
        if active_minutes % step and active_minutes not in (minimum_active, maximum_active, original_active):
            continue
        minimum_team = max(planning['team_min'], active_minutes - planning['extra_max'])
        maximum_team = min(planning['team_max'], active_minutes - planning['extra_min'])
        team_minutes = min(maximum_team, max(minimum_team, planning['original_team']))
        extra_minutes = active_minutes - team_minutes
        duration = active_minutes + planning['other_recorded']
        allocations.append(dict(team=int(team_minutes), extra=int(extra_minutes),
                                actual_duration_min=duration))
    return pd.DataFrame(allocations, columns=['team', 'extra', DURATION])


def day_options(day, planning, step, history, athlete):
    """Predict the feasible allocations and the original plan for one day."""
    allocations = candidates(planning, step)
    original_duration = planning['original_team'] + planning['original_extra'] + planning['other_recorded']
    durations = sorted(set(allocations[DURATION]) | {original_duration})
    predictions = evaluate(history, durations, FITTING_DATA, athlete)
    if predictions.empty:
        raise ValueError(f'Day {day}: no historically supported duration.')

    options = allocations.merge(predictions, on=DURATION)
    within_ml = options.movement_load + planning['ml_buffer'] <= planning['ml_limit']
    within_trimp = options.training_trimp + planning['trimp_buffer'] <= planning['trimp_limit']
    options = options[within_ml & within_trimp]
    if options.empty:
        raise ValueError(f'Day {day}: no supported allocation meets the daily limits.')
    context_fields = ['original_team', 'original_extra', 'other_recorded'] + ['ml_buffer', 'trimp_buffer', 'ml_limit', 'trimp_limit']
    options = options.assign(day=day, **{name: planning[name] for name in context_fields})

    original = dict(day=day, team=planning['original_team'], extra=planning['original_extra'],
                    duration=original_duration, mip1=None, movement_load=None, training_trimp=None)
    original_prediction = predictions[predictions[DURATION] == original_duration]
    if not original_prediction.empty:
        original.update(original_prediction[['mip1', 'movement_load', 'training_trimp']].iloc[0].to_dict())
    return options, original


def weekly_options(config, history, athlete):
    """Build the candidate table for the training days of the week."""
    tables, originals = [], []
    for day, activity in enumerate(config['schedule'], 1):
        if activity != 'training':
            continue
        planning = {**config['planning'], **config.get('overrides', {}).get(str(day), {})}
        options, original = day_options(day, planning, config['step'], history, athlete)
        tables.append(options)
        originals.append(original)
    return pd.concat(tables, ignore_index=True), originals
