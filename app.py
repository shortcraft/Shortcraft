# ShortCraft - Web Interface v2.0

from flask import Flask, request, jsonify, send_file, redirect, url_for, session, render_template
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from auth import db, login_manager, User
import os
import whisper
import numpy as np
from moviepy import VideoFileClip, TextClip, CompositeVideoClip, concatenate_videoclips

app = Flask(__name__)
app.secret_key = "shortcraft2026"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"

db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = "login"

with app.app_context():
    db.create_all()

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "outputs"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ─── SIGNUP ───────────────────────
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name     = request.form.get("name")
        email    = request.form.get("email")
        password = request.form.get("password")

        existing = User.query.filter_by(email=email).first()
        if existing:
            return render_template("signup.html", error="Email already exists")

        new_user = User(
            name     = name,
            email    = email,
            password = generate_password_hash(password)
        )
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for("home"))

    return render_template("signup.html")

# ─── LOGIN ────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email    = request.form.get("email")
        password = request.form.get("password")
        user     = User.query.filter_by(email=email).first()

        if not user or not check_password_hash(user.password, password):
            return render_template("login.html", error="Invalid email or password")

        login_user(user)
        return redirect(url_for("home"))

    return render_template("login.html")

# ─── LOGOUT ───────────────────────
@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# ─── HOME / DASHBOARD ─────────────
@app.route("/")
@login_required
def home():
    return render_template("dashboard.html",
        name         = current_user.name,
        shorts_count = 0
    )

# ─── UPLOAD ───────────────────────
@app.route("/upload", methods=["POST"])
@login_required
def upload():
    if "video" not in request.files:
        return jsonify({"success": False, "error": "No file"})
    file     = request.files["video"]
    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)
    return jsonify({"success": True, "filename": file.filename})

# ─── EDIT ─────────────────────────
@app.route("/edit", methods=["POST"])
@login_required
def edit():
    try:
        data     = request.get_json()
        filename = data["filename"]
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        output   = "ShortCraft_" + filename
        out_path = os.path.join(OUTPUT_FOLDER, output)

        # 1. Load video
        video    = VideoFileClip(filepath)
        duration = video.duration

        # 2. Find emotional peaks
        audio      = video.audio
        energy_map = []
        for second in range(int(duration)):
            end     = min(second + 1, duration)
            chunk   = audio.subclipped(second, end)
            samples = chunk.get_frame(0)
            energy  = float(np.mean(np.abs(samples)))
            energy_map.append((second, energy))

        sorted_peaks = sorted(energy_map, key=lambda x: x[1], reverse=True)
        selected = []
        for peak in sorted_peaks:
            too_close = any(abs(peak[0] - s[0]) < 30 for s in selected)
            if not too_close:
                selected.append(peak)
            if len(selected) == 3:
                break

        selected = sorted(selected, key=lambda x: x[0])

        # 3. Build cut ranges
        cut_ranges = []
        for peak in selected:
            cut_start = max(0, peak[0] - 8)
            cut_end   = min(duration, peak[0] + 8)
            cut_ranges.append((cut_start, cut_end))

        # 4. Build clips
        clips = []
        for cs, ce in cut_ranges:
            clips.append(video.subclipped(cs, ce))

        short = concatenate_videoclips(clips)
        dur   = short.duration

        # 5. Captions
        model     = whisper.load_model("base")
        result    = model.transcribe(filepath)
        cap_clips = []

        for seg in result["segments"]:
            s    = seg["start"]
            e    = min(seg["end"], dur)
            text = seg["text"].strip().upper()

            if not text or s > dur:
                continue

            in_cut = any(cs <= s <= ce for cs, ce in cut_ranges)
            if not in_cut:
                continue

            words  = text.split()
            chunks = [words[i:i+3] for i in range(0, len(words), 3)]
            tpc    = (e - s) / max(len(chunks), 1)

            for j, chunk in enumerate(chunks):
                cs2 = s + j * tpc
                ce2 = min(cs2 + tpc, dur)
                if cs2 >= dur:
                    continue
                tc = TextClip(
                    text         = " ".join(chunk),
                    font_size    = 40,
                    color        = "white",
                    font         = "C:/Windows/Fonts/arialbd.ttf",
                    stroke_color = "black",
                    stroke_width = 2,
                    size         = (1800, 100),
                    method       = "caption",
                )
                tc = tc.with_start(cs2).with_end(ce2).with_position(("center", 700))
                cap_clips.append(tc)

        # 6. Composite and export
        final = CompositeVideoClip([short] + cap_clips)
        final.write_videofile(out_path, fps=30, codec="libx264", audio_codec="aac")

        video.close()
        final.close()

        return jsonify({"success": True, "output": output})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

# ─── DOWNLOAD ─────────────────────
@app.route("/download/<filename>")
@login_required
def download(filename):
    return send_file(os.path.join(OUTPUT_FOLDER, filename), as_attachment=True)

# ─── START SERVER ─────────────────
if __name__ == "__main__":
    print("=" * 40)
    print("  ShortCraft Web Server Starting...")
    print("  Open: http://localhost:5000")
    print("=" * 40)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
