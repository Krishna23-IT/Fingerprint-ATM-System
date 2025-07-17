from flask import Flask, render_template, request, redirect, session, url_for
import sqlite3
from datetime import datetime
import os
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

app = Flask(__name__)
app.secret_key = 'secure-atm-key'

# ---------------- DB Connection ----------------
def get_connection():
    return sqlite3.connect("atm.db")

# ---------------- Home ----------------
@app.route('/')
@app.route('/index')
def index():
    return render_template('index.html')

@app.route('/Signup', methods=['GET'])
def Signup():
    return render_template('Signup.html', msg='')

@app.route('/Login', methods=['GET'])
def Login():
    return render_template('Login.html', msg='')

# ---------------- Signup ----------------
@app.route('/SignupAction', methods=['POST'])
def SignupAction():
    user = request.form['t1']
    password = request.form['t2']
    file = request.files['t3']

    if not user or not password or not file:
        return render_template('Signup.html', msg="All fields are required")

    con = get_connection()
    try:
        cur = con.cursor()
        cur.execute("SELECT * FROM users WHERE username=?", (user,))
        if cur.fetchone():
            return render_template('Signup.html', msg="User already exists")

        cur.execute("INSERT INTO users (username, password) VALUES (?, ?)", (user, password))
        con.commit()

        file.save(f"static/users/{user}.png")
        return render_template('Login.html', msg="Signup successful. Please login.")
    finally:
        con.close()

# ---------------- Login ----------------
@app.route('/LoginAction', methods=['POST'])
def LoginAction():
    user = request.form['t1']
    password = request.form['t2']
    uploaded_file = request.files['t3'].read()

    con = get_connection()
    try:
        cur = con.cursor()
        cur.execute("SELECT password FROM users WHERE username=?", (user,))
        row = cur.fetchone()
        if not row or row[0] != password:
            return render_template('Login.html', msg="Invalid username or password")

        path = f"static/users/{user}.png"
        if not os.path.exists(path):
            return render_template('Login.html', msg="Fingerprint not found for user")

        with open(path, 'rb') as stored:
            stored_data = stored.read()
            if stored_data != uploaded_file:
                return render_template('Login.html', msg="Fingerprint does not match")

        session['user'] = user
        return render_template('UserScreen.html', msg=f"Welcome {user}")
    finally:
        con.close()

@app.route('/UserScreen')
def UserScreen():
    if 'user' not in session:
        return redirect(url_for('Login'))
    return render_template('UserScreen.html', msg=f"Welcome {session['user']}")

@app.route('/Logout')
def Logout():
    session.clear()
    return redirect(url_for('index'))

# ---------------- Deposit ----------------
@app.route('/Deposit')
def Deposit():
    if 'user' not in session:
        return redirect(url_for('Login'))

    user = session['user']
    return render_template('Deposit.html', msg1=f"<tr><td>Username</td><td><input type='text' name='t1' value='{user}' readonly/></td></tr>")

@app.route('/DepositAction', methods=['POST'])
def DepositAction():
    user = request.form['t1']
    amount = float(request.form['t2'])

    con = get_connection()
    try:
        cur = con.cursor()
        cur.execute("SELECT balance FROM transactions WHERE username=? ORDER BY id DESC LIMIT 1", (user,))
        row = cur.fetchone()
        current_balance = row[0] if row else 0
        new_balance = current_balance + amount
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cur.execute("INSERT INTO transactions (username, date, transaction_type, amount, balance) VALUES (?, ?, ?, ?, ?)",
                    (user, timestamp, 'Deposit', amount, new_balance))
        con.commit()
        receipt_file = generate_receipt(user, 'Deposit', amount, new_balance)
        return render_template('UserScreen.html', msg=f"₹{amount} deposited successfully.", receipt=receipt_file)
    finally:
        con.close()

# ---------------- Withdraw ----------------
@app.route('/Withdraw')
def Withdraw():
    if 'user' not in session:
        return redirect(url_for('Login'))

    user = session['user']
    return render_template('Withdraw.html', msg1=f"<tr><td>Username</td><td><input type='text' name='t1' value='{user}' readonly/></td></tr>")

@app.route('/WithdrawAction', methods=['POST'])
def WithdrawAction():
    user = request.form['t1']
    amount = float(request.form['t2'])

    con = get_connection()
    try:
        cur = con.cursor()
        cur.execute("SELECT balance FROM transactions WHERE username=? ORDER BY id DESC LIMIT 1", (user,))
        row = cur.fetchone()
        current_balance = row[0] if row else 0

        if current_balance < amount:
            return render_template('UserScreen.html', msg="Insufficient fund")

        new_balance = current_balance - amount
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cur.execute("INSERT INTO transactions (username, date, transaction_type, amount, balance) VALUES (?, ?, ?, ?, ?)",
                    (user, timestamp, 'Withdraw', amount, new_balance))
        con.commit()
        receipt_file = generate_receipt(user, 'Withdraw', amount, new_balance)
        return render_template('UserScreen.html', msg=f"₹{amount} withdrawn successfully.", receipt=receipt_file)
    finally:
        con.close()

