import functools

import datetime

import gensim
import numpy
from keras import Input, Model
from keras.callbacks import ModelCheckpoint
from keras.layers import concatenate, Dense
from keras.preprocessing import sequence
from keras.utils import plot_model
from keras.wrappers.scikit_learn import KerasClassifier
from sklearn import svm
from sklearn.decomposition import PCA
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis

from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.linear_model import SGDClassifier
from sklearn.model_selection import cross_val_predict, StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelBinarizer

from classifier import classifier_util as util
import os
from classifier import dnn_util as dmc

RANDOM_SEED = 1
RANDOM_STATE = 42


def create_feature_reduction_alg(feature_reduction, max_feature=None):
    if feature_reduction == "pca":
        if max_feature is not None and max_feature > 2000:
            return 'pca', PCA(n_components=1000)
        elif max_feature is not None and max_feature < 2000:
            return 'pca', PCA(n_components=int(max_feature / 2))
        else:
            return 'pca', PCA(n_components=1000)
    else:
        return 'lda', LinearDiscriminantAnalysis(n_components=300)


'''if nfold is none, the method will fit on the entire X_train data and a model file
will be saved. If nfold is an integer, the model will perform cross fold valiation and 
results will be saved'''


def learn_discriminative(cpus, task, model,
                         X_train, y_train,
                         identifier, outfolder, nfold=None, feature_reduction=None):
    classifier = None
    model_file = None

    if (model == "rf"):
        print("== Random Forest ...")
        cls = RandomForestClassifier(n_estimators=20, n_jobs=cpus)
        # rfc_tuning_params = {"max_depth": [3, 5, None],
        #                      "max_features": [1, 3, 5, 7, 10],
        #                      "min_samples_split": [2, 5, 10],
        #                      "min_samples_leaf": [1, 3, 10],
        #                      "bootstrap": [True, False],
        #                      "criterion": ["gini", "entropy"]}
        if feature_reduction is not None:
            fr = create_feature_reduction_alg(feature_reduction, len(X_train[0]))
            print("\t using " + str(fr[1]))
            pipe = Pipeline([(fr[0], fr[1]), ('rf', cls)])
            classifier = pipe
        else:
            classifier = cls
        model_file = os.path.join(outfolder, "random-forest_classifier-%s.m" % task)
    if (model == "svm-l"):
        print("== SVM, kernel=linear ...")
        cls = svm.LinearSVC(class_weight='balanced', C=0.01, penalty='l2', loss='squared_hinge',
                            multi_class='ovr')
        if feature_reduction is not None:
            fr = create_feature_reduction_alg(feature_reduction, len(X_train[0]))
            print("\t using " + str(fr[1]))
            pipe = Pipeline([(fr[0], fr[1]), ('rf', cls)])
            classifier = pipe
        else:
            classifier = cls
        model_file = os.path.join(outfolder, "liblinear-svm-linear-%s.m" % task)

    if (model == "svm-rbf"):
        # tuned_parameters = [{'gamma': np.logspace(-9, 3, 3), 'probability': [True], 'C': np.logspace(-2, 10, 3)},
        #                     {'C': [1e-1, 1e-3, 1e-5, 0.2, 0.5, 1, 1.2, 1.3, 1.5, 1.6, 1.7, 1.8, 2]}]
        print("== SVM, kernel=rbf ...")
        cls = svm.SVC()
        if feature_reduction is not None:
            fr = create_feature_reduction_alg(feature_reduction, len(X_train[0]))
            pipe = Pipeline([(fr[0], fr[1]), ('rf', cls)])
            print("\t using " + str(fr[1]))
            classifier = pipe
        else:
            classifier = cls
        model_file = os.path.join(outfolder, "liblinear-svm-rbf-%s.m" % task)

    if nfold is not None:
        nfold_predictions = cross_val_predict(classifier, X_train, y_train, cv=nfold)
        util.save_classifier_model(classifier, model_file)
        util.save_scores(nfold_predictions, y_train, model, task,
                         identifier, 2, outfolder)
    else:
        classifier.fit(X_train, y_train)
        util.save_classifier_model(classifier, model_file)


