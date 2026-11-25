from sklearn.svm import SVR

def configurations():
    models = []
    for regularization in [1, 5, 20]:
        for gamma in ['scale', 0.01]:
            parameters = {'C': regularization, 'gamma': gamma, 'epsilon': 0.1}
            models.append(('RBF SVR', parameters, SVR(**parameters)))
    return models
