from flask import (
    Flask, render_template, request, redirect,
    url_for, session, jsonify, make_response, flash
)
from database import get_db_connection

import os
import shutil
import numpy as np
import face_recognition
import base64
from io import BytesIO
from PIL import Image
from datetime import date, datetime, time
from mysql.connector import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash

from face_utils import get_face_encoding, match_face

app = Flask(__name__, template_folder='templates')
app.secret_key = "super_secret_key"  # change in production

# ======================================================
# ATTENDANCE TIME SETTINGS
# ======================================================
ATTENDANCE_START = time(9, 0)      # 09:00 AM
ATTENDANCE_END   = time(10, 30)    # 10:30 AM


def is_attendance_time():
    now = datetime.now().time()
    return ATTENDANCE_START <= now <= ATTENDANCE_END


def is_holiday(admin_id, today):
    # Sunday check
    if today.weekday() == 6:
        return True

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM holidays WHERE admin_id=%s AND holiday_date=%s",
        (admin_id, today)
    )
    result = cursor.fetchone()
    conn.close()
    return bool(result)


# ======================================================
# PUBLIC HOME (AUTO CAMERA PAGE)
# ======================================================
@app.route('/')
def home():
    return render_template('public_scan.html')


# ======================================================
# PUBLIC FACE SCAN (ADMIN-WISE ISOLATION)
# ======================================================
@app.route('/scan-face', methods=['POST'])
def scan_face():
    # Attendance time check
    if not is_attendance_time():
        return jsonify({
            "status": "blocked",
            "message": "Attendance allowed only from 09:00 AM to 10:30 AM"
        })

    data = request.json['image']
    img_data = base64.b64decode(data.split(',')[1])
    img = Image.open(BytesIO(img_data)).convert('RGB')
    frame = np.array(img)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Load ALL students (ALL ADMINS)
    cursor.execute("""
        SELECT student_id, name, admin_id, face_encoding
        FROM students
        WHERE face_encoding IS NOT NULL
    """)
    students = cursor.fetchall()

    known_encodings = []
    student_records = []

    for s in students:
        known_encodings.append(np.frombuffer(s['face_encoding'], dtype=np.float64))
        student_records.append(s)

    face_encodings = face_recognition.face_encodings(frame)

    if not face_encodings:
        conn.close()
        return jsonify({"status": "unknown"})

    for face_encoding in face_encodings:
        matches = face_recognition.compare_faces(
            known_encodings, face_encoding, tolerance=0.45
        )

        matched_students = [
            student_records[i]
            for i, match in enumerate(matches) if match
        ]

        if not matched_students:
            conn.close()
            return jsonify({"status": "unknown"})

        today = date.today()
        now = datetime.now().time()
        already_marked = []
        newly_marked = []

        for student in matched_students:
            student_id = student['student_id']
            admin_id = student['admin_id']

            # Holiday check per admin
            if is_holiday(admin_id, today):
                continue

            # One scan per day lock
            cursor.execute("""
                SELECT 1 FROM attendance
                WHERE student_id=%s AND admin_id=%s AND date=%s
            """, (student_id, admin_id, today))

            if cursor.fetchone():
                already_marked.append(student['name'])
                continue

            # Mark PRESENT
            cursor.execute("""
                INSERT INTO attendance
                (student_id, admin_id, date, time, status)
                VALUES (%s,%s,%s,%s,%s)
            """, (
                student_id,
                admin_id,
                today,
                now,
                "Present"
            ))

            newly_marked.append(student['name'])

        conn.commit()
        conn.close()

        if newly_marked:
            return jsonify({
                "status": "success",
                "name": newly_marked[0],
                "message": f"Attendance marked for {len(newly_marked)} admin(s)"
            })

        return jsonify({
            "status": "already",
            "message": "Attendance already marked today"
        })

    conn.close()
    return jsonify({"status": "unknown"})


