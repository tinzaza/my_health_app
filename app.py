# app.py
import os, json
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from markupsafe import Markup



app = Flask(__name__)
app.secret_key = "very_secret_key_here"

##DB_PATH = os.environ.get("DATABASE_PATH", "database.db")


# ---------------- DB ---------------- #
def get_db():
    db_url = os.environ["DATABASE_URL"]

    sslmode = "require" if "render.com" in db_url else "disable"

    return psycopg2.connect(
        db_url,
        cursor_factory=RealDictCursor,
        sslmode=sslmode
    )








def init_db():
    conn = get_db()
    cur = conn.cursor()

    # USERS
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL,
        full_name TEXT
    )
    """)

    # PATIENT PROFILE
    cur.execute("""
    CREATE TABLE IF NOT EXISTS patient_profiles (
        id SERIAL PRIMARY KEY,
        user_id INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
        email TEXT,
        phone TEXT,
        address TEXT,
        dob DATE,
        gender TEXT,
        emergency_contact TEXT,
        insurance_provider TEXT,
        hospital_number TEXT
    )
    """)

    # SYMPTOMS
    cur.execute("""
    CREATE TABLE IF NOT EXISTS symptoms (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        tnss INTEGER,
        avg_vas REAL,
        pattern TEXT,
        recommendation TEXT,
        follow_up INTEGER DEFAULT 0,
        created_at TIMESTAMP,
        raw_form JSONB,
        medicine_effect INTEGER
    )
    """)

    # PATIENT HISTORY
    cur.execute("""
    CREATE TABLE IF NOT EXISTS patient_history (
        id SERIAL PRIMARY KEY,
        user_id INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,

        symptom_year_pattern TEXT,

        season_summer BOOLEAN,
        season_rainy BOOLEAN,
        season_winter BOOLEAN,
        season_summer_rainy BOOLEAN,
        season_rainy_winter BOOLEAN,
        season_uncertain BOOLEAN,

        duration_per_year TEXT,
        weekly_frequency TEXT,

        time_6_12 BOOLEAN,
        time_12_18 BOOLEAN,
        time_18_24 BOOLEAN,
        time_24_6 BOOLEAN,
        time_all_day BOOLEAN,
        time_uncertain BOOLEAN,

        living_area TEXT,
        near_road BOOLEAN,
        housing_type TEXT,
        air_conditioner BOOLEAN,

        pet_cat BOOLEAN,
        pet_dog BOOLEAN,
        pet_bird BOOLEAN,
        pet_other TEXT,

        trigger_dust BOOLEAN,
        trigger_pollen BOOLEAN,
        trigger_animal BOOLEAN,
        trigger_smoke BOOLEAN,
        trigger_cold_air BOOLEAN,
        trigger_pollution BOOLEAN,
        trigger_stress BOOLEAN,
        trigger_other TEXT,

        smoking_status TEXT,
        cigarettes_per_day INTEGER,
        quit_years INTEGER,
        secondhand_smoke TEXT,

        drug_allergy TEXT,
        drug_allergy_name TEXT,
        drug_allergy_symptom TEXT,
        food_allergy TEXT,
        food_allergy_name TEXT,
        food_allergy_symptom TEXT,

        natural_allergy TEXT,
        natural_allergy_symptom TEXT,

        family_asthma TEXT,
        family_rhinitis TEXT,
        family_allergic_conjunctivitis TEXT,
        family_atopic_dermatitis TEXT,

        work_performance TEXT,
        physical_activity_problem TEXT,
        stairs_problem TEXT,

        work_less_physical TEXT,
        work_careful_physical TEXT,
        work_less_emotional TEXT,
        work_careless_emotional TEXT,

        daily_activity_limit TEXT,

        feel_calm TEXT,
        feel_energetic TEXT,
        feel_sad TEXT,
        social_limit TEXT
    )
    """)

    conn.commit()
    conn.close()

init_db()
# ---------------- Helpers ---------------- #
def classify_pattern(days_per_week: int) -> str:
    return "persistent" if days_per_week >= 4 else "intermittent"

def calculate_follow_up(prev_follow_up, avg_vas, pattern, used_steroid_before):
    # reset condition
    if avg_vas < 5 and pattern == "intermittent":
        return 0

    # first time worsening
    if avg_vas >= 5 and prev_follow_up == 0:
        return 1

    # follow_up = 1 logic
    if prev_follow_up == 1:
        if used_steroid_before == "yes":
            return 2
        return 1

    # follow_up = 2 stays 2
    if prev_follow_up >= 2:
        return 2

    return prev_follow_up

# ---------------- Medicine Algorithm ---------------- #
def generate_recommendation(pattern, avg_vas, follow_up, used_steroid_answer):
    saline = (
        "ล้างจมูกด้วยน้ำเกลือ (Normal saline irrigation)\n"
        "– วันละ 1–2 ครั้ง\n\n"
    )

    oral_ah = (
        "ยาต้านฮิสตามีนชนิดรับประทาน รุ่นที่ 2\n"
        "– วันละ 1 ครั้ง\n\n"
    )

    leuko = (
        "Leukotriene receptor antagonist (LTRA)\n"
        "– วันละ 1 ครั้ง\n\n"
    )

    incs_standard = (
        "ยาสเตียรอยด์พ่นจมูก\n"
        "– 2 sprays/nostril วันละครั้ง\n"
    )

    incs_high = (
        "ยาสเตียรอยด์พ่นจมูก (เพิ่มขนาดยา)\n"
        "– 2 sprays/nostril วันละ 2 ครั้ง\n"
    )

    # ================= STATE 0 =================
    if follow_up == 0:
        if pattern == "intermittent" and avg_vas < 5:
            return saline + "เลือกอย่างใดอย่างหนึ่ง\n\n" + oral_ah + "หรือ\n\n" + leuko

        if (pattern == "intermittent" and avg_vas >= 5) or \
           (pattern == "persistent" and avg_vas < 5):
            return saline + "เลือกอย่างใดอย่างหนึ่ง\n\n" + oral_ah + "หรือ\n\n" + incs_standard

        if pattern == "persistent" and avg_vas >= 5:
            return saline + incs_standard

    # ================= STATE 1 =================
    if follow_up == 1:
        if avg_vas < 5:
            return "อาการดีขึ้น → ลดระดับยา และใช้ยาต่ออีก 2 สัปดาห์"

        if used_steroid_answer == "no":
            return saline + incs_standard

        return (
            "ส่งพบแพทย์เฉพาะทาง\n"
            "ประเมินการวินิจฉัยและการใช้ยา\n\n"
            + incs_high
        )

    # ================= STATE 2 =================
    if follow_up == 2:
        if avg_vas < 5:
            return "อาการดีขึ้น → ลดระดับยา และใช้ยาต่ออีก 2 สัปดาห์"

        return (
            "ส่งพบแพทย์เฉพาะทาง\n"
            "ประเมินการวินิจฉัยและการใช้ยา\n\n"
            + incs_high
        )

    # ================= STATE 3 =================
    if follow_up == 3:
        if avg_vas < 5:
            return "อาการดีขึ้น → ลดระดับยา และใช้ยาต่ออีก 2 สัปดาห์"
        return (
        "ภูมิคุ้มกันบัมบัดด้วยสารก่อภูมิแพ้\n"
        "ควรได้รับการผ่าตัด"
        )

# ---------------- Routes ---------------- #

@app.route("/", methods=["GET"])
def index():
    return redirect(url_for("welcome"))

@app.route("/welcome")
def welcome():
    return render_template("welcome.html")

# ---------- Login ---------- #
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            "SELECT * FROM users WHERE username = %s",
            (request.form["username"],)
        )
        user = cur.fetchone()
        conn.close()

        if user and check_password_hash(user["password"], request.form["password"]):
            session["user_id"] = user["id"]
            session["role"] = user["role"]
            return redirect(
                url_for("doctor_dashboard" if user["role"] == "doctor" else "patient_form")
            )

        flash("Invalid login", "danger")

    return render_template("login.html")

# ---------- Signup ---------- #
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        print("SIGNUP FORM:", dict(request.form))
        conn = get_db()
        cur = conn.cursor()

        try:
            role = request.form["role"]

            # 0️⃣ CHECK DOCTOR CODE
            if role == "doctor":
                if request.form.get("doctor_code") != "SECRET123":
                    flash("Invalid doctor signup code", "danger")
                    return redirect(url_for("signup"))

            # 1️⃣ CREATE USER (RETURNING id is REQUIRED for PostgreSQL)
            cur.execute(
                """
                INSERT INTO users (username, password, role, full_name)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (
                    request.form["username"],
                    generate_password_hash(request.form["password"]),
                    role,
                    request.form["full_name"]
                )
            )
            user_id = cur.fetchone()["id"]

            # 2️⃣ PATIENT PROFILE
            if role == "patient":
                cur.execute(
                    """
                    INSERT INTO patient_profiles
                    (user_id, email, phone, address, dob, gender,
                     emergency_contact, insurance_provider, hospital_number)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        user_id,
                        request.form.get("email"),
                        request.form.get("phone"),
                        request.form.get("address"),
                        request.form.get("dob"),
                        request.form.get("gender"),
                        request.form.get("emergency_contact"),
                        request.form.get("insurance_provider"),
                        request.form.get("hospital_number")
                    )
                )

                # 3️⃣ PATIENT HISTORY
                history_data = {
                    "symptom_year_pattern": request.form.get("symptom_year_pattern"),

                    "season_summer": bool(request.form.get("season_summer")),
                    "season_rainy": bool(request.form.get("season_rainy")),
                    "season_winter": bool(request.form.get("season_winter")),
                    "season_summer_rainy": bool(request.form.get("season_summer_rainy")),
                    "season_rainy_winter": bool(request.form.get("season_rainy_winter")),
                    "season_uncertain": bool(request.form.get("season_uncertain")),

                    "duration_per_year": request.form.get("duration_per_year"),
                    "weekly_frequency": request.form.get("weekly_frequency"),

                    "time_6_12": bool(request.form.get("time_6_12")),
                    "time_12_18": bool(request.form.get("time_12_18")),
                    "time_18_24": bool(request.form.get("time_18_24")),
                    "time_24_6": bool(request.form.get("time_24_6")),
                    "time_all_day": bool(request.form.get("time_all_day")),
                    "time_uncertain": bool(request.form.get("time_uncertain")),

                    "living_area": request.form.get("living_area"),
                    "near_road": request.form.get("near_road") == "yes",
                    "housing_type": request.form.get("housing_type"),
                    "air_conditioner": request.form.get("air_conditioner") == "yes",

                    "pet_cat": bool(request.form.get("pet_cat")),
                    "pet_dog": bool(request.form.get("pet_dog")),
                    "pet_bird": bool(request.form.get("pet_bird")),
                    "pet_other": request.form.get("pet_other"),

                    "trigger_dust": bool(request.form.get("trigger_dust")),
                    "trigger_pollen": bool(request.form.get("trigger_pollen")),
                    "trigger_animal": bool(request.form.get("trigger_animal")),
                    "trigger_smoke": bool(request.form.get("trigger_smoke")),
                    "trigger_cold_air": bool(request.form.get("trigger_cold_air")),
                    "trigger_pollution": bool(request.form.get("trigger_pollution")),
                    "trigger_stress": bool(request.form.get("trigger_stress")),
                    "trigger_other": request.form.get("trigger_other"),

                    "smoking_status": request.form.get("smoking_status"),
                    "cigarettes_per_day": (
                        int(request.form.get("cigarettes_per_day"))
                        if request.form.get("cigarettes_per_day")
                        else None
                    ),
                    "quit_years": (
                        int(request.form.get("quit_years"))
                        if request.form.get("quit_years")
                        else None
                    ),

                    "secondhand_smoke": request.form.get("secondhand_smoke"),

                    "drug_allergy": request.form.get("drug_allergy"),
                    "drug_allergy_name": request.form.get("drug_allergy_name"),
                    "drug_allergy_symptom": request.form.get("drug_allergy_symptom"),

                    "food_allergy": request.form.get("food_allergy"),
                    "food_allergy_name": request.form.get("food_allergy_name"),
                    "food_allergy_symptom": request.form.get("food_allergy_symptom"),

                    "natural_allergy": request.form.get("natural_allergy"),
                    "natural_allergy_symptom": request.form.get("natural_allergy_symptom"),

                    "family_asthma": ",".join(request.form.getlist("family_asthma")),
                    "family_rhinitis": ",".join(request.form.getlist("family_rhinitis")),
                    "family_allergic_conjunctivitis": ",".join(request.form.getlist("family_allergic_conjunctivitis")),
                    "family_atopic_dermatitis": ",".join(request.form.getlist("family_atopic_dermatitis")),

                    "work_performance": request.form.get("work_performance"),
                    "physical_activity_problem": request.form.get("physical_activity_problem"),
                    "stairs_problem": request.form.get("stairs_problem"),

                    "work_less_physical": request.form.get("work_less_physical"),
                    "work_careful_physical": request.form.get("work_careful_physical"),

                    "work_less_emotional": request.form.get("work_less_emotional"),
                    "work_careless_emotional": request.form.get("work_careless_emotional"),

                    "daily_activity_limit": request.form.get("daily_activity_limit"),

                    "feel_calm": request.form.get("feel_calm"),
                    "feel_energetic": request.form.get("feel_energetic"),
                    "feel_sad": request.form.get("feel_sad"),
                    "social_limit": request.form.get("social_limit"),
                }

                columns = ", ".join(history_data.keys())
                placeholders = ", ".join(["%s"] * len(history_data))

                cur.execute(
                    f"""
                    INSERT INTO patient_history (user_id, {columns})
                    VALUES (%s, {placeholders})
                    """,
                    (user_id, *history_data.values())
                )

            conn.commit()

            flash(
                "สมัครสมาชิกสำเร็จ กรุณาเข้าสู่ระบบและกรอกแบบประเมินอาการ\n\n"
                "Signup successful. Please log in and complete the assessment form.",
                "success"
            )
            return redirect(url_for("login"))

        except Exception as e:
            conn.rollback()
            flash(f"Signup error: {e}", "danger")

        finally:
            conn.close()

    return render_template("signup.html")

# ---------- Doctor Dashboard ---------- #
@app.route("/doctor_dashboard")
def doctor_dashboard():
    if session.get("role") != "doctor":
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT 
            u.id,
            u.full_name,
            p.phone,
            p.email,
            COUNT(s.id) AS record_count
        FROM users u
        LEFT JOIN patient_profiles p ON u.id = p.user_id
        LEFT JOIN symptoms s ON u.id = s.user_id
        WHERE u.role = 'patient'
        GROUP BY u.id, u.full_name, p.phone, p.email
        ORDER BY u.full_name
    """)

    patients = cur.fetchall()
    conn.close()

    return render_template("doctor_dashboard.html", patients=patients)


