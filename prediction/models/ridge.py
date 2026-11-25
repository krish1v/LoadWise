from sklearn.linear_model import Ridge

def configurations():
    models = []
    for alpha in [0.1, 1, 10, 100]:
        models.append(('Ridge', {'alpha': alpha}, Ridge(alpha=alpha)))
    return models
