import os
import sys
import json
import sqlite3
import bcrypt
import random
import csv
import io
import secrets
import time
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, jsonify, flash, g
)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'smartdesk-secret-key-change-in-prod-2024')
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')
if os.environ.get('FLASK_ENV') == 'production':
    app.config['SESSION_COOKIE_SECURE'] = True

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'database', 'smartdesk.db')

# ──────────────────────────────────────────────
# DATABASE
# ──────────────────────────────────────────────

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db


@app.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL,
            priority TEXT DEFAULT 'Medium',
            status TEXT DEFAULT 'Open',
            admin_notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            sender TEXT NOT NULL,
            message TEXT NOT NULL,
            intent TEXT DEFAULT '',
            confidence REAL DEFAULT 0.0,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS knowledge_base (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            intent TEXT NOT NULL,
            patterns TEXT NOT NULL,
            response TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            rating INTEGER NOT NULL,
            comment TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (ticket_id) REFERENCES tickets(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            details TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    ''')

    # Seed admin user
    admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
    admin_password = os.environ.get('ADMIN_PASSWORD', 'change-me-before-deployment')
    admin_email = os.environ.get('ADMIN_EMAIL', 'admin@smartdesk.local')
    admin_pw = bcrypt.hashpw(admin_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    cur.execute('''
        INSERT OR IGNORE INTO users (username, email, password, role)
        VALUES (?, ?, ?, ?)
    ''', (admin_username, admin_email, admin_pw, 'admin'))

    # Seed knowledge base from intents.json
    intents_path = os.path.join(BASE_DIR, 'data', 'intents.json')
    if os.path.exists(intents_path):
        with open(intents_path) as f:
            data = json.load(f)
        for intent in data['intents']:
            patterns_str = ' | '.join(intent['patterns'])
            response_str = intent['responses'][0]
            exists = cur.execute("SELECT 1 FROM knowledge_base WHERE intent=?", (intent['tag'],)).fetchone()
            if not exists:
                cur.execute(
                    "INSERT INTO knowledge_base (intent, patterns, response) VALUES (?, ?, ?)",
                    (intent['tag'], patterns_str, response_str)
                )

    conn.commit()
    conn.close()
    print("Database initialised.")


# ──────────────────────────────────────────────
# AUTH DECORATORS
# ──────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to continue.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_urlsafe(32)
    return session['_csrf_token']


app.jinja_env.globals['csrf_token'] = csrf_token


@app.before_request
def csrf_protect():
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        supplied = request.headers.get('X-CSRF-Token') or request.form.get('_csrf_token')
        if not supplied or not secrets.compare_digest(supplied, session.get('_csrf_token', '')):
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Security token expired. Refresh the page and try again.'}), 400
            flash('Your session security token expired. Please try again.', 'warning')
            return redirect(request.referrer or url_for('login'))


def log_action(action, details=''):
    db = get_db()
    db.execute("INSERT INTO audit_log(user_id, action, details) VALUES(?,?,?)",
               (session.get('user_id'), action, details))
    db.commit()


def ticket_ref(ticket):
    created = ticket['created_at'] if ticket and ticket['created_at'] else ''
    digits = ''.join(ch for ch in str(created)[:10] if ch.isdigit()) or datetime.now().strftime('%Y%m%d')
    return f"TKT-{digits}-{int(ticket['id']):04d}"


app.jinja_env.globals['ticket_ref'] = ticket_ref


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('chat'))
        return f(*args, **kwargs)
    return decorated


# ──────────────────────────────────────────────
# AUTH ROUTES
# ──────────────────────────────────────────────

@app.route('/')
def index():
    if 'user_id' in session:
        if session.get('role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('chat'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').encode('utf-8')
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        failures = session.get('login_failures', [])
        failures = [stamp for stamp in failures if time.time() - stamp < 300]
        if len(failures) >= 5:
            flash('Too many failed attempts. Please wait five minutes.', 'danger')
            return render_template('login.html'), 429
        if user and user['role'] == 'user' and bcrypt.checkpw(password, user['password'].encode('utf-8')):
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            return redirect(url_for('chat'))
        failures.append(time.time()); session['login_failures'] = failures
        flash('Invalid username or password.', 'danger')
    return render_template('login.html')


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').encode('utf-8')
        user = get_db().execute("SELECT * FROM users WHERE username=? AND role='admin'", (username,)).fetchone()
        failures = session.get('admin_login_failures', [])
        failures = [stamp for stamp in failures if time.time() - stamp < 300]
        if len(failures) >= 5:
            flash('Too many failed attempts. Please wait five minutes.', 'danger')
            return render_template('admin_login.html'), 429
        if user and bcrypt.checkpw(password, user['password'].encode('utf-8')):
            session.clear()
            session.update(user_id=user['id'], username=user['username'], role='admin')
            return redirect(url_for('admin_dashboard'))
        failures.append(time.time()); session['admin_login_failures'] = failures
        flash('Invalid administrator credentials.', 'danger')
    return render_template('admin_login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        confirm = request.form.get('confirm_password', '').strip()

        if not all([username, email, password, confirm]):
            flash('All fields are required.', 'danger')
            return render_template('register.html')

        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('register.html')

        if len(password) < 8 or not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
            flash('Password must be at least 8 characters and contain letters and numbers.', 'danger')
            return render_template('register.html')

        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        db = get_db()
        try:
            db.execute(
                "INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, 'user')",
                (username, email, hashed)
            )
            db.commit()
            log_action('User registered', username)
            flash('Account created! You can now log in.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username or email already exists.', 'danger')

    return render_template('register.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


# ──────────────────────────────────────────────
# CHAT ROUTE
# ──────────────────────────────────────────────

@app.route('/chat')
@login_required
def chat():
    return render_template('chat.html', username=session['username'])


@app.route('/api/chat', methods=['POST'])
@login_required
def api_chat():
    data = request.get_json()
    user_message = data.get('message', '').strip()
    if not user_message:
        return jsonify({'error': 'Empty message'}), 400

    user_id = session['user_id']
    db = get_db()

    # Save user message
    db.execute(
        "INSERT INTO messages (user_id, sender, message) VALUES (?, 'user', ?)",
        (user_id, user_message)
    )

    # Predict intent
    try:
        from model.predict import predict
        result = predict(user_message)
        intent = result['intent']
        confidence = result['confidence']
        response = result['response']
        category = result.get('category', 'General')
        priority = result.get('priority', 'Medium')
        escalate = result['escalate']
    except Exception as e:
        intent = 'unknown'
        confidence = 0.0
        response = "I'm having trouble understanding right now. Please raise a ticket and an agent will help you."
        category = 'General'
        priority = 'Medium'
        escalate = True

    # Save bot message
    db.execute(
        "INSERT INTO messages (user_id, sender, message, intent, confidence) VALUES (?, 'bot', ?, ?, ?)",
        (user_id, response, intent, confidence)
    )

    ticket_id = None
    if escalate:
        # Auto-create escalation ticket
        ticket = db.execute(
            '''INSERT INTO tickets (user_id, title, description, category, priority, status)
               VALUES (?, ?, ?, ?, ?, ?)''',
            (
                user_id,
                f"Auto-escalated: {user_message[:80]}",
                user_message,
                category,
                priority,
                'Escalated'
            )
        )
        ticket_id = ticket.lastrowid
        created_ticket = db.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        reference = ticket_ref(created_ticket)
        response += f" A support ticket ({reference}) has been created and routed to the {category} team."

    db.commit()

    return jsonify({
        'response': response,
        'intent': intent,
        'confidence': round(confidence, 3),
        'escalate': escalate,
        'ticket_id': reference if ticket_id else None
        ,'category': category
        ,'priority': priority
    })


# ──────────────────────────────────────────────
# TICKETS (USER)
# ──────────────────────────────────────────────

@app.route('/tickets')
@login_required
def tickets():
    db = get_db()
    user_tickets = db.execute(
        "SELECT * FROM tickets WHERE user_id = ? ORDER BY created_at DESC",
        (session['user_id'],)
    ).fetchall()
    return render_template('tickets.html', tickets=user_tickets)


@app.route('/submit-ticket', methods=['GET', 'POST'])
@login_required
def submit_ticket():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        category = request.form.get('category', 'General')
        priority = request.form.get('priority', 'Medium')

        if not title or not description:
            flash('Title and description are required.', 'danger')
            return render_template('submit_ticket.html')

        db = get_db()
        db.execute(
            "INSERT INTO tickets (user_id, title, description, category, priority) VALUES (?, ?, ?, ?, ?)",
            (session['user_id'], title, description, category, priority)
        )
        db.commit()
        flash('Ticket submitted successfully!', 'success')
        return redirect(url_for('tickets'))

    return render_template('submit_ticket.html')


@app.route('/feedback/<int:ticket_id>', methods=['GET', 'POST'])
@login_required
def feedback(ticket_id):
    db = get_db()
    ticket = db.execute(
        "SELECT * FROM tickets WHERE id = ? AND user_id = ?",
        (ticket_id, session['user_id'])
    ).fetchone()

    if not ticket:
        flash('Ticket not found.', 'danger')
        return redirect(url_for('tickets'))

    if ticket['status'] != 'Resolved':
        flash('Feedback can only be submitted for resolved tickets.', 'warning')
        return redirect(url_for('tickets'))

    if request.method == 'POST':
        rating = request.form.get('rating')
        comment = request.form.get('comment', '').strip()
        if not rating:
            flash('Please select a rating.', 'danger')
            return render_template('feedback.html', ticket=ticket)
        existing = db.execute("SELECT 1 FROM feedback WHERE ticket_id=? AND user_id=?", (ticket_id, session['user_id'])).fetchone()
        if existing:
            flash('You have already rated this ticket.', 'warning')
            return redirect(url_for('tickets'))
        db.execute(
            "INSERT INTO feedback (ticket_id, user_id, rating, comment) VALUES (?, ?, ?, ?)",
            (ticket_id, session['user_id'], int(rating), comment)
        )
        db.commit()
        flash('Thank you for your feedback!', 'success')
        return redirect(url_for('tickets'))

    return render_template('feedback.html', ticket=ticket)


# ──────────────────────────────────────────────
# ADMIN ROUTES
# ──────────────────────────────────────────────

@app.route('/admin')
@admin_required
def admin_dashboard():
    db = get_db()
    stats = {
        'total': db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0],
        'open': db.execute("SELECT COUNT(*) FROM tickets WHERE status='Open'").fetchone()[0],
        'in_progress': db.execute("SELECT COUNT(*) FROM tickets WHERE status='In Progress'").fetchone()[0],
        'resolved': db.execute("SELECT COUNT(*) FROM tickets WHERE status='Resolved'").fetchone()[0],
        'escalated': db.execute("SELECT COUNT(*) FROM tickets WHERE status='Escalated'").fetchone()[0],
    }
    escalated_tickets = db.execute(
        '''SELECT t.*, u.username FROM tickets t
           JOIN users u ON t.user_id = u.id
           WHERE t.status = 'Escalated'
           ORDER BY t.created_at DESC LIMIT 10'''
    ).fetchall()
    recent_tickets = db.execute(
        '''SELECT t.*, u.username FROM tickets t
           JOIN users u ON t.user_id = u.id
           ORDER BY t.created_at DESC LIMIT 5'''
    ).fetchall()
    recent_activity = db.execute('''SELECT a.*, COALESCE(u.username, 'System') username
        FROM audit_log a LEFT JOIN users u ON a.user_id=u.id
        ORDER BY a.created_at DESC LIMIT 10''').fetchall()
    return render_template('admin_dashboard.html', stats=stats,
                           escalated_tickets=escalated_tickets,
                           recent_tickets=recent_tickets, recent_activity=recent_activity)


@app.route('/admin/tickets')
@admin_required
def admin_tickets():
    db = get_db()
    status_filter = request.args.get('status', '')
    category_filter = request.args.get('category', '')

    query = '''SELECT t.*, u.username FROM tickets t
               JOIN users u ON t.user_id = u.id WHERE 1=1'''
    params = []
    if status_filter:
        query += " AND t.status = ?"
        params.append(status_filter)
    if category_filter:
        query += " AND t.category = ?"
        params.append(category_filter)
    query += " ORDER BY t.created_at DESC"

    all_tickets = db.execute(query, params).fetchall()
    categories = ['General', 'Network', 'Hardware', 'Software', 'Email', 'Account', 'Security', 'Other']
    statuses = ['Open', 'In Progress', 'Resolved', 'Escalated', 'Closed']
    return render_template('admin_tickets.html', tickets=all_tickets,
                           categories=categories, statuses=statuses,
                           status_filter=status_filter, category_filter=category_filter)


@app.route('/admin/tickets/<int:ticket_id>', methods=['GET', 'POST'])
@admin_required
def admin_ticket_detail(ticket_id):
    db = get_db()
    if request.method == 'POST':
        new_status = request.form.get('status')
        admin_notes = request.form.get('admin_notes', '')
        db.execute(
            "UPDATE tickets SET status=?, admin_notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (new_status, admin_notes, ticket_id)
        )
        db.commit()
        log_action('Ticket updated', f'{ticket_ref({"id": ticket_id, "created_at": datetime.now().isoformat()})} → {new_status}')
        flash('Ticket updated.', 'success')
        return redirect(url_for('admin_ticket_detail', ticket_id=ticket_id))

    ticket = db.execute(
        '''SELECT t.*, u.username, u.email FROM tickets t
           JOIN users u ON t.user_id = u.id WHERE t.id = ?''', (ticket_id,)
    ).fetchone()
    if not ticket:
        flash('Ticket not found.', 'danger')
        return redirect(url_for('admin_tickets'))

    statuses = ['Open', 'In Progress', 'Resolved', 'Escalated', 'Closed']
    return render_template('admin_ticket_detail.html', ticket=ticket, statuses=statuses)


@app.route('/admin/kb')
@admin_required
def admin_kb():
    db = get_db()
    kb_items = db.execute("SELECT * FROM knowledge_base ORDER BY intent").fetchall()
    return render_template('admin_kb.html', kb_items=kb_items)


@app.route('/admin/kb/add', methods=['POST'])
@admin_required
def admin_kb_add():
    intent = request.form.get('intent', '').strip()
    patterns = request.form.get('patterns', '').strip()
    response = request.form.get('response', '').strip()
    if intent and patterns and response:
        db = get_db()
        db.execute(
            "INSERT INTO knowledge_base (intent, patterns, response) VALUES (?, ?, ?)",
            (intent, patterns, response)
        )
        db.commit()
        log_action('Knowledge entry added', intent)
        flash('Knowledge base entry added.', 'success')
    else:
        flash('All fields required.', 'danger')
    return redirect(url_for('admin_kb'))


@app.route('/admin/kb/edit/<int:kb_id>', methods=['POST'])
@admin_required
def admin_kb_edit(kb_id):
    intent = request.form.get('intent', '').strip()
    patterns = request.form.get('patterns', '').strip()
    response = request.form.get('response', '').strip()
    if intent and patterns and response:
        db = get_db()
        db.execute(
            "UPDATE knowledge_base SET intent=?, patterns=?, response=? WHERE id=?",
            (intent, patterns, response, kb_id)
        )
        db.commit()
        log_action('Knowledge entry updated', intent)
        flash('Knowledge base entry updated.', 'success')
    else:
        flash('All fields required.', 'danger')
    return redirect(url_for('admin_kb'))


@app.route('/admin/kb/delete/<int:kb_id>', methods=['POST'])
@admin_required
def admin_kb_delete(kb_id):
    db = get_db()
    item = db.execute("SELECT intent FROM knowledge_base WHERE id=?", (kb_id,)).fetchone()
    db.execute("DELETE FROM knowledge_base WHERE id=?", (kb_id,))
    db.commit()
    log_action('Knowledge entry deleted', item['intent'] if item else str(kb_id))
    flash('Entry deleted.', 'success')
    return redirect(url_for('admin_kb'))


@app.route('/admin/users')
@admin_required
def admin_users():
    db = get_db()
    users = db.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    return render_template('admin_users.html', users=users)


@app.route('/admin/tickets/export')
@admin_required
def admin_tickets_export():
    data = get_db().execute('''SELECT t.*, u.username, u.email FROM tickets t
        JOIN users u ON t.user_id=u.id ORDER BY t.created_at DESC''').fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Ticket Reference','User','Email','Title','Description','Category','Priority','Status','Created'])
    for row in data:
        writer.writerow([ticket_ref(row),row['username'],row['email'],row['title'],row['description'],row['category'],row['priority'],row['status'],row['created_at']])
    log_action('Tickets exported', f'{len(data)} records')
    return app.response_class(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition':'attachment; filename=smartdesk-tickets.csv'})


@app.errorhandler(404)
def not_found(error):
    return render_template('error.html', code=404, title='Page not found', message='The page you requested does not exist.'), 404


@app.errorhandler(500)
def server_error(error):
    return render_template('error.html', code=500, title='Something went wrong', message='SmartDesk could not complete that request. Please try again.'), 500


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

init_db()

if __name__ == '__main__':
    preferred = int(os.environ.get('PORT', '5000'))
    port = preferred
    import socket
    if 'PORT' not in os.environ:
        for candidate in range(preferred, preferred + 20):
            with socket.socket() as probe:
                try:
                    probe.bind(('127.0.0.1', candidate)); port = candidate; break
                except OSError:
                    continue
    app.run(debug=os.environ.get('FLASK_DEBUG', '1') == '1', host='0.0.0.0', port=port)
