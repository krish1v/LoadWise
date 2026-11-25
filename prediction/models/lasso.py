from sklearn.linear_model import Lasso

def configurations():
    models = []
    for alpha in [0.001, 0.01, 0.05, 0.1, 0.5]:
        model = Lasso(alpha=alpha, max_iter=30000)
        models.append(('Lasso', {'alpha': alpha}, model))
    return models