# ======================================================
# LOGIN
# ======================================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    # If already logged in as admin, redirect to dashboard
    if 'admin_id' in session:
        return redirect(url_for('dashboard'))

    # If already logged in as student, redirect to student dashboard
    if 'student_id' in session:
        return redirect(url_for('student_dashboard'))

    error = None
    student_error = None

    if request.method == 'POST':
        user_type = request.form.get('user_type')
        username = request.form['username']
        password = request.form['password']

        if user_type == 'admin':
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM admin WHERE username=%s", (username,))
            admin = cursor.fetchone()
            conn.close()

            if admin and check_password_hash(admin['password'], password):
                session['admin'] = admin['username']
                session['admin_id'] = admin['admin_id']
                return render_template('redirect_dashboard.html')

            error = "Invalid credentials"

        elif user_type == 'student':
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute("""
                SELECT student_id, name, student_password
                FROM students
                WHERE student_username=%s OR roll_no=%s OR name=%s
            """, (username, username, username))
            student = cursor.fetchone()
            conn.close()

            if student and check_password_hash(student['student_password'], password):
                session['student_id'] = student['student_id']
                session['student_name'] = student['name']
                return redirect(url_for('student_dashboard'))

            student_error = "Invalid credentials"

    response = make_response(render_template(
        'login.html',
        error=error,
        student_error=student_error
    ))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


# ======================================================
# SIGNUP (ADMIN)
# ======================================================
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO admin (username, password) VALUES (%s,%s)",
                (username, password)
            )
            conn.commit()
        except IntegrityError:
            conn.close()
            return render_template('signup.html', error="Username already exists")

        conn.close()
        return redirect(url_for('login'))

    return render_template('signup.html')


# ======================================================
# FORGOT PASSWORD (ADMIN)
# ======================================================
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username = request.form['username']
        new_password = generate_password_hash(request.form['password'])

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE admin SET password=%s WHERE username=%s",
            (new_password, username)
        )

        if cursor.rowcount == 0:
            conn.close()
            return render_template('forgot_password.html', error="Username not found")

        conn.commit()
        conn.close()
        return redirect(url_for('login'))

    return render_template('forgot_password.html')


# ======================================================
# LOGOUT (ADMIN)
# ======================================================
@app.route('/logout')
def logout():
    session.clear()
    return render_template('logout.html')


# ======================================================
# DASHBOARD (ADMIN-WISE STATS)
# ======================================================
@app.route('/dashboard')
def dashboard():
    if 'admin_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*) 
        FROM students 
        WHERE admin_id=%s
    """, (session['admin_id'],))
    total_students = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(DISTINCT student_id)
        FROM attendance
        WHERE admin_id=%s
        AND date=CURDATE()
        AND status='Present'
    """, (session['admin_id'],))
    present_today = cursor.fetchone()[0]

    conn.close()

    return render_template(
        'dashboard.html',
        admin=session['admin'],
        total_students=total_students,
        present_today=present_today
    )


# ======================================================
# ADD STUDENT (ADMIN-SCOPED)
# ======================================================
@app.route('/add-student', methods=['GET', 'POST'])
def add_student():
    if 'admin_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form['name']
        age = request.form['age']
        roll_no = request.form['roll_no']
        course = request.form['course']
        email = request.form['email']
        phone = request.form['phone']

        student_username = request.form['student_username']
        raw_password = request.form['student_password']
        student_password = generate_password_hash(raw_password)

        images = request.files.getlist('images')

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO students
            (name, age, roll_no, course, email, phone,
             student_username, student_password,
             face_encoding, admin_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            name, age, roll_no, course, email, phone,
            student_username, student_password,
            None, session['admin_id']
        ))

        student_id = cursor.lastrowid
        conn.commit()

        face_encoding = None
        folder = f"dataset/admin_{session['admin_id']}/student_{student_id}"
        os.makedirs(folder, exist_ok=True)

        for idx, image in enumerate(images):
            if image and image.filename:
                image_path = os.path.join(folder, f"{idx+1}_{image.filename}")
                image.save(image_path)

                encoding = get_face_encoding(image_path)
                if encoding is not None:
                    face_encoding = encoding
                    break

        if face_encoding is not None:
            cursor.execute("""
                UPDATE students
                SET face_encoding=%s
                WHERE student_id=%s
            """, (face_encoding.tobytes(), student_id))
            conn.commit()

        conn.close()
        return redirect(url_for('dashboard'))

    return render_template('add_student.html')


