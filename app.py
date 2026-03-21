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
login_manager.login_view = "landing"

with app.app_context():
    db.create_all()

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "outputs"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# LANDING
@app.route("/landing")
def landing():
    return render_template("landing.html")

# SIGNUP
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name     = request.form.get("name")
        email    = request.form.get("email")
        password = request.form.get("password")
        existing = User.query.filter_by(email=email).first()
        if existing:
            return render_template("signup.html", error="Email already exists")
        new_user = User(name=name, email=email, password=generate_password_hash(password))
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for("home"))
    return render_template("signup.html")

# LOGIN
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

# LOGOUT
@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("landing"))

# HOME
@app.route("/")
@login_required
def home():
    return render_template("dashboard.html", name=current_user.name, shorts_count=0)

# UPLOAD
@app.route("/upload", methods=["POST"])
@login_required
def upload():
    if "video" not in request.files:
        return jsonify({"success": False, "error": "No file"})
    file     = request.files["video"]
    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)
    return jsonify({"success": True, "filename": file.filename})

# EDIT
@app.route("/edit", methods=["POST"])
@login_required
def edit():
    try:
        data     = request.get_json()
        filename = data["filename"]
        prompt   = data.get("prompt", "")
        template = data.get("template", "viral")
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        output   = "ShortCraft_" + filename
        out_path = os.path.join(OUTPUT_FOLDER, output)

        print(f"Template: {template} | Prompt: {prompt}")

        TEMPLATES = {
            "viral":     {"energy": "high",   "length": 24, "clip_count": 4, "captions": True,  "caption_words": 3},
            "cinematic": {"energy": "low",    "length": 48, "clip_count": 3, "captions": False, "caption_words": 0},
            "talking":   {"energy": "speech", "length": 36, "clip_count": 5, "captions": True,  "caption_words": 5},
        }

        ai = TEMPLATES.get(template, TEMPLATES["viral"]).copy()

        if prompt:
            p = prompt.lower()
            if any(w in p for w in ["calm", "slow", "cinematic", "peaceful"]): ai["energy"] = "low"
            if any(w in p for w in ["fast", "energy", "hype", "viral"]):       ai["energy"] = "high"
            if any(w in p for w in ["no caption", "no captions"]):             ai["captions"] = False
            if any(w in p for w in ["caption", "captions", "text"]):           ai["captions"] = True
            for word in p.split():
                if word.isdigit() and 10 <= int(word) <= 120:
                    ai["length"] = int(word)

        print(f"AI settings: {ai}")

        # 1. Load video
        video    = VideoFileClip(filepath)
        duration = video.duration

        # 2. Scan audio energy
        audio      = video.audio
        energy_map = []
        for second in range(int(duration)):
            end     = min(second + 1, duration)
            chunk   = audio.subclipped(second, end)
            samples = chunk.get_frame(0)
            energy  = float(np.mean(np.abs(samples)))
            energy_map.append((second, energy))

        # 3. Find peaks
        clip_count  = ai.get("clip_count", 3)
        clip_length = max(4, ai.get("length", 48) // clip_count)

        if ai.get("energy") == "speech":
            model_w  = whisper.load_model("base")
            segments = model_w.transcribe(filepath)["segments"][:clip_count]
            selected = [(int(seg["start"]), 0.5) for seg in segments]
            if not selected:
                selected = sorted(energy_map, key=lambda x: x[1], reverse=True)[:clip_count]
        else:
            sorted_peaks   = sorted(energy_map, key=lambda x: x[1], reverse=True)
            final_selected = []
            for peak in sorted_peaks:
                too_close = any(abs(peak[0] - s[0]) < clip_length for s in final_selected)
                if not too_close:
                    final_selected.append(peak)
                if len(final_selected) == clip_count:
                    break
            selected = sorted(final_selected, key=lambda x: x[0])

        # 4. Build cut ranges
        cut_ranges = []
        for peak in selected:
            cut_start = max(0, peak[0] - clip_length // 2)
            cut_end   = min(duration, peak[0] + clip_length // 2)
            cut_ranges.append((cut_start, cut_end))

        # 5. Build clips
        clips = []
        for cs, ce in cut_ranges:
            clips.append(video.subclipped(cs, ce))

        short = concatenate_videoclips(clips)
        dur   = short.duration

        # 6. Captions
        use_captions = ai.get("captions", True)
        cap_words    = max(1, ai.get("caption_words", 3))
        cap_clips    = []

        if use_captions:
            model_w = whisper.load_model("base")
            result  = model_w.transcribe(filepath)
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
                chunks = [words[i:i+cap_words] for i in range(0, len(words), cap_words)]
                tpc    = (e - s) / max(len(chunks), 1)
                for j, chunk in enumerate(chunks):
                    cs2 = s + j * tpc
                    ce2 = min(cs2 + tpc, dur)
                    if cs2 >= dur:
                        continue
                    tc = TextClip(
                        text=" ".join(chunk), font_size=40, color="white",
                        font="C:/Windows/Fonts/arialbd.ttf", stroke_color="black",
                        stroke_width=2, size=(1800, 100), method="caption",
                    )
                    tc = tc.with_start(cs2).with_end(ce2).with_position(("center", 700))
                    cap_clips.append(tc)

        # 7. Export
        final = CompositeVideoClip([short] + cap_clips)
        final.write_videofile(out_path, fps=30, codec="libx264", audio_codec="aac")
        video.close()
        final.close()

        return jsonify({"success": True, "output": output})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

# DOWNLOAD
@app.route("/download/<filename>")
@login_required
def download(filename):
    return send_file(os.path.join(OUTPUT_FOLDER, filename), as_attachment=True)

# START
if __name__ == "__main__":
    print("=" * 40)
    print("  ShortCraft Web Server Starting...")
    print("  Open: http://localhost:5000")
    print("=" * 40)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
