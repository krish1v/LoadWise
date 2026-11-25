"""Read the Bamberg workbook and prepare daily training histories"""
import statistics
import argparse
from collections import defaultdict
from pathlib import Path
import pandas as pd

DATA = Path(__file__).resolve().parent
RAW_WORKBOOK = DATA.parent / 'Data Set Georgia Tech_anonymized.xlsx'
PROCESSED = DATA / 'processed'

def total(values):
    observed = [value for value in values if value is not None]
    return sum(observed) if observed else None

def mean(values):
    observed = [value for value in values if value is not None]
    return statistics.mean(observed) if observed else None

def complete_sum(values):
    # A partial recording should not look like a complete daily workload.
    if not values or any(value is None for value in values):
        return None
    return sum(values)

def read_data(workbook):
    raw = pd.read_excel(workbook, sheet_name='Full Day')
    raw['source_row'] = raw.index + 2
    for column in ['Duration (hh:mm:ss)', 'High intensity training (hh:mm:ss)']:
        raw[column] = raw[column].dt.total_seconds() / 60
    return raw

def column_values(rows, column):
    return [None if pd.isna(value) else value for value in rows[column]]

def day_label(rows, column, athlete, day):
    labels = rows[column].dropna().unique()
    if len(labels) > 1:
        raise ValueError(f'Conflicting {column} labels for {athlete}, Day {day}')
    return labels[0] if len(labels) else 'UNKNOWN'

def aggregate(raw):
    training = raw[raw['Measurement type'] == 'Training']
    game_records = raw[raw['Measurement type'] == 'Game']
    game_days = set(zip(game_records['Athlete name'], game_records['Day']))
    daily = []

    for (athlete, day), rows in training.groupby(['Athlete name', 'Day']):
        movement_load = complete_sum(column_values(rows, 'Movement load'))
        trimp = complete_sum(column_values(rows, 'TRIMP (Index)'))
        mip1 = rows['Maximal Intensity Period MI 1min'].dropna()
        mip3 = rows['Maximal Intensity Period MI 3min'].dropna()
        games_today = game_records[(game_records['Athlete name'] == athlete) & (game_records['Day'] == day)]
        efficiency = None
        if movement_load is not None and trimp:
            efficiency = movement_load / trimp

        daily.append({
            'athlete_id': athlete,
            'day': int(day),
            'date_label': rows['Date'].iloc[0],
            'gd_recorded': day_label(rows, 'GD', athlete, day),
            'colour_recorded': day_label(rows, 'Colour', athlete, day),
            'training_record_count': len(rows),
            'movement_record_count': len(mip1),
            'source_rows': ';'.join(map(str, rows.source_row)),
            # MIP is the highest recorded intensity, so take the day's maximum
            'mip1': float(mip1.max()) if len(mip1) else None,
            'mip3': float(mip3.max()) if len(mip3) else None,
            'movement_load': movement_load,
            'training_trimp': trimp,
            'recorded_duration_min': complete_sum(column_values(rows, 'Duration (hh:mm:ss)')),
            'high_hr_minutes': complete_sum(column_values(rows, 'High intensity training (hh:mm:ss)')),
            'movement_efficiency': efficiency,
            'zero_trimp': int(trimp == 0),
            'game_record_count': len(games_today),
            'reported_game_trimp': games_today['TRIMP (Index)'].sum(min_count=1)})
    return daily, game_days