# ======================================================
# TEST ADD STUDENT (VALIDATION WITHOUT SAVING)
# ======================================================
@app.route('/test-add-student', methods=['POST'])
def test_add_student():
    if 'admin_id' not in session:
        return redirect(url_for('login'))

    name = request.form['name']
    age = request.form['age']
    roll_no = request.form['roll_no']
    course = request.form['course']
    email = request.form['email']
    phone = request.form['phone']
    student_username = request.form['student_username']
    raw_password = request.form['student_password']
    images = request.files.getlist('images')

    errors = []
    if not name or len(name.strip()) < 2:
        errors.append("Name must be at least 2 characters long")
    if not age or not age.isdigit() or int(age) < 1 or int(age) > 100:
        errors.append("Age must be a number between 1 and 100")
    if not roll_no or len(roll_no.strip()) < 1:
        errors.append("Roll number is required")
    if not course or len(course.strip()) < 2:
        errors.append("Course must be at least 2 characters long")
    if not email or '@' not in email:
        errors.append("Valid email address is required")
    if not phone or len(phone) != 10 or not phone.isdigit():
        errors.append("Phone number must be 10 digits")
    if not student_username or len(student_username.strip()) < 3:
        errors.append("Username must be at least 3 characters long")
    if not raw_password or len(raw_password) < 6:
        errors.append("Password must be at least 6 characters long")
    if not images or len(images) == 0:
        errors.append("At least one face image is required")

    if errors:
        return render_template('add_student.html', error="; ".join(errors))

    face_encoding = None
    for image in images:
        if image and image.filename:
            encoding = get_face_encoding(image)
            if encoding is not None:
                face_encoding = encoding
                break

    if face_encoding is None:
        return render_template(
            'add_student.html',
            error="No valid face detected in uploaded images. Please upload clear face images."
        )

    return render_template(
        'add_student.html',
        success="Test successful! All validations passed. Student data would be saved if you clicked 'Save Student'."
    )


# ======================================================
# STUDENT LIST (ADMIN-WISE)
# ======================================================
@app.route('/students')
def student_list():
    if 'admin_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT student_id, name, age, roll_no, course, email, phone,
        CASE WHEN face_encoding IS NULL THEN 'Not Registered' ELSE 'Registered' END AS face_status
        FROM students
        WHERE admin_id=%s
        ORDER BY student_id DESC
    """, (session['admin_id'],))

    students = cursor.fetchall()
    conn.close()

    return render_template('student_list.html', students=students)


# ======================================================
# MARK ATTENDANCE MANUALLY (ADMIN ACTION)
# ======================================================
@app.route('/mark-attendance/<int:student_id>/<status>')
def mark_attendance(student_id, status):
    if 'admin_id' not in session:
        return redirect(url_for('login'))

    if status not in ['Present', 'Absent']:
        return redirect(url_for('student_list'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT 1 FROM students WHERE student_id=%s AND admin_id=%s",
        (student_id, session['admin_id'])
    )
    if not cursor.fetchone():
        conn.close()
        return redirect(url_for('student_list'))

    today = date.today()
    now = datetime.now().time()

    cursor.execute("""
        SELECT 1 FROM attendance
        WHERE student_id=%s AND admin_id=%s AND date=%s
    """, (student_id, session['admin_id'], today))

    if cursor.fetchone():
        conn.close()
        return redirect(url_for('student_list'))

    cursor.execute("""
        INSERT INTO attendance
        (student_id, admin_id, date, time, status)
        VALUES (%s,%s,%s,%s,%s)
    """, (student_id, session['admin_id'], today, now, status))

    conn.commit()
    conn.close()

    return redirect(url_for('student_list'))


# ======================================================
# ATTENDANCE LIST (ADMIN-WISE)
# ======================================================
@app.route('/attendance-list')
def attendance_list():
    if 'admin_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT s.name, s.roll_no, a.date, a.time, a.status
        FROM attendance a
        JOIN students s ON a.student_id = s.student_id
        WHERE a.admin_id=%s
        ORDER BY a.date DESC, a.time DESC
    """, (session['admin_id'],))

    records = cursor.fetchall()
    conn.close()

    return render_template('attendance_list.html', records=records)


