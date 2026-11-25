from sklearn.neighbors import KNeighborsRegressor

def configurations():
    models = []
    for neighbor_count in [5, 15, 30, 60]:
        for weights in ['uniform', 'distance']:
            parameters = {'n_neighbors': neighbor_count, 'weights': weights}
            models.append(('KNN', parameters, KNeighborsRegressor(**parameters)))
    return models