def history_features(past, games, athlete, day):
    # Use only observations before the day being predicted
    measured = [row for row in past if row['mip1'] is not None]
    if len(measured) < 3:
        raise ValueError('Fewer than three prior measured training days.')
    week = [row for row in past if day - 7 <= row['day'] < day]
    month = [row for row in past if day - 28 <= row['day'] < day]

    def observed(rows, field):
        return [row[field] for row in rows if row[field] is not None]

    recent_games = sum((athlete, earlier_day) in games for earlier_day in range(day - 7, day))
    return {
        'last_mip1': measured[-1]['mip1'],
        'days_since_mip1': day - measured[-1]['day'],
        'mip1_mean_7d': mean(observed(week, 'mip1')),
        'mip1_mean_28d': mean(observed(month, 'mip1')),
        'mip1_days_7d': len(observed(week, 'mip1')),
        'mip1_days_28d': len(observed(month, 'mip1')),
        'last_recorded_duration_min': past[-1]['recorded_duration_min'],
        'recorded_duration_mean_7d': mean(observed(week, 'recorded_duration_min')),
        'training_days_7d': len(week),
        'training_days_28d': len(month),
        'training_trimp_sum_7d': total(observed(week, 'training_trimp')),
        'training_trimp_sum_28d': total(observed(month, 'training_trimp')),
        'movement_load_sum_7d': total(observed(week, 'movement_load')),
        'movement_load_days_7d': len(observed(week, 'movement_load')),
        'high_hr_minutes_sum_7d': total(observed(week, 'high_hr_minutes')),
        'high_hr_days_7d': len(observed(week, 'high_hr_minutes')),
        'reported_game_days_7d': recent_games}

def build_features(daily, game_days):
    by_athlete = defaultdict(list)
    for row in daily:
        by_athlete[row['athlete_id']].append(row)

    output = []
    for athlete, records in sorted(by_athlete.items()):
        records = sorted(records, key=lambda row: row['day'])
        for row in records:
            if row['mip1'] is None:
                continue
            day = row['day']
            past = [record for record in records if record['day'] < day]
            measured_count = sum(record['mip1'] is not None for record in past)
            if measured_count < 3:
                continue
            if day <= 70:
                split = 'train'
            elif day <= 95:
                split = 'validation'
            else:
                split = 'test'

            output.append({
                'athlete_id': athlete,
                'day': day,
                'date_label': row['date_label'],
                'split': split,
                'target_mip1': row['mip1'],
                'target_mip3': row['mip3'],
                'target_movement_load': row['movement_load'],
                'target_training_trimp': row['training_trimp'],
                'gd_recorded': row['gd_recorded'],
                'prior_mip1_count': measured_count,
                'history_last_day': past[-1]['day'],
                **history_features(past, game_days, athlete, day)})
    return sorted(output, key=lambda row: (row['day'], row['athlete_id']))

def load_data(processed=PROCESSED):
    processed = Path(processed)
    daily = pd.read_csv(processed / 'athlete_training_days.csv')
    modeling_data = pd.read_csv(processed / 'modeling_data.csv')
    durations = daily[['athlete_id', 'day', 'recorded_duration_min']].rename(columns={'recorded_duration_min': 'actual_duration_min'})
    modeling_data = modeling_data.merge(durations, on=['athlete_id', 'day'], validate='one_to_one')
    game_records = pd.read_csv(processed / 'game_days.csv')
    game_days = set(zip(game_records.athlete_id, game_records.day))
    return daily, modeling_data, game_days

def prepare_data(workbook=RAW_WORKBOOK, output=PROCESSED):
    output = Path(output)
    raw = read_data(workbook)
    daily, game_days = aggregate(raw)
    modeling_data = build_features(daily, game_days)
    output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(daily).to_csv(output / 'athlete_training_days.csv', index=False)
    pd.DataFrame(modeling_data).to_csv(output / 'modeling_data.csv', index=False)
    pd.DataFrame(sorted(game_days), columns=['athlete_id', 'day']).to_csv(output / 'game_days.csv', index=False)
    print(f'{len(raw)} source records, {len(daily)} training days, '
          f'{len(modeling_data)} modeling rows.', flush=True)
    return output

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workbook', nargs='?', type=Path, default=RAW_WORKBOOK)
    parser.add_argument('--output', type=Path, default=PROCESSED)
    args = parser.parse_args()
    prepare_data(args.workbook, args.output)




