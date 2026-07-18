# SmartDesk AI — Intelligent IT Help Desk

SmartDesk AI is a full-stack Flask final-year project that classifies natural-language IT complaints with TF-IDF vectors and cosine similarity, returns targeted troubleshooting guidance, and routes high-risk or uncertain requests into an administrator-managed ticket workflow.

## Core features

- Separate employee and administrator authentication
- Role-protected admin routes, CSRF protection and login throttling
- Live administrator-editable SQLite knowledge base
- NLP analysis showing intent, category, confidence and priority
- Automated escalation for security, hardware, access and unknown requests
- Professional `TKT-YYYYMMDD-XXXX` references
- Ticket filtering, status management and CSV export
- User feedback and administrator audit logging
- Responsive light product interface

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install --prefer-binary -r requirements.txt
python3 app.py
```

Open the URL printed in the terminal. The application automatically selects the next available port if port 5000 is occupied.

## Initial administrator setup

- Login URL: `/admin/login`
- Set `ADMIN_USERNAME`, `ADMIN_PASSWORD`, and `ADMIN_EMAIL` before the first production start.
- Render generates a private administrator password automatically; retrieve it from the service environment settings.

Always set a strong `SECRET_KEY`. New employees create their own accounts from `/register`.

## NLP pipeline

1. Lowercase and punctuation normalization
2. Unigram and bigram TF-IDF vectorization
3. Cosine similarity against knowledge-base sample queries
4. Highest-scoring intent selection
5. Confidence threshold and automated response/ticket routing

The live engine reads the `knowledge_base` SQLite table. Changes made in the Admin Knowledge Base screen take effect on the next request.

## Academic evaluation

Run:

```bash
python3 model/evaluate.py
```

This evaluates unseen complaint wording and produces `model/evaluation_results.json` plus `model/confusion_matrix.csv`. Include these results in the implementation/testing chapter of the report and discuss the misclassified examples as limitations.

Run the regression suite with:

```bash
python3 -m unittest discover -s tests -v
```

## Deployment

The included `render.yaml` supports a GitHub-to-Render deployment. Free Render services use temporary local storage, so SQLite data can reset after restarts. A lasting production deployment should use persistent storage or migrate SQLite to PostgreSQL.