## ---------- Doctor Stats ---------- #
@app.route("/doctor_stats")
def doctor_stats():
    if session.get("role") != "doctor":
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()

    # total patients
    cur.execute(
        "SELECT COUNT(*) AS c FROM users WHERE role = 'patient'"
    )
    total_patients = cur.fetchone()["c"]

    # gender breakdown
    cur.execute("""
        SELECT COALESCE(p.gender, 'unknown') AS gender, COUNT(*) AS c
        FROM users u
        LEFT JOIN patient_profiles p ON u.id = p.user_id
        WHERE u.role = 'patient'
        GROUP BY COALESCE(p.gender, 'unknown')
    """)
    gender_rows = cur.fetchall()
    genders = {r["gender"] or "unknown": r["c"] for r in gender_rows}

    # latest symptom row per patient
    cur.execute("""
        SELECT s.*
        FROM symptoms s
        WHERE s.id IN (
            SELECT MAX(id)
            FROM symptoms
            GROUP BY user_id
        )
    """)
    latest_rows = cur.fetchall()

    conn.close()

    # compute combos and treatment / VAS counts in Python
    im_mild = im_mod = per_mild = per_mod = 0
    treatments = {
        "oral_antihistamine": 0,
        "incs": 0,
        "ltra": 0,
        "saline": 0,
        "referral": 0
    }
    vas_counts = [0] * 11  # 0..10

    for r in latest_rows:
        pattern = (r["pattern"] or "").lower()
        avg_vas = float(r["avg_vas"]) if r["avg_vas"] is not None else 0.0
        severity = "mild" if avg_vas < 5 else "modsev"

        if pattern == "intermittent":
            if severity == "mild":
                im_mild += 1
            else:
                im_mod += 1
        elif pattern == "persistent":
            if severity == "mild":
                per_mild += 1
            else:
                per_mod += 1

        rec = (r["recommendation"] or "").lower()
        if "ฮิสตามีน" in rec or "antihistamine" in rec or "oral_ah" in rec:
            treatments["oral_antihistamine"] += 1
        if "สเตียรอยด์" in rec or "steroid" in rec or "incs" in rec:
            treatments["incs"] += 1
        if "leukotriene" in rec or "ltra" in rec or "leuko" in rec:
            treatments["ltra"] += 1
        if "ล้างจมูกด้วยน้ำเกลือ" in rec or "normal saline" in rec or "saline" in rec:
            treatments["saline"] += 1
        if "ส่งพบแพทย์" in rec or "refer" in rec or "ผ่าตัด" in rec:
            treatments["referral"] += 1

        v = int(round(avg_vas))
        if v < 0:
            v = 0
        if v > 10:
            v = 10
        vas_counts[v] += 1

    combo_counts = [im_mild, im_mod, per_mild, per_mod]

    return render_template(
        "doctor_stats.html",
        total_patients=total_patients,
        genders=genders,
        combo_counts=combo_counts,
        treatments=treatments,
        vas_counts=vas_counts
    )