# ======================================================
# TAKE ATTENDANCE (ADMIN PAGE)
# ======================================================
@app.route('/take-attendance')
def take_attendance():
    if 'admin_id' not in session:
        return redirect(url_for('login'))

    return render_template('take_attendance.html')


# ======================================================
# START ATTENDANCE (ADMIN ACTION)
# ======================================================
@app.route('/start-attendance')
def start_attendance():
    if 'admin_id' not in session:
        return redirect(url_for('login'))

    return redirect(url_for('home'))


# ======================================================
# EDIT STUDENT (ADMIN-WISE)
# ======================================================
@app.route('/edit-student/<int:student_id>', methods=['GET', 'POST'])
def edit_student(student_id):
    if 'admin_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        student_username = request.form['student_username']
        raw_password = request.form['student_password']
        hashed_password = generate_password_hash(raw_password)

        cursor.execute("""
            UPDATE students
            SET student_username=%s,
                student_password=%s
            WHERE student_id=%s AND admin_id=%s
        """, (
            student_username,
            hashed_password,
            student_id,
            session['admin_id']
        ))

        conn.commit()
        conn.close()
        return redirect(url_for('student_list'))

    cursor.execute("""
        SELECT * FROM students
        WHERE student_id=%s AND admin_id=%s
    """, (student_id, session['admin_id']))
    student = cursor.fetchone()
    conn.close()

    return render_template('edit_student.html', student=student)


# ======================================================
# VIEW STUDENT FACE IMAGES (ADMIN-WISE)
# ======================================================
@app.route('/view-faces/<int:student_id>')
def view_faces(student_id):
    if 'admin_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT student_id FROM students WHERE student_id=%s AND admin_id=%s",
        (student_id, session['admin_id'])
    )
    student = cursor.fetchone()
    conn.close()

    if not student:
        return redirect(url_for('student_list'))

    folder = f"dataset/admin_{session['admin_id']}/student_{student_id}"
    images = []

    if os.path.exists(folder):
        images = os.listdir(folder)

    return render_template(
        'view_faces.html',
        student_id=student_id,
        images=images
    )


# ======================================================
# DELETE STUDENT (ADMIN-WISE, SAFE)
# ======================================================
@app.route('/delete-student/<int:student_id>')
def delete_student(student_id):
    if 'admin_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT student_id FROM students WHERE student_id=%s AND admin_id=%s",
        (student_id, session['admin_id'])
    )
    student = cursor.fetchone()

    if not student:
        conn.close()
        return redirect(url_for('student_list'))

    cursor.execute(
        "DELETE FROM attendance WHERE student_id=%s AND admin_id=%s",
        (student_id, session['admin_id'])
    )

    cursor.execute(
        "DELETE FROM students WHERE student_id=%s AND admin_id=%s",
        (student_id, session['admin_id'])
    )

    conn.commit()
    conn.close()

    folder = f"dataset/admin_{session['admin_id']}/student_{student_id}"
    if os.path.exists(folder):
        shutil.rmtree(folder)

    return redirect(url_for('student_list'))


