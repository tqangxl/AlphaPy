##############################################################
#
# Package   : AlphaPy
# Module    : model
# Version   : 1.0
# Copyright : Mark Conway
# Date      : June 29, 2013
#
##############################################################


#
# Imports
#

import cPickle as pickle
from datetime import datetime
from estimators import get_classifiers
from estimators import get_class_scorers
from estimators import get_regressors
from estimators import get_regr_scorers
from globs import PSEP, SSEP, USEP
import logging
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.linear_model import RidgeCV
from sklearn.metrics import accuracy_score
from sklearn.metrics import classification_report
from sklearn.metrics import confusion_matrix
from sklearn.metrics import explained_variance_score
from sklearn.metrics import f1_score
from sklearn.metrics import mean_absolute_error
from sklearn.metrics import mean_squared_error
from sklearn.metrics import median_absolute_error
from sklearn.metrics import precision_score
from sklearn.metrics import r2_score
from sklearn.metrics import recall_score
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler


#
# Initialize logger
#

logger = logging.getLogger(__name__)


#
# Class Model
#
# model unifies algorithms and we use hasattr to list the available attrs for each
# algorithm so users can query an algorithm and get the list of attributes
#

class Model:

    # class variable to track all models

    models = {}

    # __new__
    
    def __new__(cls,
                specs):
        # create model name
        try:
            mn = specs['project']
        except:
            raise KeyError("Model specs must include the key: project")
        if not mn in Model.models:
            return super(Model, cls).__new__(cls)
        else:
            print "Model %s already exists" % mn
            
    # __init__
            
    def __init__(self,
                 specs):
        self.specs = specs
        self.name = specs['project']
        # initialize model
        self.X_train = None
        self.X_test = None
        self.y_train = None
        self.y_test = None
        try:
            separator = self.specs['separator']
        except:
            raise KeyError("Model specs must include the key: separator")
        try:
            self.algolist = self.specs['algorithms'].upper().split(separator)
        except:
            raise KeyError("Model specs must include the key: algorithms")
        # Key: (algorithm)
        self.estimators = {}
        self.support = {}
        self.scores = {}
        self.importances = {}
        self.coefs = {}
        # Keys: (algorithm, partition)
        self.preds = {}
        self.probas = {}
        # Keys: (algorithm, partition, metric)
        self.metrics = {}
        # add model to models list
        try:
            Model.models[specs['project']] = self
        except:
            raise KeyError("Model specs must include the key: project")
                
    # __str__

    def __str__(self):
        return self.name


#
# Function predict_best
#

def predict_best(model):
    """
    Select the best model based on score.
    """

    # Extract model parameters.

    X_train = model.X_train
    X_test = model.X_test
    regression = model.specs['regression']

    # Add BEST algorithm.

    best_tag = 'BEST'

    # Initialize best score

    best_score = 0.0

    # Iterate through the models, getting the best score for each one.

    start_time = datetime.now()
    logger.info("Best Model Selection Start: %s", start_time)

    for algorithm in model.algolist:
        top_score = model.scores[algorithm]
        # determine the best score from all the estimators
        if top_score > best_score:
            best_score = top_score
            best_algo = algorithm

    # Store predictions of best estimator

    model.estimators[best_tag] = model.estimators[best_algo]
    model.preds[(best_tag, 'train')] = model.preds[(best_algo, 'train')]
    model.preds[(best_tag, 'test')] = model.preds[(best_algo, 'test')]
    if not regression:
        model.probas[(best_tag, 'train')] = model.probas[(best_algo, 'train')]
        model.probas[(best_tag, 'test')] = model.probas[(best_algo, 'test')]

    # Return the model with best estimator and predictions.

    end_time = datetime.now()
    time_taken = end_time - start_time
    logger.info("Best Model Selection Complete: %s", time_taken)

    return model


#
# Function predict_blend
#

def predict_blend(model):
    """
    Make predictions from a blended model.
    """

    # Extract data and model parameters.

    X_train = model.X_train
    X_test = model.X_test
    y_train = model.y_train

    n_folds = model.specs['n_folds']
    regression = model.specs['regression']

    # Add blended algorithm.

    blend_tag = 'BLEND'

    # Create blended training and test sets.

    n_models = len(model.algolist)
    X_blend_train = np.zeros((X_train.shape[0], n_models))
    X_blend_test = np.zeros((X_test.shape[0], n_models))

    # Iterate through the models, cross-validating for each one.

    start_time = datetime.now()
    logger.info("Blending Start: %s", start_time)

    for i, algorithm in enumerate(model.algolist):
        # get the best estimator
        estimator = model.estimators[algorithm]
        if hasattr(estimator, "coef_"):
            model.coefs[algorithm] = estimator.coef_
        if hasattr(estimator, "feature_importances_"):
            model.importances[algorithm] = estimator.feature_importances_
        # store predictions in the blended training set
        if not regression:
            X_blend_train[:, i] = model.probas[(algorithm, 'train')]
            X_blend_test[:, i] = model.probas[(algorithm, 'test')]
        else:
            X_blend_train[:, i] = model.preds[(algorithm, 'train')]
            X_blend_test[:, i] = model.preds[(algorithm, 'test')]

    # Use the blended estimator to make predictions

    if not regression:
        clf = LogisticRegression()
        clf.fit(X_blend_train, y_train)
        model.estimators[blend_tag] = clf
        model.preds[(blend_tag, 'train')] = clf.predict(X_blend_train)
        model.preds[(blend_tag, 'test')] = clf.predict(X_blend_test)
        model.probas[(blend_tag, 'train')] = clf.predict_proba(X_blend_train)[:, 1]
        model.probas[(blend_tag, 'test')] = clf.predict_proba(X_blend_test)[:, 1]
    else:
        alphas = [0.0001, 0.005, 0.001, 0.005, 0.01, 0.05, 0.1, 0.5,
                  1.0, 5.0, 10.0, 50.0, 100.0, 500.0, 1000.0]    
        rcvr = RidgeCV(alphas=alphas, normalize=True, cv=n_folds)
        rcvr.fit(X_blend_train, y_train)
        model.estimators[blend_tag] = rcvr
        model.preds[(blend_tag, 'train')] = rcvr.predict(X_blend_train)
        model.preds[(blend_tag, 'test')] = rcvr.predict(X_blend_test)

    # Return the model with blended estimator and predictions.

    end_time = datetime.now()
    time_taken = end_time - start_time
    logger.info("Blending Complete: %s", time_taken)

    return model


