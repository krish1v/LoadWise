from sklearn.ensemble import RandomForestRegressor

def configurations():
    models = []
    for depth in [4, 8, None]:
        for leaf_size in [3, 10]:
            parameters = {
                'max_depth': depth,
                'min_samples_leaf': leaf_size,
                'n_estimators': 120,
                'max_features': 0.7,
                'random_state': 42}
            model = RandomForestRegressor(**parameters, n_jobs=2)
            models.append(('Random Forest', parameters, model))
    return models