# ======================================================
# ANALYTICS DATA (ADMIN)
# ======================================================
@app.route('/analytics-data')
def analytics_data():
    if 'admin_id' not in session:
        return jsonify({})

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    admin_id = session['admin_id']

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM students
        WHERE admin_id=%s
    """, (admin_id,))
    total_students = cursor.fetchone()['total']

    cursor.execute("""
        SELECT COUNT(DISTINCT student_id) AS present
        FROM attendance
        WHERE admin_id=%s
        AND date=CURDATE()
        AND status='Present'
    """, (admin_id,))
    present_today = cursor.fetchone()['present']

    cursor.execute("""
        SELECT COUNT(DISTINCT student_id) AS absent
        FROM attendance
        WHERE admin_id=%s
        AND date=CURDATE()
        AND status='Absent'
    """, (admin_id,))
    absent_today = cursor.fetchone()['absent']

    if present_today + absent_today > total_students:
        present_today = min(present_today, total_students)
        absent_today = max(total_students - present_today, 0)

    cursor.execute("""
        SELECT 
            DATE_FORMAT(date, '%a') AS day,
            COUNT(DISTINCT student_id) AS count
        FROM attendance
        WHERE admin_id=%s
        AND status='Present'
        AND date >= CURDATE() - INTERVAL 6 DAY
        GROUP BY date
        ORDER BY date
    """, (admin_id,))
    weekly = cursor.fetchall()

    cursor.execute("""
        SELECT 
            s.name,
            COUNT(a.attendance_id) AS absents
        FROM students s
        LEFT JOIN attendance a
            ON s.student_id = a.student_id
            AND a.status='Absent'
        WHERE s.admin_id=%s
        GROUP BY s.student_id
        ORDER BY absents DESC
        LIMIT 5
    """, (admin_id,))
    absent = cursor.fetchall()

    conn.close()

    return jsonify({
        "total_students": total_students,
        "present_today": present_today,
        "absent_today": absent_today,
        "weekly": weekly,
        "absent": absent
    })


# ======================================================
# HOLIDAYS MANAGEMENT (ADMIN-WISE)
# ======================================================
@app.route('/holidays', methods=['GET', 'POST'])
def holiday_list():
    if 'admin_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        holiday_date = request.form['holiday_date']
        reason = request.form['reason']

        try:
            cursor.execute("""
                INSERT INTO holidays (admin_id, holiday_date, reason)
                VALUES (%s,%s,%s)
            """, (session['admin_id'], holiday_date, reason))
            conn.commit()
        except IntegrityError:
            pass

    cursor.execute("""
        SELECT * FROM holidays
        WHERE admin_id=%s
        ORDER BY holiday_date
    """, (session['admin_id'],))

    holidays = cursor.fetchall()
    conn.close()

    return render_template('holidays.html', holidays=holidays)


@app.route('/delete-holiday/<int:holiday_id>')
def delete_holiday(holiday_id):
    if 'admin_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM holidays
        WHERE holiday_id=%s AND admin_id=%s
    """, (holiday_id, session['admin_id']))

    conn.commit()
    conn.close()
    return redirect(url_for('holiday_list'))


# ======================================================
# STUDENT LOGOUT
# ======================================================
@app.route('/student-logout')
def student_logout():
    session.pop('student_id', None)
    session.pop('student_name', None)
    session.pop('student_admin_id', None)
    return redirect(url_for('login'))


