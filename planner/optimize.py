"""Select a seven-day training plan using a mixed-integer linear model.

Adapted from SamuelO12/createx-loadwise, prototype/optimization/optimize.py (commit e5ec641).
Only `optimize_week` changed: it takes the PlanningContext built from LoadWise data.
"""
import numpy as np
from scipy.optimize import milp, Bounds, LinearConstraint

from .predict import DURATION
from .scenarios import weekly_options


def weekly_constraints(options, planning):
    # Select one candidate per training day, then limit total workload.
    training_days = options.day.unique()
    rows = [np.array(options.day == day, dtype=float) for day in training_days]
    rows.append(options.movement_load + options.ml_buffer)
    rows.append(options.training_trimp + options.trimp_buffer)
    lower = [1] * len(training_days) + [-np.inf, -np.inf]
    upper = [1] * len(training_days) + [planning['weekly_ml_limit'], planning['weekly_trimp_limit']]
    return rows, lower, upper


def objective_priorities(options, objective, target):
    # MIP is compared to five decimal places for stable solver results.
    mip_scores = np.rint(options[target].to_numpy() * 100000)
    team_change = abs(options.team - options.original_team)
    extra_change = abs(options.extra - options.original_extra)
    priorities = [-mip_scores]
    if objective == 'terminal':
        priorities.insert(0, -mip_scores * (options.day == 7))
    priorities.extend([team_change + extra_change, team_change, options.team + options.extra])
    return priorities


def order_equivalent_days(plan, options, objective):
    """Give interchangeable days a consistent order without changing the solution."""
    columns = ['original_team', 'original_extra', 'other_recorded', 'ml_limit',
               'trimp_limit', 'ml_buffer', 'trimp_buffer']
    plan['terminal'] = (plan.day == 7) & (objective == 'terminal')
    for _, equivalent in plan.groupby(columns + ['terminal']):
        days = sorted(equivalent.day)
        first_choices = options.loc[options.day == days[0], ['team', 'extra', DURATION]].values.tolist()
        same_choices = True
        for day in days:
            choices = options.loc[options.day == day, ['team', 'extra', DURATION]].values.tolist()
            if choices != first_choices:
                same_choices = False
                break
        if same_choices:
            plan.loc[equivalent.sort_values(DURATION).index, 'day'] = days
    return plan.drop(columns='terminal')


def choose(options, planning, objective, target):
    """Solve each priority in order, preserving the earlier optimal values."""
    rows, lower, upper = weekly_constraints(options, planning)
    priorities = objective_priorities(options, objective, target)
    for priority in priorities:
        coefficients = np.asarray(priority, dtype=float)
        result = milp(coefficients, integrality=np.ones(len(options)), bounds=Bounds(0, 1),
                      constraints=LinearConstraint(np.array(rows), lower, upper),
                      options={'mip_rel_gap': 0.0, 'time_limit': 20})
        if result.status == 2:
            return None
        if result.status != 0 or result.x is None:
            raise ValueError('Solver did not certify an optimum. Try a larger minute step.')
        if not np.isfinite(result.x).all() or np.max(np.abs(result.x - np.rint(result.x))) > 1e-5:
            raise RuntimeError('The solver returned a nonintegral result.')
        selected = np.rint(result.x).astype(int)
        # Fix the current optimum before solving the next priority.
        rows.append(coefficients)
        lower.append(-np.inf)
        upper.append(round(float(coefficients @ selected)))

    plan = options.loc[selected == 1].copy()
    total_ml = (plan.movement_load + plan.ml_buffer).sum()
    total_trimp = (plan.training_trimp + plan.trimp_buffer).sum()
    if (len(plan) != options.day.nunique() or plan.day.nunique() != len(plan)
            or total_ml > planning['weekly_ml_limit'] + 1e-6
            or total_trimp > planning['weekly_trimp_limit'] + 1e-6):
        raise ValueError('The solver result does not satisfy the weekly constraints.')
    plan = order_equivalent_days(plan, options, objective)
    # Verify daily allocation and workload limits after ordering equivalent days.
    for row in plan.itertuples(index=False):
        choices = options[options.day == row.day]
        matched = choices[(choices.team == row.team) & (choices.extra == row.extra)]
        if matched.empty or row.movement_load + row.ml_buffer > row.ml_limit + 1e-6 or row.training_trimp + row.trimp_buffer > row.trimp_limit + 1e-6:
            raise RuntimeError('The solver result does not satisfy the daily constraints.')
    return plan


def optimize_week(context, config):
    context.validate_week(config)
    athlete = config['athlete']
    _, history, reason = context.athlete_state(athlete, config['start'])
    if reason and config.get('allow_pooled') is not True:
        raise ValueError(reason + ' Confirm the pooled scenario to continue.')
    options, originals = weekly_options(config, history, None if reason else athlete)
    planning, objective = config['planning'], config['objective']
    primary = choose(options, planning, objective, 'mip1')
    if primary is None:
        raise ValueError('No weekly plan meets both weekly workload limits.')
    alternative = None if reason else choose(options, planning, objective, 'spline')
    return primary, alternative, originals, reason
