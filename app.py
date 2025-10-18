from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = "your_secret_key_here"
DB_PATH = 'users.db'

# ------------------ DB helpers ------------------
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()

    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE,
        password TEXT NOT NULL
    )''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS club_members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        club TEXT NOT NULL,
        members INTEGER NOT NULL,
        group_name TEXT NOT NULL,
        reason TEXT,
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS event_bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        event_name TEXT NOT NULL,
        event_date TEXT NOT NULL DEFAULT '',
        event_time TEXT NOT NULL DEFAULT '',
        duration INTEGER NOT NULL DEFAULT 1,
        participants INTEGER NOT NULL DEFAULT 1,
        booked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(username, event_name)
    )''')

    conn.commit()
    conn.close()

# Initialize database
init_db()

# ------------------ Helpers ------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return decorated_function

# ------------------ Main Pages ------------------
@app.route('/')
def index():
    return render_template('index.html', user=session.get('user'))

@app.route('/about')
def about():
    return render_template('about.html', user=session.get('user'))

@app.route('/contact')
def contact():
    return render_template('contact.html', user=session.get('user'))

# ------------------ Auth ------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            flash("Enter both username and password", "danger")
            return redirect(url_for('login'))

        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user'] = username
            flash('Login successful!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('Invalid username or password', 'danger')
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        if not username or not password:
            flash('Provide username and password', 'danger')
            return redirect(url_for('login'))

        hashed_password = generate_password_hash(password)
        conn = get_db_connection()
        try:
            conn.execute("INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
                         (username, email, hashed_password))
            conn.commit()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username or email already exists!', 'danger')
        finally:
            conn.close()

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('index'))

# ------------------ CLUB ROUTES ------------------
@app.route('/join_club', methods=['GET', 'POST'])
@login_required
def join_club():
    username = session.get('user')

    if request.method == 'POST':
        club = request.form.get('club')
        members = request.form.get('members')
        group_name = request.form.get('group_name')
        reason = request.form.get('reason')

        conn = get_db_connection()
        conn.execute("""INSERT INTO club_members (username, club, members, group_name, reason)
                        VALUES (?, ?, ?, ?, ?)""",
                     (username, club, members, group_name, reason))
        conn.commit()
        conn.close()
        flash("✅ You joined the club successfully!", "success")
        return redirect(url_for('join_club'))

    conn = get_db_connection()
    groups = conn.execute("SELECT * FROM club_members WHERE username=?", (username,)).fetchall()
    conn.close()
    return render_template('join_club.html', user=username, groups=groups)

@app.route('/edit_club/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_club(id):
    username = session.get('user')
    conn = get_db_connection()
    group = conn.execute("SELECT * FROM club_members WHERE id=? AND username=?", (id, username)).fetchone()
    conn.close()

    if not group:
        flash("Group not found.", "danger")
        return redirect(url_for('join_club'))

    if request.method == 'POST':
        club = request.form['club']
        members = request.form['members']
        group_name = request.form['group_name']
        reason = request.form['reason']

        conn = get_db_connection()
        conn.execute("""UPDATE club_members
                        SET club=?, members=?, group_name=?, reason=?
                        WHERE id=?""",
                     (club, members, group_name, reason, id))
        conn.commit()
        conn.close()
        flash("✏️ Group updated successfully!", "success")
        return redirect(url_for('join_club'))

    return render_template('edit_club.html', user=username, group=group)

@app.route('/delete_club/<int:id>', methods=['POST'])
@login_required
def delete_club(id):
    username = session.get('user')
    conn = get_db_connection()
    conn.execute("DELETE FROM club_members WHERE id=? AND username=?", (id, username))
    conn.commit()
    conn.close()
    flash("🗑️ Group deleted successfully!", "success")
    return redirect(url_for('join_club'))

# ------------------ EVENT ROUTES ------------------
@app.route('/book_event', methods=['GET', 'POST'])
@login_required
def book_event():
    username = session.get('user')
    conn = get_db_connection()

    if request.method == 'POST':
        event_name = request.form.get('event_name')
        event_date = request.form.get('event_date') or ''
        event_time = request.form.get('event_time') or ''
        duration = int(request.form.get('duration', 1))
        participants = int(request.form.get('participants', 1))

        # Check for conflict
        conflict = conn.execute("""SELECT * FROM event_bookings
                                   WHERE event_date=? AND event_time=? AND username=?""",
                                (event_date, event_time, username)).fetchone()
        if conflict:
            flash("⚠️ You already have an event at this date and time!", "danger")
        else:
            conn.execute("""INSERT INTO event_bookings
                            (username, event_name, event_date, event_time, duration, participants)
                            VALUES (?, ?, ?, ?, ?, ?)""",
                         (username, event_name, event_date, event_time, duration, participants))
            conn.commit()
            flash("✅ Event booked successfully!", "success")
        conn.close()
        return redirect(url_for('book_event'))

    # GET request
    events = conn.execute("SELECT * FROM event_bookings WHERE username=? ORDER BY event_date, event_time",
                          (username,)).fetchall()
    conn.close()
    return render_template('book_event.html', user=username, events=events)

@app.route('/edit_event/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_event(id):
    username = session.get('user')
    conn = get_db_connection()
    event = conn.execute("SELECT * FROM event_bookings WHERE id=? AND username=?", (id, username)).fetchone()
    conn.close()

    if not event:
        flash("Event not found.", "danger")
        return redirect(url_for('book_event'))

    if request.method == 'POST':
        event_name = request.form['event_name']
        event_date = request.form['event_date']
        event_time = request.form['event_time']
        duration = request.form['duration']
        participants = request.form['participants']

        conn = get_db_connection()
        conn.execute("""UPDATE event_bookings
                        SET event_name=?, event_date=?, event_time=?, duration=?, participants=?
                        WHERE id=?""",
                     (event_name, event_date, event_time, duration, participants, id))
        conn.commit()
        conn.close()
        flash("✏️ Event updated successfully!", "success")
        return redirect(url_for('book_event'))

    return render_template('edit_event.html', user=username, event=event)

@app.route('/delete_event/<int:id>', methods=['POST'])
@login_required
def delete_event(id):
    username = session.get('user')
    conn = get_db_connection()
    conn.execute("DELETE FROM event_bookings WHERE id=? AND username=?", (id, username))
    conn.commit()
    conn.close()
    flash("🗑️ Event deleted successfully!", "success")
    return redirect(url_for('book_event'))

# ------------------ Run App ------------------
if __name__ == '__main__':
    app.run(debug=True)