#
# Function generate_metrics
#

def generate_metrics(model, partition='train'):

    # Extract data and model parameters.

    if partition == 'train':
        expected = model.y_train
    else:
        expected = model.y_test

    regression = model.specs['regression']

    # Generate Metrics

    if expected is not None:
        # get the metrics for each algorithm
        for algo in model.algolist:
            # get predictions for the given algorithm
            predicted = model.preds[(algo, partition)]
            if not regression:
                model.metrics[(algo, partition, 'accuracy')] = accuracy_score(expected, predicted)
                model.metrics[(algo, partition, 'precision')] = precision_score(expected, predicted)
                model.metrics[(algo, partition, 'recall')] = recall_score(expected, predicted)
                model.metrics[(algo, partition, 'f1')] = f1_score(expected, predicted)
                model.metrics[(algo, partition, 'confusion_matrix')] = confusion_matrix(expected, predicted)
                model.metrics[(algo, partition, 'roc_auc')] = roc_auc_score(expected, predicted)
            else:
                model.metrics[(algo, partition, 'mse')] = mean_squared_error(expected, predicted)
                model.metrics[(algo, partition, 'mae')] = mean_absolute_error(expected, predicted)
                model.metrics[(algo, partition, 'r2')] = r2_score(expected, predicted)
                model.metrics[(algo, partition, 'explained_variance')] = explained_variance_score(expected, predicted)
                model.metrics[(algo, partition, 'median_abs_error')] = median_absolute_error(expected, predicted)
        # log the metrics for each algorithm
        logger.info('='*80)
        logger.info("Metrics for Partition: %s", partition)
        for algo in model.algolist:
            logger.info('-'*80)
            logger.info("Algorithm: %s", algo)
            metrics = [(k[2], v) for k, v in model.metrics.iteritems() if k[0] == algo and k[1] == partition]
            for key, value in metrics:
                svalue = str(value)
                svalue.replace('\n', ' ')
                logger.info("%s: %s", key, svalue)
    else:
        logger.info("No labels are present to generate metrics")

    return model


#
# Function save_results
#

def save_results(model, tag, partition):
    """
    Save results in the given output file.
    """

    # Extract data and model parameters.

    X_train = model.X_train
    X_test = model.X_test

    predicted = model.preds[(tag, partition)]
    probas = model.probas[(tag, partition)]
    base_dir = model.specs['base_dir']
    project = model.specs['project']
    extension = model.specs['extension']
    separator = model.specs['separator']
    regression = model.specs['regression']

    # Get date stamp to record file creation

    d = datetime.now()
    f = "%m%d%y"

    # Save predictions and final features

    # training data
    # output_dir = SSEP.join([base_dir, project])
    # output_file = USEP.join(['train', d.strftime(f)])
    # output_file = PSEP.join([output_file, extension])
    # output = SSEP.join([output_dir, output_file])
    # np.savetxt(output, X_train, delimiter=separator)
    # test data
    # output_dir = SSEP.join([base_dir, project])
    # output_file = USEP.join(['test', d.strftime(f)])
    # output_file = PSEP.join([output_file, extension])
    # output = SSEP.join([output_dir, output_file])
    # np.savetxt(output, X_test, delimiter=separator)
    # predictions
    # output_dir = SSEP.join([base_dir, project])
    # output_file = USEP.join(['predictions', d.strftime(f)])
    # output_file = PSEP.join([output_file, extension])
    # output = SSEP.join([output_dir, output_file])
    # np.savetxt(output, preds, delimiter=separator)
    # probabilities
    if not regression:
        output_dir = SSEP.join([base_dir, project])
        output_file = USEP.join(['probas', d.strftime(f)])
        output_file = PSEP.join([output_file, extension])
        output = SSEP.join([output_dir, output_file])
        np.savetxt(output, probas, delimiter=separator)

    # Save model object

    # f = file('model.save', 'wb')
    # pickle.dump(model, f, protocol=pickle.HIGHEST_PROTOCOL)
    # f.close()

    # Open model object

    # f = file('model.save', 'rb')
    # model = pickle.load(f)
    # f.close()