# ---------- Patient Detail ---------- #
@app.route("/patient/<int:patient_id>")
def patient_detail(patient_id):
    if session.get("role") != "doctor":
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()

    # patient + profile + history
    cur.execute("""
        SELECT 
            u.id,
            u.full_name,

            -- profile
            p.email,
            p.phone,
            p.address,
            p.dob,
            p.gender,
            p.emergency_contact,
            p.insurance_provider,
            p.hospital_number,

            -- history
            h.symptom_year_pattern,
            h.season_summer, h.season_rainy, h.season_winter,
            h.season_summer_rainy, h.season_rainy_winter, h.season_uncertain,
            h.duration_per_year, h.weekly_frequency,
            h.time_6_12, h.time_12_18, h.time_18_24, h.time_24_6, h.time_all_day, h.time_uncertain,
            h.living_area, h.near_road, h.housing_type, h.air_conditioner,
            h.pet_cat, h.pet_dog, h.pet_bird, h.pet_other,
            h.trigger_dust, h.trigger_pollen, h.trigger_animal,
            h.trigger_smoke, h.trigger_cold_air, h.trigger_pollution, h.trigger_stress, h.trigger_other,
            h.smoking_status, h.cigarettes_per_day, h.quit_years, h.secondhand_smoke,
            h.drug_allergy, h.drug_allergy_name, h.drug_allergy_symptom,
            h.food_allergy, h.food_allergy_name, h.food_allergy_symptom,
            h.natural_allergy, h.natural_allergy_symptom,
            h.family_asthma, h.family_rhinitis, h.family_allergic_conjunctivitis, h.family_atopic_dermatitis,
            h.work_performance, h.physical_activity_problem, h.stairs_problem,
            h.work_less_physical, h.work_careful_physical,
            h.work_less_emotional, h.work_careless_emotional,
            h.daily_activity_limit,
            h.feel_calm, h.feel_energetic, h.feel_sad, h.social_limit
        FROM users u
        LEFT JOIN patient_profiles p ON u.id = p.user_id
        LEFT JOIN patient_history h ON u.id = h.user_id
        WHERE u.id = %s
    """, (patient_id,))
    patient = cur.fetchone()

    # all symptom rows
    cur.execute("""
        SELECT * FROM symptoms
        WHERE user_id = %s
        ORDER BY created_at DESC
    """, (patient_id,))
    rows = cur.fetchall()

    # VAS rows (date-wise)
    cur.execute("""
        SELECT DATE(created_at) AS date, avg_vas, recommendation
        FROM symptoms
        WHERE user_id = %s
        ORDER BY DATE(created_at)
    """, (patient_id,))
    vas_rows = cur.fetchall()

    conn.close()

    reports = [{
        "created_at": r["created_at"],
        "tnss": r["tnss"],
        "pattern": r["pattern"],
        "avg_vas": r["avg_vas"],
        "follow_up": r["follow_up"],
        "recommendation": r["recommendation"],
        "data": r["raw_form"] if r["raw_form"] else {}
    } for r in rows]

    return render_template(
        "patient_detail.html",
        patient=patient,
        reports=reports,
        vas_rows=vas_rows
    )

