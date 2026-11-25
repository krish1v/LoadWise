"""Choose individual training minutes around the team's fixed schedule."""
import copy

import numpy as np
import pandas as pd

from .features import day_date
from .optimize import solve_options
from .recommend import summarize
from .scenarios import validate_number, week_dates, weekly_options

LIMITS = (
    'ml_limit', 'trimp_limit', 'ml_buffer', 'trimp_buffer',
    'weekly_ml_limit', 'weekly_trimp_limit',
)


def athlete_config(config, athlete):
    """Build one athlete's inputs for the existing candidate generator."""
    planning = {
        'original_team': 0,
        'original_extra': 0,
        'other_recorded': athlete['other_recorded'],
        'team_min': 0,
        'team_max': 0,
        'extra_min': 0,
        'extra_max': 0,
    }
    planning.update(athlete['limits'])

    overrides = {}
    for day, inputs in enumerate(config['days'], 1):
        team_minutes = inputs['team']
        # Equal minimum and maximum keep team practice fixed.
        overrides[str(day)] = {
            'original_team': team_minutes,
            'team_min': team_minutes,
            'team_max': team_minutes,
            'extra_max': athlete['availability'][day - 1],
        }

    return {
        'athlete': athlete['athlete'],
        'start': config['start'],
        'planning': planning,
        'schedule': [day['kind'] for day in config['days']],
        'overrides': overrides,
        'step': config['step'],
        'objective': config['objective'],
        'allow_pooled': athlete['allow_pooled'],
    }


def check_config(context, config):
    if not isinstance(config, dict):
        raise ValueError('Provide the squad planning inputs.')
    start = context.start_day(config.get('start'))
    if config.get('objective') not in ('terminal', 'cumulative'):
        raise ValueError('Choose a final-day or whole-week objective.')
    if type(config.get('step')) is not int or config['step'] not in (1, 5, 10):
        raise ValueError('Choose minute steps of 1, 5 or 10.')

    days = config.get('days')
    if not isinstance(days, list) or len(days) != 7:
        raise ValueError('Provide the seven days of the team schedule.')
    for day, inputs in enumerate(days, 1):
        if not isinstance(inputs, dict):
            raise ValueError(f'Day {day}: choose training, game or rest.')
        if inputs.get('kind') not in ('training', 'game', 'rest'):
            raise ValueError(f'Day {day}: choose training, game or rest.')
        validate_number(inputs.get('team'), f'Day {day}: team minutes', True)
        if inputs['kind'] != 'training' and inputs['team'] != 0:
            raise ValueError(f'Day {day}: team training must be zero on game and rest days.')
        if inputs.get('individual_limit') is not None:
            validate_number(inputs['individual_limit'], f'Day {day}: shared individual-minute limit')
    if not any(day['kind'] == 'training' for day in days):
        raise ValueError('Select at least one training day.')
    if config['objective'] == 'terminal' and days[-1]['kind'] != 'training':
        raise ValueError('The final-day objective requires Day 7 to be a training day.')

    athletes = config.get('athletes')
    if not isinstance(athletes, list) or not 1 <= len(athletes) <= len(context.roster):
        raise ValueError('Select at least one roster athlete, with no duplicates.')
    selected_names = set()
    for athlete in athletes:
        if not isinstance(athlete, dict):
            raise ValueError('Provide each athlete’s availability and workload limits.')
        name = athlete.get('athlete')
        if not isinstance(name, str) or name not in context.roster or name in selected_names:
            raise ValueError('Select each roster athlete once.')
        selected_names.add(name)

        availability = athlete.get('availability')
        if not isinstance(availability, list) or len(availability) != 7:
            raise ValueError(f'{name}: provide seven daily availability limits.')
        for day, minutes in enumerate(availability, 1):
            validate_number(minutes, f'{name}, Day {day}: individual availability', True)
        validate_number(athlete.get('other_recorded'), f'{name}: other monitored minutes', True)

        limits = athlete.get('limits')
        if not isinstance(limits, dict) or set(limits) != set(LIMITS):
            raise ValueError(f'{name}: provide all daily and weekly workload limits.')
        for name_of_limit, value in limits.items():
            validate_number(value, f'{name}: {name_of_limit}')
        if type(athlete.get('allow_pooled')) is not bool:
            raise ValueError(f'{name}: specify whether to allow duration-only models.')
    return start


