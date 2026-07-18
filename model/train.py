import json
import pickle
import os
import numpy as np

import nltk
from nltk.stem import WordNetLemmatizer
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder

# Download required NLTK data
nltk.download('punkt', quiet=True)
nltk.download('wordnet', quiet=True)
nltk.download('stopwords', quiet=True)
nltk.download('averaged_perceptron_tagger', quiet=True)
nltk.download('punkt_tab', quiet=True)

lemmatizer = WordNetLemmatizer()
stop_words = set(stopwords.words('english'))


def preprocess(text):
    """Tokenize, lowercase, remove stopwords, lemmatize."""
    tokens = word_tokenize(text.lower())
    tokens = [lemmatizer.lemmatize(t) for t in tokens if t.isalpha() and t not in stop_words]
    return ' '.join(tokens)


def load_intents(path):
    with open(path, 'r') as f:
        data = json.load(f)
    return data['intents']


def train_model():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    intents_path = os.path.join(base_dir, 'data', 'intents.json')
    model_dir = os.path.dirname(os.path.abspath(__file__))

    intents = load_intents(intents_path)

    X = []  # preprocessed patterns
    y = []  # intent tags

    for intent in intents:
        for pattern in intent['patterns']:
            X.append(preprocess(pattern))
            y.append(intent['tag'])

    print(f"Training on {len(X)} patterns across {len(set(y))} intents...")

    # Vectorizer
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), max_features=5000)

    # Classifier
    classifier = LinearSVC(C=1.0, max_iter=2000)

    X_vec = vectorizer.fit_transform(X)
    classifier.fit(X_vec, y)

    # Save models
    vec_path = os.path.join(model_dir, 'vectorizer.pkl')
    clf_path = os.path.join(model_dir, 'classifier.pkl')

    with open(vec_path, 'wb') as f:
        pickle.dump(vectorizer, f)

    with open(clf_path, 'wb') as f:
        pickle.dump(classifier, f)

    print(f"Model trained and saved to {model_dir}")
    print(f"Intents: {sorted(set(y))}")


if __name__ == '__main__':
    train_model()