# ---------- Patient Form ---------- #
@app.route("/patient_form", methods=["GET", "POST"])
def patient_form():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()

    # latest record
    cur.execute("""
        SELECT * FROM symptoms
        WHERE user_id = %s
        ORDER BY created_at DESC
        LIMIT 1
    """, (session["user_id"],))
    last = cur.fetchone()

    follow_up = last["follow_up"] if last else 0
    need_followup = follow_up in (1, 2)
    next_allowed = None

    if last:
        last_date = last["created_at"]  # already datetime
        next_allowed = last_date + timedelta(days=14)

    # ---------- POST ----------
    if request.method == "POST":
        report_date = datetime.fromisoformat(request.form["report_date"])

        if last and report_date < next_allowed:
            flash(f"กรอกได้อีกครั้งวันที่ {next_allowed:%Y-%m-%d}", "warning")
            return redirect(url_for("patient_form"))

        freq = int(request.form["symptom_frequency"])
        avg_vas = (float(request.form["vas_score1"])+float(request.form["vas_score2"])+float(request.form["vas_score3"]))/3
        pattern = classify_pattern(freq)
        used_steroid = request.form.get("used_steroid_before", "no")
        prev_follow_up = follow_up

        tnss = (
            int(request.form.get("Frequently sneeze", 0)) +
            int(request.form.get("Stuffed nose", 0)) +
            int(request.form.get("runny nose", 0)) +
            int(request.form.get("itchy nose", 0))
        )

        # 1️⃣ recommendation first
        recommendation = generate_recommendation(
            pattern, avg_vas, prev_follow_up, used_steroid
        )

        # 2️⃣ follow-up logic
        next_follow_up = prev_follow_up
        if avg_vas < 5 and pattern == "intermittent":
            next_follow_up = 0
        elif prev_follow_up == 0 and avg_vas >= 5:
            next_follow_up = 1
        elif prev_follow_up == 1 and avg_vas >= 5:
            next_follow_up = 2 if used_steroid == "yes" else 1
        elif prev_follow_up == 2 and avg_vas >= 5:
            next_follow_up = 3

        # Create dictionary from form data and explicitly add VAS scores
        form_data = {k: request.form.get(k) for k in request.form}
        form_data['vas_score1'] = request.form.get('vas_score1')
        form_data['vas_score2'] = request.form.get('vas_score2')
        form_data['vas_score3'] = request.form.get('vas_score3')
        raw_form = json.dumps(form_data)


        # ----- medicine_effect: update previous row -----
        medicine_effect_answer = request.form.get("medicine_effect")
        if last and medicine_effect_answer:
            try:
                me_val = int(medicine_effect_answer)
                cur.execute(
                    "UPDATE symptoms SET medicine_effect = %s WHERE id = %s",
                    (me_val, last["id"])
                )
            except ValueError:
                pass

        # insert new record
        cur.execute("""
            INSERT INTO symptoms
            (user_id, avg_vas, tnss, pattern, recommendation,
             follow_up, created_at, raw_form, medicine_effect)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            session["user_id"],
            avg_vas,
            tnss,
            pattern,
            recommendation,
            next_follow_up,
            report_date.isoformat(),
            raw_form,          # JSONB
            None
        ))

        conn.commit()
        conn.close()

        flash("บันทึกข้อมูลเรียบร้อย ดูผลการประเมินที่หน้า Result", "success")
        return redirect(url_for("patient_form", show_result="1"))

    # ================= GET =================
    cur.execute(
        "SELECT * FROM symptoms WHERE user_id = %s ORDER BY created_at DESC",
        (session["user_id"],)
    )
    reports = cur.fetchall()

    cur.execute("""
        SELECT 
            u.full_name,
            p.email,
            p.phone,
            p.gender,
            p.dob,
            p.address
        FROM users u
        LEFT JOIN patient_profiles p ON u.id = p.user_id
        WHERE u.id = %s
    """, (session["user_id"],))
    patient = cur.fetchone()

    conn.close()

    show_medicine_effect_question = bool(last)

    latest_html = ""
    if reports:
        r = reports[0]
        latest_html = Markup(
            f"<b>Date:</b> {r['created_at'].date()}<br>"
            f"<b>Pattern:</b> {r['pattern']}<br>"
            f"<b>VAS:</b> {r['avg_vas']}<br>"
            f"<b>Follow-up:</b> {r['follow_up']}<br>"
            f"<pre>{r['recommendation']}</pre>"
        )

    return render_template(
        "patient_form.html",
        patient=patient,
        reports=reports,
        latest_html=latest_html,
        today=datetime.utcnow().strftime("%Y-%m-%d"),
        need_followup=need_followup,
        show_medicine_effect_question=show_medicine_effect_question
    )

# ---------- Logout ---------- #
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__=="__main__":
    app.run(debug=True,port=5000)