def squad_constraints(options, config):
    rows = []
    lower = []
    upper = []

    # Select exactly one option for every athlete on each training day.
    for _, choices in options.groupby(['athlete', 'day']):
        rows.append(np.asarray(options.index.isin(choices.index), dtype=float))
        lower.append(1)
        upper.append(1)

    for athlete in config['athletes']:
        athlete_rows = options.athlete == athlete['athlete']
        movement_load = athlete_rows * (options.movement_load + options.ml_buffer)
        trimp = athlete_rows * (options.training_trimp + options.trimp_buffer)
        rows.append(np.asarray(movement_load, dtype=float))
        lower.append(-np.inf)
        upper.append(athlete['limits']['weekly_ml_limit'])
        rows.append(np.asarray(trimp, dtype=float))
        lower.append(-np.inf)
        upper.append(athlete['limits']['weekly_trimp_limit'])

    # A shared budget links the individual plans when coaching time is limited.
    for day, inputs in enumerate(config['days'], 1):
        if inputs['kind'] != 'training' or inputs.get('individual_limit') is None:
            continue
        individual_minutes = (options.day == day) * options.extra
        rows.append(np.asarray(individual_minutes, dtype=float))
        lower.append(-np.inf)
        upper.append(inputs['individual_limit'])
    return rows, lower, upper


def squad_scores(athletes, objective, baseline=False):
    summary_key = 'summary'
    if baseline:
        summary_key = 'baseline'
    metric = 'mip_sum'
    if objective == 'terminal':
        metric = 'day7_mip'

    total = 0.0
    for athlete in athletes:
        value = athlete[summary_key][metric]
        # A missing prediction must not count as zero in the team score.
        if value is None:
            return {'total': None, 'average': None}
        total += value
    return {'total': float(total), 'average': float(total / len(athletes))}


def baseline_summary(originals, planning):
    for day in originals:
        if day['mip1'] is None:
            return {
                'day7_mip': None,
                'mip_sum': None,
                'feasible': False,
                'reason': 'Some team-only durations are outside the model’s supported range.',
            }

    weekly_ml = 0.0
    weekly_trimp = 0.0
    mip_sum = 0.0
    day7_mip = None
    feasible = True
    for day in originals:
        movement_load = day['movement_load'] + planning['ml_buffer']
        trimp = day['training_trimp'] + planning['trimp_buffer']
        weekly_ml += day['movement_load']
        weekly_trimp += day['training_trimp']
        mip_sum += day['mip1']
        if movement_load > planning['ml_limit'] or trimp > planning['trimp_limit']:
            feasible = False
        if day['day'] == 7:
            day7_mip = day['mip1']
    weekly_ml += len(originals) * planning['ml_buffer']
    weekly_trimp += len(originals) * planning['trimp_buffer']
    if weekly_ml > planning['weekly_ml_limit'] or weekly_trimp > planning['weekly_trimp_limit']:
        feasible = False

    reason = None
    if not feasible:
        reason = 'The team-only baseline exceeds a workload limit.'
    return {'day7_mip': day7_mip, 'mip_sum': mip_sum, 'feasible': feasible, 'reason': reason}


