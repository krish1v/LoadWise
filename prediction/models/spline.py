from sklearn.linear_model import Ridge

def configurations():
    models = []
    for knots in [3, 5]:
        for alpha in [1, 10, 100]:
            parameters = {'n_knots': knots, 'alpha': alpha}
            models.append(('Spline Ridge', parameters, Ridge(alpha=alpha)))
    return models
