from datetime import date, datetime, time
from database import get_db_connection
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ==================================================
# CONFIGURATION
# ==================================================

ATTENDANCE_END = time(10,30)   # Attendance closes at 10:30 AM

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

SENDER_EMAIL = "nithinreddythimmareddy18@gmail.com"          # 🔴 CHANGE
SENDER_PASSWORD = "qsrh ybqq kdwk eyju"  # 🔴 CHANGE (App Password)


# ==================================================
# TIME CHECK
# ==================================================
def is_after_attendance_time():
    return datetime.now().time() >= ATTENDANCE_END


# ==================================================
# HOLIDAY CHECK
# ==================================================
def is_holiday(admin_id, today, cursor):
    # Sunday
    if today.weekday() == 6:
        return True

    cursor.execute(
        "SELECT 1 FROM holidays WHERE admin_id=%s AND holiday_date=%s",
        (admin_id, today)
    )
    return cursor.fetchone() is not None


# ==================================================
# EMAIL FUNCTION
# ==================================================
def send_absent_email(student_name, student_email, admin_name):
    print(f"📨 Sending email to {student_email}")

    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = student_email
    msg["Subject"] = "Attendance Alert – Absent"

    body = f"""
Dear {student_name},

This is an **official notification** to inform you that you have been marked **ABSENT** for today’s attendance session.

Attendance Window:
09:00 AM – 10:30 AM

Please note that **regular attendance is compulsory**. Any absence without prior approval or valid justification is considered a **serious violation of academic regulations**.

Repeated or unjustified absences may result in:
• Shortage of attendance  
• Academic penalties  
• Ineligibility for internal assessments  
• Further disciplinary action as per institutional rules  

If you believe this absence has been recorded incorrectly, you must report to the concerned administrator **immediately** with valid proof. Delays in reporting will not be entertained.

Administrator in Charge:
{admin_name}

This is a **system-generated official notice**.  
No reply is required.

Regards,  
Academic Administration Department  
Face Attendance & Monitoring System
"""


    msg.attach(MIMEText(body, "plain"))

    server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
    server.starttls()
    server.login(SENDER_EMAIL, SENDER_PASSWORD)
    server.sendmail(SENDER_EMAIL, student_email, msg.as_string())
    server.quit()

    print(f"✅ Email sent to {student_email}")


# ==================================================
# AUTO ABSENT + EMAIL PROCESS
# ==================================================
def mark_auto_absent():
    today = date.today()

    if not is_after_attendance_time():
        print("⏳ Attendance window still open. Exiting.")
        return

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch all admins
    cursor.execute("SELECT admin_id, username FROM admin")
    admins = cursor.fetchall()

    for admin in admins:
        admin_id = admin["admin_id"]
        admin_name = admin["username"]

        # Skip holidays
        if is_holiday(admin_id, today, cursor):
            print(f"📅 Holiday for admin {admin_id}. Skipping.")
            continue

        # Fetch students for admin
        cursor.execute("""
            SELECT student_id, name, email
            FROM students
            WHERE admin_id=%s
        """, (admin_id,))
        students = cursor.fetchall()

        for s in students:
            student_id = s["student_id"]
            student_name = s["name"]
            student_email = s["email"]

            # Check if attendance already exists
            cursor.execute("""
                SELECT status FROM attendance
                WHERE student_id=%s AND admin_id=%s AND date=%s
            """, (student_id, admin_id, today))

            if cursor.fetchone():
                continue  # Already Present / Absent

            # Insert ABSENT
            cursor.execute("""
                INSERT INTO attendance
                (student_id, admin_id, date, time, status, email_sent)
                VALUES (%s,%s,%s,%s,%s,%s)
            """, (
                student_id,
                admin_id,
                today,
                None,
                "Absent",
                0
            ))

            print(f"❌ ABSENT | Admin {admin_id} | Student {student_id}")

            # Send Email
            if student_email:
                try:
                    send_absent_email(student_name, student_email, admin_name)

                    cursor.execute("""
                        UPDATE attendance
                        SET email_sent=1
                        WHERE student_id=%s AND admin_id=%s AND date=%s
                    """, (student_id, admin_id, today))

                except Exception as e:
                    print(f"⚠ Email failed for {student_email}: {e}")

    conn.commit()
    conn.close()
    print("✅ Auto-absent + email process completed.")


# ==================================================
# RUN SCRIPT
# ==================================================
if __name__ == "__main__":
    mark_auto_absent()

