# ================================
# SHORTCRAFT AI - FULL ENGINE v1.0
# ================================

import whisper
import librosa
import numpy as np
from moviepy import VideoFileClip, TextClip, CompositeVideoClip, concatenate_videoclips

def analyze_video(video_path):
    print(f"\n[1/5] Loading video: {video_path}")
    video    = VideoFileClip(video_path)
    duration = video.duration
    print(f"Duration: {duration:.1f}s | FPS: {video.fps} | Size: {video.size}")
    return video, duration

def find_emotional_peaks(video, duration):
    print("\n[2/5] Scanning for emotional peaks...")
    audio      = video.audio
    energy_map = []

    for second in range(int(duration)):
        start   = second
        end     = min(second + 1, duration)
        chunk   = audio.subclipped(start, end)
        samples = chunk.get_frame(0)
        energy  = float(np.mean(np.abs(samples)))
        energy_map.append((second, energy))

    # Find top 3 peaks at least 30s apart
    sorted_peaks  = sorted(energy_map, key=lambda x: x[1], reverse=True)
    selected      = []

    for peak in sorted_peaks:
        too_close = any(abs(peak[0] - s[0]) < 30 for s in selected)
        if not too_close:
            selected.append(peak)
        if len(selected) == 3:
            break

    selected = sorted(selected, key=lambda x: x[0])
    print(f"Found {len(selected)} emotional peaks:")
    for p in selected:
        print(f"  → {p[0]}s (energy: {p[1]:.4f})")
    return selected

def build_clips(video, peaks, duration):
    print("\n[3/5] Building clips from peaks...")
    clips = []
    for peak in peaks:
        start = max(0, peak[0] - 8)
        end   = min(duration, peak[0] + 8)
        clip  = video.subclipped(start, end)
        clips.append(clip)
        print(f"  → Clip: {start}s to {end}s")

    final = concatenate_videoclips(clips)
    print(f"Total short duration: {final.duration:.1f}s")
    return final

def add_captions(clip, source_video_path):
    print("\n[4/5] Adding captions with Whisper AI...")
    model    = whisper.load_model("base")
    result   = model.transcribe(source_video_path)
    duration = clip.duration
    caption_clips = []

    for segment in result["segments"]:
        start = segment["start"]
        end   = segment["end"]
        text  = segment["text"].strip().upper()

        if not text or start > duration:
            continue

        end    = min(end, duration)
        words  = text.split()
        chunks = [words[i:i+3] for i in range(0, len(words), 3)]
        time_per_chunk = (end - start) / max(len(chunks), 1)

        for j, chunk in enumerate(chunks):
            chunk_text  = " ".join(chunk)
            chunk_start = start + (j * time_per_chunk)
            chunk_end   = min(chunk_start + time_per_chunk, duration)

            if chunk_start >= duration:
                continue

            txt_clip = TextClip(
                text         = chunk_text,
                font_size    = 40,
                color        = "white",
                font         = "C:/Windows/Fonts/arialbd.ttf",
                stroke_color = "black",
                stroke_width = 2,
                size         = (1800, 100),
                method       = "caption",
            )
            txt_clip = txt_clip.with_start(chunk_start)
            txt_clip = txt_clip.with_end(chunk_end)
            txt_clip = txt_clip.with_position(("center", 700))
            caption_clips.append(txt_clip)

    print(f"Added {len(caption_clips)} caption clips")
    return CompositeVideoClip([clip] + caption_clips)

def export(final, output_name):
    print(f"\n[5/5] Exporting: {output_name}")
    final.write_videofile(
        output_name,
        fps         = 30,
        codec       = "libx264",
        audio_codec = "aac",
    )
    print(f"\n✅ ShortCraft export complete: {output_name}")

# ================================
# RUN SHORTCRAFT
# ================================

VIDEO_INPUT  = "The Perfect Porsche Cinematic _4K_.mp4"
VIDEO_OUTPUT = "ShortCraft_FINAL.mp4"

print("=" * 40)
print("   SHORTCRAFT AI ENGINE v1.0")
print("=" * 40)

video,  duration = analyze_video(VIDEO_INPUT)
peaks            = find_emotional_peaks(video, duration)
short            = build_clips(video, peaks, duration)
captioned        = add_captions(short, VIDEO_INPUT)
export(captioned, VIDEO_OUTPUT)

video.close()

print("\n🎬 ShortCraft done. Your short is ready.")