# ShortCraft - Web Interface

from flask import Flask, request, jsonify, send_file
import os
import whisper
import numpy as np
from moviepy import VideoFileClip, TextClip, CompositeVideoClip, concatenate_videoclips

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "outputs"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ─── HOME PAGE ───────────────────
@app.route("/")
def home():
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>ShortCraft AI</title>
        <style>
            * { margin:0; padding:0; box-sizing:border-box; }
            body {
                background: #0C0C0E;
                color: #fff;
                font-family: monospace;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                min-height: 100vh;
            }
            h1 { font-size: 48px; color: #F59E0B; margin-bottom: 8px; }
            p  { color: rgba(255,255,255,.4); margin-bottom: 40px; font-size: 16px; }
            .box {
                border: 2px dashed rgba(245,158,11,.4);
                border-radius: 16px;
                padding: 60px 80px;
                text-align: center;
                cursor: pointer;
                transition: all .3s;
                margin-bottom: 24px;
            }
            .box:hover { border-color: #F59E0B; background: rgba(245,158,11,.05); }
            .box-icon  { font-size: 48px; margin-bottom: 16px; }
            .box-title { font-size: 20px; font-weight: bold; margin-bottom: 8px; }
            .box-sub   { color: rgba(255,255,255,.35); font-size: 14px; }
            input[type=file] { display: none; }
            .btn {
                background: #F59E0B;
                color: #000;
                border: none;
                padding: 14px 40px;
                border-radius: 8px;
                font-size: 16px;
                font-weight: bold;
                cursor: pointer;
                font-family: monospace;
                transition: all .2s;
            }
            .btn:hover { background: #FBBF24; transform: translateY(-2px); }
            .btn:disabled { opacity: .4; cursor: not-allowed; transform: none; }
            #status {
                margin-top: 24px;
                color: #F59E0B;
                font-size: 14px;
                min-height: 24px;
            }
            #filename {
                color: #F59E0B;
                margin-top: 12px;
                font-size: 14px;
            }
        </style>
    </head>
    <body>
        <h1>ShortCraft.</h1>
        <p>AI-powered shorts editor — drop a video, get a short</p>

        <label for="fileInput">
            <div class="box" id="dropBox">
                <div class="box-icon">🎬</div>
                <div class="box-title">Drop your video here</div>
                <div class="box-sub">MP4 · MOV · AVI — click to browse</div>
            </div>
        </label>

        <input type="file" id="fileInput" accept="video/*">
        <div id="filename"></div>

        <button class="btn" id="editBtn" disabled onclick="uploadAndEdit()">
            ⚡ Generate Short
        </button>

        <div id="status"></div>

        <script>
            const fileInput = document.getElementById("fileInput");
            const editBtn   = document.getElementById("editBtn");
            const status    = document.getElementById("status");
            const filename  = document.getElementById("filename");

            fileInput.addEventListener("change", function() {
                if (fileInput.files.length > 0) {
                    editBtn.disabled = false;
                    filename.textContent = "Selected: " + fileInput.files[0].name;
                }
            });

            async function uploadAndEdit() {
                const file = fileInput.files[0];
                if (!file) return;

                editBtn.disabled = true;
                status.textContent = "Uploading video...";

                const formData = new FormData();
                formData.append("video", file);

                try {
                    status.textContent = "Uploading...";
                    const uploadRes  = await fetch("/upload", { method: "POST", body: formData });
                    const uploadData = await uploadRes.json();

                    if (!uploadData.success) {
                        status.textContent = "Upload failed.";
                        return;
                    }

                    status.textContent = "Analyzing video... this takes 1-2 mins ⚙️";

                    const editRes  = await fetch("/edit", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ filename: uploadData.filename })
                    });
                    const editData = await editRes.json();

                    if (editData.success) {
                        status.innerHTML = "✅ Done! <a href='/download/" + editData.output + "' style='color:#F59E0B'>Download your short</a>";
                    } else {
                        status.textContent = "Error: " + editData.error;
                    }

                } catch(e) {
                    status.textContent = "Something went wrong.";
                    editBtn.disabled = false;
                }
            }
        </script>
    </body>
    </html>
    '''

# ─── UPLOAD ───────────────────────
@app.route("/upload", methods=["POST"])
def upload():
    if "video" not in request.files:
        return jsonify({"success": False, "error": "No file"})
    file     = request.files["video"]
    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)
    return jsonify({"success": True, "filename": file.filename})

# ─── EDIT ─────────────────────────
@app.route("/edit", methods=["POST"])
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

        # 5. Captions — only on speech segments inside cut ranges
        model     = whisper.load_model("base")
        result    = model.transcribe(filepath)
        cap_clips = []

        for seg in result["segments"]:
            s    = seg["start"]
            e    = min(seg["end"], dur)
            text = seg["text"].strip().upper()

            if not text or s > dur:
                continue

            # Only caption if speech falls inside one of our cut ranges
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
def download(filename):
    return send_file(os.path.join(OUTPUT_FOLDER, filename), as_attachment=True)

# ─── START SERVER ─────────────────
if __name__ == "__main__":
    print("=" * 40)
    print("  ShortCraft Web Server Starting...")
    print("  Open: http://localhost:5000")
    print("=" * 40)
    app.run(debug=True)