def learn_generative(cpus, task, model_flag, X_train, y_train,
                     identifier, outfolder, nfold=None, feature_reduction=None):
    classifier = None
    model_file = None
    if (model_flag == "sgd"):
        print("== SGD ...")
        # "loss": ["log", "modified_huber", "squared_hinge", 'squared_loss'],
        #               "penalty": ['l2', 'l1'],
        #               "alpha": [0.0001, 0.001, 0.01, 0.03, 0.05, 0.1],
        #               "n_iter": [1000],
        #               "learning_rate": ["optimal"]}
        cls = SGDClassifier(loss='log', penalty='l2', n_jobs=cpus)
        if feature_reduction is not None:
            fr = create_feature_reduction_alg(feature_reduction, len(X_train[0]))
            print("\t using " + str(fr[1]))
            pipe = Pipeline([(fr[0], fr[1]), ('rf', cls)])
            classifier = pipe
        else:
            classifier = cls
        model_file = os.path.join(outfolder, "sgd-classifier-%s.m" % task)
    if (model_flag == "lr"):
        print("== Stochastic Logistic Regression ...")

        cls = LogisticRegression(random_state=111)
        if feature_reduction is not None:
            fr = create_feature_reduction_alg(feature_reduction, len(X_train[0]))
            print("\t using " + str(fr[1]))
            pipe = Pipeline([(fr[0], fr[1]), ('rf', cls)])
            classifier = pipe
        else:
            classifier = cls
        model_file = os.path.join(outfolder, "stochasticLR-%s.m" % task)

    if nfold is not None:
        print(y_train.shape)
        nfold_predictions = cross_val_predict(classifier, X_train, y_train, cv=nfold)
        util.save_scores(nfold_predictions, y_train, model_flag, task, identifier, 2, outfolder)
    else:
        classifier.fit(X_train, y_train)
        util.save_classifier_model(classifier, model_file)



