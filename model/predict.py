"""SmartDesk runtime NLP: normalize → TF-IDF → cosine similarity → intent."""
import json
import os
import random
import re
import sqlite3
from contextlib import closing

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTENTS_PATH = os.path.join(BASE_DIR, "data", "intents.json")
DB_PATH = os.path.join(BASE_DIR, "database", "smartdesk.db")

with open(INTENTS_PATH, encoding="utf-8") as file:
    INTENTS = json.load(file)["intents"]

def normalize(text):
    return re.sub(r"[^a-z0-9\s]", " ", (text or "").lower()).strip()

_engine = {"signature": None}

def _runtime_intents():
    """Load the administrator-editable KB, falling back to the bundled JSON."""
    if os.path.exists(DB_PATH):
        with closing(sqlite3.connect(DB_PATH)) as db:
            rows = db.execute("SELECT intent, patterns, response FROM knowledge_base ORDER BY id").fetchall()
        if rows:
            return [{"tag": row[0], "patterns": [p.strip() for p in row[1].split("|") if p.strip()],
                     "responses": [row[2]]} for row in rows]
    return INTENTS

def _get_engine():
    files = (DB_PATH, DB_PATH + "-wal")
    signature = tuple((os.path.getmtime(path), os.path.getsize(path)) if os.path.exists(path) else (0, 0) for path in files)
    if _engine.get("signature") != signature:
        intents = _runtime_intents()
        patterns = [(intent, pattern) for intent in intents for pattern in intent["patterns"]]
        vectorizer = TfidfVectorizer(preprocessor=normalize, ngram_range=(1, 2), sublinear_tf=True)
        matrix = vectorizer.fit_transform([pattern for _, pattern in patterns])
        _engine.update(signature=signature, patterns=patterns, vectorizer=vectorizer, matrix=matrix)
    return _engine

ROUTING = {
    "greeting": ("General", "Low", False), "goodbye": ("General", "Low", False),
    "password_reset": ("Account", "Medium", False), "account_locked": ("Account", "High", True),
    "two_factor_issue": ("Account", "High", True), "login_problem": ("Account", "Medium", False),
    "network_issue": ("Network", "Medium", False), "vpn_issue": ("Network", "High", False),
    "printer_problem": ("Hardware", "Medium", False), "slow_computer": ("Hardware", "Medium", False),
    "hardware_fault": ("Hardware", "High", True), "overheating": ("Hardware", "High", True),
    "blue_screen": ("Hardware", "High", True), "software_install": ("Software", "Medium", True),
    "software_crash": ("Software", "Medium", False), "windows_update": ("Software", "Low", False),
    "email_issue": ("Email", "Medium", False), "storage_full": ("Hardware", "Medium", False),
    "audio_issue": ("Hardware", "Medium", False), "camera_issue": ("Hardware", "Medium", False),
    "virus_malware": ("Security", "Critical", True), "phishing": ("Security", "Critical", True),
    "raise_ticket": ("General", "Medium", True),
}

# Domain vocabulary boosts help short, conversational complaints whose key nouns
# are rare in the small academic corpus. TF-IDF remains the primary score.
KEYWORDS = {
    "greeting": ("hello", "hi", "good morning", "good afternoon"),
    "password_reset": ("password", "forgot password", "password expired"),
    "account_locked": ("locked out", "account locked", "account disabled"),
    "two_factor_issue": ("2fa", "two factor", "authenticator", "verification code", "mfa"),
    "login_problem": ("login", "sign in", "signed out", "credentials", "session"),
    "network_issue": ("wifi", "wireless", "internet", "ethernet", "network"),
    "vpn_issue": ("vpn", "remote access", "tunnel"),
    "printer_problem": ("printer", "printing", "print queue", "out of paper"),
    "email_issue": ("email", "outlook", "mailbox", "inbox", "outbox"),
    "audio_issue": ("microphone", "speaker", "sound", "audio", "headset"),
    "camera_issue": ("camera", "webcam", "video is black"),
    "software_crash": ("app crashes", "application closes", "program freezes", "not responding"),
    "software_install": ("install", "software request", "new application", "need software"),
    "windows_update": ("update", "windows update", "mac update"),
    "storage_full": ("storage", "disk", "drive", "no room", "space left"),
    "overheating": ("overheat", "very hot", "fan is loud", "burning hot"),
    "blue_screen": ("blue screen", "stop code", "boot loop", "will not boot"),
    "phishing": ("phishing", "fake page", "suspicious attachment", "entered credentials"),
    "virus_malware": ("virus", "malware", "ransomware", "antivirus"),
    "hardware_fault": ("cracked", "broken", "hardware", "keyboard keys"),
}

def predict(text):
    clean = normalize(text)
    if not clean:
        return fallback(0.0)
    engine = _get_engine()
    scores = cosine_similarity(engine["vectorizer"].transform([clean]), engine["matrix"])[0]
    intent_scores = {}
    intent_objects = {}
    for score, (candidate, _) in zip(scores, engine["patterns"]):
        tag = candidate["tag"]
        intent_scores[tag] = max(intent_scores.get(tag, 0.0), float(score))
        intent_objects[tag] = candidate
    for tag, terms in KEYWORDS.items():
        hits = sum(bool(re.search(r"\b" + re.escape(term) + r"\b", clean)) for term in terms)
        if hits:
            intent_scores[tag] = intent_scores.get(tag, 0.0) + min(0.42, 0.28 + 0.07 * (hits - 1))
    best_tag = max(intent_scores, key=intent_scores.get)
    confidence = min(1.0, intent_scores[best_tag])
    if confidence < 0.22:
        return fallback(confidence)
    intent = intent_objects[best_tag]
    category, priority, always_escalate = ROUTING.get(intent["tag"], ("General", "Medium", False))
    return {
        "intent": intent["tag"], "confidence": confidence,
        "response": random.choice(intent["responses"]),
        "category": category, "priority": priority,
        "escalate": always_escalate, "processed_text": clean,
    }

def fallback(confidence):
    return {
        "intent": "unknown", "confidence": confidence, "category": "General",
        "priority": "Medium", "escalate": True,
        "response": "I could not identify the issue confidently. Please include the device or application name, what you expected, and any error message. I have also created a ticket for an IT specialist.",
        "processed_text": "",
    }

if __name__ == "__main__":
    for query in ("forgot my password", "wifi keeps disconnecting", "laptop is hot", "camera not working", "clicked a phishing link"):
        print(query, predict(query))