# ---------------- View Balance ----------------
@app.route('/ViewBalance')
def ViewBalance():
    if 'user' not in session:
        return redirect(url_for('Login'))

    user = session['user']
    con = get_connection()
    try:
        cur = con.cursor()

        # Get balance
        cur.execute("SELECT balance FROM transactions WHERE username=? ORDER BY id DESC LIMIT 1", (user,))
        row = cur.fetchone()
        balance = row[0] if row else 0

        # Get all transactions to show in table
        cur.execute("SELECT username, date, transaction_type, amount, balance FROM transactions WHERE username=? ORDER BY date DESC", (user,))
        transactions = cur.fetchall()

    finally:
        con.close()

    statement_file = generate_statement(user)
    return render_template('ViewBalance.html', balance=balance, statement=statement_file, transactions=transactions)


# ---------------- PDF Receipt Generator ----------------
def generate_receipt(username, trans_type, amount, balance):
    os.makedirs('static/receipts', exist_ok=True)
    filename = f"{username}_{trans_type}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
    filepath = os.path.join('static/receipts', filename)

    c = canvas.Canvas(filepath, pagesize=letter)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(180, 750, "ATM Transaction Receipt")

    c.setFont("Helvetica", 12)
    c.drawString(50, 720, f"Username: {username}")
    c.drawString(50, 700, f"Transaction Type: {trans_type}")
    c.drawString(50, 680, f"Amount: ₹{amount}")
    c.drawString(50, 660, f"Balance: ₹{balance}")
    c.drawString(50, 640, f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    c.save()
    return filename

# ---------------- PDF Statement Generator ----------------
def generate_statement(username):
    con = get_connection()
    try:
        cur = con.cursor()
        cur.execute("SELECT date, transaction_type, amount, balance FROM transactions WHERE username=? ORDER BY date DESC", (username,))
        rows = cur.fetchall()
    finally:
        con.close()

    os.makedirs('static/statements', exist_ok=True)
    filename = f"{username}_statement_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
    filepath = os.path.join('static/statements', filename)

    c = canvas.Canvas(filepath, pagesize=letter)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(180, 750, "ATM Transaction Statement")
    c.setFont("Helvetica", 12)
    c.drawString(50, 720, f"Username: {username}")
    c.drawString(50, 700, f"Date Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    y = 660
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Date")
    c.drawString(160, y, "Type")
    c.drawString(260, y, "Amount")
    c.drawString(360, y, "Balance")

    c.setFont("Helvetica", 11)
    for row in rows:
        y -= 20
        if y < 100:
            c.showPage()
            y = 750
        c.drawString(50, y, str(row[0]))
        c.drawString(160, y, row[1])
        c.drawString(260, y, f"₹{row[2]}")
        c.drawString(360, y, f"₹{row[3]}")

    c.save()
    return filename

# ---------------- Admin ----------------
@app.route('/AdminLogin', methods=['GET', 'POST'])
def AdminLogin():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if username == 'admin' and password == 'admin123':
            session['admin'] = True
            return redirect(url_for('AdminDashboard'))
        else:
            return render_template('AdminLogin.html', msg='Invalid Credentials')

    return render_template('AdminLogin.html', msg='')

@app.route('/AdminDashboard')
def AdminDashboard():
    if 'admin' not in session:
        return redirect(url_for('AdminLogin'))

    con = get_connection()
    try:
        cur = con.cursor()
        cur.execute("SELECT username FROM users")
        users = cur.fetchall()

        cur.execute("SELECT username, date, transaction_type, amount, balance FROM transactions ORDER BY date DESC")
        transactions = cur.fetchall()

        return render_template('AdminDashboard.html', users=users, transactions=transactions)
    finally:
        con.close()

@app.route('/AdminLogout')
def AdminLogout():
    session.pop('admin', None)
    return redirect(url_for('AdminLogin'))

# ---------------- Change Password ----------------
@app.route('/ChangePassword', methods=['GET', 'POST'])
def ChangePassword():
    if 'user' not in session:
        return redirect(url_for('Login'))

    user = session['user']

    if request.method == 'POST':
        old_pass = request.form['old_password']
        new_pass = request.form['new_password']
        confirm_pass = request.form['confirm_password']

        if new_pass != confirm_pass:
            return render_template('ChangePassword.html', msg="New passwords do not match.")

        con = get_connection()
        try:
            cur = con.cursor()
            cur.execute("SELECT password FROM users WHERE username=?", (user,))
            row = cur.fetchone()

            if not row or row[0] != old_pass:
                return render_template('ChangePassword.html', msg="Old password is incorrect.")

            cur.execute("UPDATE users SET password=? WHERE username=?", (new_pass, user))
            con.commit()
            return render_template('ChangePassword.html', msg="Password changed successfully!")
        finally:
            con.close()

    return render_template('ChangePassword.html', msg='')


if __name__ == '__main__':
    app.run(debug=True)
