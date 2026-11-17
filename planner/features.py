"""Build the planner's inputs from validated LoadWise daily records.

This replaces prototype/data/prepare_data.py from SamuelO12/createx-loadwise, which read the
workbook directly. The rules are the same:
- one row per athlete and day with at least one included training session
- mip1 / mip3: max over that day's training sessions that recorded it
- movement_load, training_trimp, recorded_duration_min, high_hr_minutes: sum over the day's
  training sessions, only when every training session has the value (otherwise None)
- game days: athlete-days with an included game session

Differences: LoadWise has already removed exact duplicates, applied manual overrides and
resolved calendar dates. `day` is the date's ordinal, so day arithmetic is in calendar days.
`history_features` is copied unchanged.
"""
import datetime as dt
import statistics

import pandas as pd

TRAINING_DAY_COLUMNS = ['athlete_id', 'loadwise_athlete_id', 'date', 'day', 'mip1', 'mip3',
                        'movement_load', 'training_trimp', 'recorded_duration_min', 'high_hr_minutes']
NUMERIC = TRAINING_DAY_COLUMNS[4:]


def day_number(iso_date):
    return dt.date.fromisoformat(iso_date).toordinal()


def day_date(day):
    return dt.date.fromordinal(int(day)).isoformat()


def training_days(daily_records):
    """Return (training-day DataFrame, set of (athlete label, day) with a game session)."""
    rows, games = [], set()
    for d in daily_records:
        label, day = d['athlete_label'], day_number(d['date'])
        if d['session_counts_by_type']['game']:
            games.add((label, day))
        if not d['session_counts_by_type']['training']:
            continue
        training = d['breakdown']['training']

        def complete(metric):
            block = training[metric]
            return block['value'] if block['completeness'] == 'complete' else None

        peaks = d['peak_intensity']
        rows.append(dict(
            athlete_id=label, loadwise_athlete_id=d['athlete_id'], date=d['date'], day=day,
            mip1=peaks['mip1']['by_bucket']['training']['value'],
            mip3=peaks['mip3']['by_bucket']['training']['value'],
            movement_load=complete('movement_load'), training_trimp=complete('trimp'),
            recorded_duration_min=complete('duration_min'), high_hr_minutes=complete('hit_min'),
        ))
    frame = pd.DataFrame(rows, columns=TRAINING_DAY_COLUMNS)
    frame[NUMERIC] = frame[NUMERIC].astype(float)
    return frame.sort_values(['athlete_id', 'day']).reset_index(drop=True), games


def total(values):
    observed = [value for value in values if value is not None]
    return sum(observed) if observed else None


def mean(values):
    observed = [value for value in values if value is not None]
    return statistics.mean(observed) if observed else None


def history_features(past, games, athlete, day):
    """Calculate the 17 historical predictors from observations before day."""
    measured = [row for row in past if row['mip1'] is not None]
    if len(measured) < 3:
        raise ValueError('Fewer than three prior measured training days.')
    previous_week = [row for row in past if day - 7 <= row['day'] < day]
    previous_28_days = [row for row in past if day - 28 <= row['day'] < day]

    def values(rows, key):
        return [row[key] for row in rows if row[key] is not None]
    return dict(
        last_mip1=measured[-1]['mip1'],
        days_since_mip1=day - measured[-1]['day'],
        mip1_mean_7d=mean(values(previous_week, 'mip1')),
        mip1_mean_28d=mean(values(previous_28_days, 'mip1')),
        mip1_days_7d=len(values(previous_week, 'mip1')),
        mip1_days_28d=len(values(previous_28_days, 'mip1')),
        last_recorded_duration_min=past[-1]['recorded_duration_min'],
        recorded_duration_mean_7d=mean(values(previous_week, 'recorded_duration_min')),
        training_days_7d=len(previous_week),
        training_days_28d=len(previous_28_days),
        training_trimp_sum_7d=total(values(previous_week, 'training_trimp')),
        training_trimp_sum_28d=total(values(previous_28_days, 'training_trimp')),
        movement_load_sum_7d=total(values(previous_week, 'movement_load')),
        movement_load_days_7d=len(values(previous_week, 'movement_load')),
        high_hr_minutes_sum_7d=total(values(previous_week, 'high_hr_minutes')),
        high_hr_days_7d=len(values(previous_week, 'high_hr_minutes')),
        reported_game_days_7d=sum(((athlete, previous_day) in games for previous_day in range(day - 7, day)))
    )