# ======================================================
# STUDENT DASHBOARD
# ======================================================
@app.route('/student-dashboard')
def student_dashboard():
    if 'student_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT date, time, status
        FROM attendance
        WHERE student_id=%s
        ORDER BY date DESC
    """, (session['student_id'],))
    attendance = cursor.fetchall()

    cursor.execute("""
        SELECT holiday_date, reason
        FROM holidays
        WHERE admin_id = (SELECT admin_id FROM students WHERE student_id=%s)
        ORDER BY holiday_date
    """, (session['student_id'],))
    holidays = cursor.fetchall()

    conn.close()

    return render_template(
        'student_dashboard.html',
        student_name=session['student_name'],
        attendance=attendance,
        holidays=holidays
    )


@app.route('/student-dashboard-data')
def student_dashboard_data():
    if 'student_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT date, time, status
        FROM attendance
        WHERE student_id=%s
        ORDER BY date DESC
    """, (session['student_id'],))
    attendance = cursor.fetchall()

    total_days = len(attendance)
    present_count = sum(1 for record in attendance if record['status'] == 'Present')
    absent_count = total_days - present_count

    cursor.execute("""
        SELECT holiday_date, reason
        FROM holidays
        WHERE admin_id = (SELECT admin_id FROM students WHERE student_id=%s)
        ORDER BY holiday_date
    """, (session['student_id'],))
    holidays = cursor.fetchall()

    conn.close()

    return jsonify({
        'student_name': session['student_name'],
        'total_days': total_days,
        'present_count': present_count,
        'absent_count': absent_count,
        'attendance': attendance,
        'holidays': holidays
    })


@app.route('/student-attendance')
def student_attendance():
    if 'student_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT date, time, status
        FROM attendance
        WHERE student_id=%s
        ORDER BY date DESC
    """, (session['student_id'],))
    records = cursor.fetchall()
    conn.close()

    return render_template(
        'student_attendance.html',
        records=records
    )


# ======================================================
# STUDENT LEAVE REQUESTS
# ======================================================
@app.route('/request-leave', methods=['GET', 'POST'])
def request_leave():
    if 'student_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT name, email, phone, roll_no
        FROM students
        WHERE student_id=%s
    """, (session['student_id'],))
    student = cursor.fetchone()

    if request.method == 'POST':
        start_date = request.form['start_date']
        end_date = request.form['end_date']
        description = request.form['description']

        cursor.execute("""
            INSERT INTO leave_requests
            (student_id, name, email, phone, roll_no,
             start_date, end_date, description, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            session['student_id'],
            student['name'],
            student['email'],
            student['phone'],
            student['roll_no'],
            start_date,
            end_date,
            description,
            'pending'
        ))
        conn.commit()
        conn.close()
        flash('Your leave is submitted successfully!', 'success')
        return redirect(url_for('my_leave_requests'))

    conn.close()
    return render_template('request_leave.html', student=student)


@app.route('/my-leave-requests')
def my_leave_requests():
    if 'student_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT *
        FROM leave_requests
        WHERE student_id=%s
        ORDER BY submitted_at DESC
    """, (session['student_id'],))
    leaves = cursor.fetchall()

    conn.close()
    return render_template('my_leave_requests.html', leaves=leaves)


# ======================================================
# ADMIN: VIEW & MANAGE LEAVE REQUESTS
# ======================================================
@app.route('/admin-leave-requests')
def admin_leave_requests():
    if 'admin_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT lr.*
        FROM leave_requests lr
        JOIN students s ON lr.student_id = s.student_id
        WHERE s.admin_id=%s
        ORDER BY lr.submitted_at DESC
    """, (session['admin_id'],))
    leaves = cursor.fetchall()
    conn.close()

    return render_template('admin_leave_requests.html', leaves=leaves)


@app.route('/update-leave-status/<int:leave_id>/<status>')
def update_leave_status(leave_id, status):
    if 'admin_id' not in session:
        return redirect(url_for('login'))

    if status not in ['approved', 'declined']:
        return redirect(url_for('admin_leave_requests'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE leave_requests lr
        JOIN students s ON lr.student_id = s.student_id
        SET lr.status=%s
        WHERE lr.id=%s AND s.admin_id=%s
    """, (status, leave_id, session['admin_id']))

    conn.commit()
    conn.close()
    return redirect(url_for('admin_leave_requests'))


# ======================================================
# RUN
# ======================================================
if __name__ == '__main__':
    app.run(debug=True)