'''
X_train_metafeature: these are features that the model should take as-is, without passing through any hidden layers.
This can be None, in which case, only text data are processed to extract features

text_data_extra_for_embedding_vocab: (usually you do not need to provide this; also
this workds only with pre-trained embeddings) when we train a model to be later loaded to predict new data, the new data 
can have unseen words. When an embedding layer is used in the model, it takes a parameter of 'vocab'
and 'weights' of these vocab. Typically these are based on the training data. But we can
force this layer to 'remember' more words and their weights. To improve the model performance, 
by injecting additional text data that are not labeled. This 'text_data_extra' and 'text_data'
will both be processed to extract words, which are indexed and stored in the embedding layer.
But only 'text_data' that has labels are in fact used for training a model. 
'''
def learn_dnn(nfold, task,
              embedding_model_file,
              text_data, X_train_metafeature, y_train,
              model_descriptor, outfolder, prediction_targets,
              text_data_extra_for_embedding_vocab=None):
    print("== Perform ANN ...")  # create model

    #process text data, index vocabulary, pad each text sentence/paragraph to a fixed length
    M = dmc.get_word_vocab(text_data, 1, tweets_extra=text_data_extra_for_embedding_vocab)
    X_train_textfeature = M[0]
    X_train_textfeature = sequence.pad_sequences(X_train_textfeature,
                                                 dmc.DNN_MAX_SEQUENCE_LENGTH)
    #load pre-trained word embedding model
    gensimFormat = ".gensim" in embedding_model_file
    if gensimFormat:
        pretrained_embedding_models = gensim.models.KeyedVectors.load(embedding_model_file, mmap='r')
    else:
        pretrained_embedding_models = gensim.models.KeyedVectors. \
            load_word2vec_format(embedding_model_file, binary=True)

    #create the embedding layer by mapping each input sentence sequence to embedding representations by
    #looking up its containing words in the pre-trained embedding model
    pretrained_word_matrix = dmc.build_pretrained_embedding_matrix(M[1],
                                                                   pretrained_embedding_models,
                                                                   dmc.DNN_EMBEDDING_DIM,
                                                                   2)

    encoder = LabelBinarizer()
    y_train_int = encoder.fit_transform(y_train)

    #now let's assemble the model based ont he descriptor
    model_text_inputs = Input(shape=(dmc.DNN_MAX_SEQUENCE_LENGTH,)) #model input
    model_text = dmc.create_submodel_textfeature( #this parses 'model_descriptor' and takes the text-based features as input to the model
        model_text_inputs,              #it is useful to see the details of this method and try a few different options to see difference
        len(M[1]),
        dmc.DNN_EMBEDDING_DIM, dmc.DNN_MAX_SEQUENCE_LENGTH,
        pretrained_word_matrix,
        model_descriptor)

    if X_train_metafeature is not None: #if we also want to use other features together with text-based, concatenate them as-is
        model_metafeature_inputs = Input(shape=(len(X_train_metafeature[0]),))
        model_metafeature = \
            dmc.create_submodel_metafeature(model_metafeature_inputs, 20)
        merge = concatenate([model_text, model_metafeature])
        final = Dense(prediction_targets, activation="softmax")(merge)
        model = Model(inputs=[model_text_inputs, model_metafeature_inputs], outputs=final)
        X_merge = numpy.concatenate([X_train_textfeature, X_train_metafeature], axis=1)
    else:
        print("--- using text features only ---")
        final = Dense(prediction_targets, activation="softmax")(model_text)
        model = Model(inputs=model_text_inputs, outputs=final)
        X_merge = X_train_textfeature

    #this prints the model architecture diagram to a file, so you can check that it looks right
    plot_model(model, to_file="model.png")
    model.compile(loss='categorical_crossentropy', optimizer='adam', metrics=['accuracy'])

    model_file = os.path.join(outfolder, "ann-%s.m" % task)

    #perform n-fold validation (we cant use scikit-learn's wrapper as we used Keras functional api above
    if nfold is not None:
        kfold = StratifiedKFold(n_splits=nfold, shuffle=True, random_state=RANDOM_STATE)
        splits = list(enumerate(kfold.split(X_merge, y_train_int.argmax(1))))

        nfold_predictions = dict()
        for k in range(0, len(splits)):
            # Fit the model
            X_train_index = splits[k][1][0]
            X_test_index = splits[k][1][1]

            X_train_merge_ = X_merge[X_train_index]
            X_test_merge_ = X_merge[X_test_index]
            y_train_ = y_train_int[X_train_index]

            X_train_text_feature = X_train_merge_[:, 0:len(X_train_textfeature[0])]
            X_train_meta_feature = X_train_merge_[:, len(X_train_text_feature[0]):]

            # y_test = y_train[X_test_index]
            X_test_text_feature = X_test_merge_[:, 0:len(X_train_textfeature[0])]
            X_test_meta_feature = X_test_merge_[:, len(X_train_textfeature[0]):]

            if X_train_metafeature is not None:
                model.fit([X_train_text_feature, X_train_meta_feature],
                          y_train_, epochs=dmc.DNN_EPOCHES, batch_size=dmc.DNN_BATCH_SIZE, verbose=2)
                prediction_prob = model.predict([X_test_text_feature, X_test_meta_feature])

            else:
                model.fit(X_train_text_feature,
                          y_train_, epochs=dmc.DNN_EPOCHES, batch_size=dmc.DNN_BATCH_SIZE, verbose=2)
                prediction_prob = model.predict(X_test_text_feature)
            # evaluate the model
            #
            predictions = prediction_prob.argmax(axis=-1)

            for i, l in zip(X_test_index, predictions):
                nfold_predictions[i] = l

            # self.save_classifier_model(best_estimator, ann_model_file)

        indexes = sorted(list(nfold_predictions.keys()))
        predicted_labels = []
        for i in indexes:
            predicted_labels.append(nfold_predictions[i])
        util.save_scores(predicted_labels, y_train_int.argmax(1), "dnn", task, model_descriptor, 2,
                         outfolder)
    else:
        if X_train_metafeature is not None:
            model.fit([X_train_textfeature, X_train_metafeature],
                  y_train_int, epochs=dmc.DNN_EPOCHES, batch_size=dmc.DNN_BATCH_SIZE, verbose=2)
        else:
            model.fit(X_train_textfeature,
                      y_train_int, epochs=dmc.DNN_EPOCHES, batch_size=dmc.DNN_BATCH_SIZE, verbose=2)

        # serialize model to YAML
        model_yaml = model.to_yaml()
        with open(model_file + ".yaml", "w") as yaml_file:
            yaml_file.write(model_yaml)
        # serialize weights to HDF5
        model.save_weights(model_file + ".h5")
        # util.save_classifier_model(model, model_file)
