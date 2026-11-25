"""Choose training options within the weekly workload budgets.

Based on SamuelO12/createx-loadwise, commit e5ec641.
"""
import numpy as np
from scipy.optimize import milp, Bounds, LinearConstraint

from .predict import DURATION
from .scenarios import weekly_options


def weekly_constraints(options, planning):
    training_days = options.day.unique()
    rows = []
    for day in training_days:
        # The binary choices for a training day must add up to exactly one.
        rows.append(np.array(options.day == day, dtype=float))
    rows.append(options.movement_load + options.ml_buffer)
    rows.append(options.training_trimp + options.trimp_buffer)
    lower = [1] * len(training_days) + [-np.inf, -np.inf]
    upper = [1] * len(training_days) + [planning['weekly_ml_limit'], planning['weekly_trimp_limit']]
    return rows, lower, upper


def objective_priorities(options, objective, target):
    # The solver minimizes. Negative MIP scores therefore maximize MIP.
    mip_scores = np.rint(options[target].to_numpy() * 100000)
    team_change = abs(options.team - options.original_team)
    extra_change = abs(options.extra - options.original_extra)
    priorities = []
    if objective == 'terminal':
        priorities.append(-mip_scores * (options.day == 7))
    priorities.append(-mip_scores)
    priorities.append(team_change + extra_change)
    priorities.append(team_change)
    priorities.append(options.team + options.extra)
    return priorities


def order_equivalent_days(plan, options, objective):
    """Make tied schedules display consistently by ordering interchangeable days."""
    context = ['original_team', 'original_extra', 'other_recorded', 'ml_limit',
               'trimp_limit', 'ml_buffer', 'trimp_buffer']
    plan['terminal'] = (plan.day == 7) & (objective == 'terminal')
    choice_columns = ['team', 'extra', DURATION]
    for _, group in plan.groupby(context + ['terminal']):
        days = sorted(group.day)
        first_choices = options.loc[options.day == days[0], choice_columns].values.tolist()
        same_choices = True
        for day in days:
            choices = options.loc[options.day == day, choice_columns].values.tolist()
            if choices != first_choices:
                same_choices = False
                break
        if same_choices:
            ordered_rows = group.sort_values(DURATION).index
            plan.loc[ordered_rows, 'day'] = days
    return plan.drop(columns='terminal')


def check_solution(plan, options, planning):
    total_ml = (plan.movement_load + plan.ml_buffer).sum()
    total_trimp = (plan.training_trimp + plan.trimp_buffer).sum()
    one_per_day = len(plan) == options.day.nunique() and plan.day.nunique() == len(plan)
    if (not one_per_day or total_ml > planning['weekly_ml_limit'] + 1e-6
            or total_trimp > planning['weekly_trimp_limit'] + 1e-6):
        raise ValueError('The solver result does not satisfy the weekly constraints.')
    for row in plan.itertuples(index=False):
        choices = options[options.day == row.day]
        matched = choices[(choices.team == row.team) & (choices.extra == row.extra)]
        within_ml = row.movement_load + row.ml_buffer <= row.ml_limit + 1e-6
        within_trimp = row.training_trimp + row.trimp_buffer <= row.trimp_limit + 1e-6
        if matched.empty or not within_ml or not within_trimp:
            raise RuntimeError('The solver result does not satisfy the daily constraints.')


def solve_options(options, rows, lower, upper, priorities):
    """Solve each objective in order, keeping the earlier optimal values."""
    for priority in priorities:
        coefficients = np.asarray(priority, dtype=float)
        result = milp(
            coefficients,
            integrality=np.ones(len(options)),
            bounds=Bounds(0, 1),
            constraints=LinearConstraint(np.array(rows), lower, upper),
            options={'mip_rel_gap': 0.0, 'time_limit': 20},
        )
        if result.status == 2:
            return None
        if result.status != 0 or result.x is None:
            raise ValueError('Solver did not certify an optimum. Try a larger minute step.')
        if not np.isfinite(result.x).all():
            raise RuntimeError('The solver returned a nonintegral result.')
        rounded = np.rint(result.x)
        if np.max(np.abs(result.x - rounded)) > 1e-5:
            raise RuntimeError('The solver returned a nonintegral result.')
        selected = rounded.astype(int)

        # Keep this optimum when solving the next tie-breaker.
        rows.append(coefficients)
        lower.append(-np.inf)
        upper.append(round(float(coefficients @ selected)))

    return options.loc[selected == 1].copy()


def choose(options, planning, objective, target):
    rows, lower, upper = weekly_constraints(options, planning)
    priorities = objective_priorities(options, objective, target)
    plan = solve_options(options, rows, lower, upper, priorities)
    if plan is None:
        return None
    check_solution(plan, options, planning)
    plan = order_equivalent_days(plan, options, objective)
    check_solution(plan, options, planning)
    return plan


def optimize_week(context, config):
    context.validate_week(config)
    athlete = config['athlete']
    _, history, reason = context.athlete_state(athlete, config['start'])
    if reason and config.get('allow_pooled') is not True:
        raise ValueError(reason + ' Confirm the pooled scenario to continue.')
    prediction_athlete = None if reason else athlete
    options, originals = weekly_options(config, history, prediction_athlete)
    planning = config['planning']
    objective = config['objective']
    primary = choose(options, planning, objective, 'mip1')
    if primary is None:
        raise ValueError('No weekly plan meets both weekly workload limits.')
    alternative = None
    if not reason:
        alternative = choose(options, planning, objective, 'spline')
    return primary, alternative, originals, reason