def recommend_squad(context, config):
    """Choose all individual blocks together, using the same history all week."""
    config = copy.deepcopy(config)
    start = check_config(context, config)
    config['start'] = day_date(start)
    candidate_tables = []
    athlete_details = []

    for athlete in config['athletes']:
        name = athlete['athlete']
        inputs = athlete_config(config, athlete)
        try:
            context.validate_week(inputs)
            _, history, reason = context.athlete_state(name, start)
            if reason and not athlete['allow_pooled']:
                raise ValueError(reason + ' Allow duration-only models or deselect this athlete.')
            prediction_athlete = name
            if reason:
                prediction_athlete = None
            options, originals = weekly_options(inputs, history, prediction_athlete)
        except ValueError as error:
            raise ValueError(f'{name}: {error}') from error
        candidate_tables.append(options.assign(athlete=name))
        athlete_details.append({
            'athlete': name,
            'athlete_id': athlete.get('athlete_id', name),
            'pooled': bool(reason),
            'reason': reason,
            'inputs': inputs,
            'original': originals,
        })

    options = pd.concat(candidate_tables, ignore_index=True)
    rows, lower, upper = squad_constraints(options, config)
    mip_scores = np.rint(options.mip1.to_numpy() * 100000)
    priorities = []
    # The solver minimizes, so negative MIP scores maximize the team's MIP.
    if config['objective'] == 'terminal':
        priorities.append(-mip_scores * (options.day == 7))
    priorities.append(-mip_scores)
    priorities.append(options.extra.to_numpy())
    plan = solve_options(options, rows.copy(), lower.copy(), upper.copy(), priorities)
    if plan is None:
        raise ValueError(
            'No squad plan meets every athlete’s weekly limits and the shared '
            'individual-training limits. Review those limits or the fixed team schedule.'
        )

    # Check the original constraints before formatting the plans.
    selected = np.asarray(options.index.isin(plan.index), dtype=float)
    totals = np.asarray(rows) @ selected
    if np.any(totals < np.asarray(lower) - 1e-6) or np.any(totals > np.asarray(upper) + 1e-6):
        raise RuntimeError('The selected squad plan does not meet its constraints.')

    dates = week_dates(start)
    schedule = [day['kind'] for day in config['days']]
    athletes = []
    for detail in athlete_details:
        planning = detail['inputs']['planning']
        athlete_plan = plan[plan.athlete == detail['athlete']].drop(columns='athlete')
        summary = summarize(athlete_plan, schedule, planning)
        for day in summary['plan']:
            day['date'] = dates[int(day['day']) - 1]
            day['team'] = int(day['team'])
            day['extra'] = int(day['extra'])
        for day in detail['original']:
            day['date'] = dates[int(day['day']) - 1]
        athletes.append({
            'athlete': detail['athlete'],
            'athlete_id': detail['athlete_id'],
            'pooled': detail['pooled'],
            'reason': detail['reason'],
            'original': detail['original'],
            'summary': summary,
            'baseline': baseline_summary(detail['original'], planning),
        })

    daily = []
    for day, inputs in enumerate(config['days'], 1):
        training = plan[plan.day == day]
        mip_total = None
        mip_average = None
        if len(training):
            mip_total = float(training.mip1.sum())
            mip_average = float(training.mip1.mean())
        day_summary = inputs.copy()
        day_summary.update({
            'day': day,
            'date': dates[day - 1],
            'individual_minutes': int(training.extra.sum()),
            'mip_total': mip_total,
            'mip_average': mip_average,
        })
        daily.append(day_summary)

    score = squad_scores(athletes, config['objective'])
    baseline = squad_scores(athletes, config['objective'], baseline=True)
    baseline['feasible'] = all(athlete['baseline']['feasible'] for athlete in athletes)
    improvement = None
    if baseline['average'] is not None:
        improvement = score['average'] - baseline['average']
    return {
        'start': config['start'],
        'objective': config['objective'],
        'athlete_count': len(athletes),
        'score': score,
        'baseline': baseline,
        'improvement': improvement,
        'days': daily,
        'athletes': athletes,
        'explanation': (
            'Maximize the sum of selected athletes’ predicted MIP, with equal weights. '
            'The squad average is that sum divided by the number of selected athletes. '
            'Ties favor less individual training; final-day ties first favor whole-week MIP.'
        ),
        'limitation': (
            'History stays fixed throughout the week. Predictions use total recorded '
            'duration, without separate effects for team and individual work. Game and '
            'rest exposure is not modeled. MIP is a training-intensity metric, not a '
            'prediction of team wins, readiness or injury.'
        ),
    }
