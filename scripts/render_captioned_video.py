#!/usr/bin/env python3
import os
import re
import sys
import wave
import subprocess

workspace = "/Users/yashrawat/Downloads/sidework"
ffmpeg_bin = os.path.join(workspace, "node_modules/ffmpeg-static/ffmpeg")
if not os.path.exists(ffmpeg_bin):
    ffmpeg_bin = "ffmpeg"

def get_audio_duration(file_path):
    try:
        with wave.open(file_path, 'rb') as w:
            frames = w.getnframes()
            rate = w.getframerate()
            return frames / float(rate)
    except Exception as e:
        print(f"Error reading wave duration: {e}", file=sys.stderr)
        return 53.68

def parse_markdown_title(md_path):
    if not os.path.exists(md_path):
        return "PROTECT YOUR PEACE\nBoundary Toolkit"
    try:
        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()
        match = re.search(r'^#\s*(?:Ebook-Driven Marketing Script:\s*)?(.*)$', content, re.MULTILINE)
        if match:
            title_text = match.group(1).strip()
            # Remove emojis and trailing space/special chars
            title_text = re.sub(r'[^\w\s:(),\-&\'"!]', '', title_text).strip()
            if ":" in title_text:
                parts = title_text.split(":", 1)
                return f"{parts[0].strip().upper()}\n{parts[1].strip()}"
            return title_text
    except Exception as e:
        print(f"Error parsing title: {e}", file=sys.stderr)
    return "PROTECT YOUR PEACE"

def parse_markdown_script(md_path):
    if not os.path.exists(md_path):
        print(f"Markdown script not found at {md_path}", file=sys.stderr)
        sys.exit(1)
        
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.split('\n')
    voiceover_text = ""
    in_voiceover = False
    
    for line in lines:
        if line.startswith('## Spoken Voiceover'):
            in_voiceover = True
            continue
        if in_voiceover:
            trimmed = line.strip()
            if not trimmed:
                continue
            if trimmed.startswith('*(') and trimmed.endswith(')*'):
                continue
            if trimmed.startswith('##'):
                break
            voiceover_text += trimmed + " "
            
    return voiceover_text.strip()

def split_into_phrases(voiceover_text):
    tokens = re.split(r'(\[[^\]]+\])', voiceover_text)
    phrases = []
    
    for token in tokens:
        token = token.strip()
        if not token:
            continue
            
        if token.startswith('[') and token.endswith(']'):
            cue_type = token.lower().strip('[]')
            phrases.append({
                'type': 'cue',
                'cue': cue_type,
                'raw': token
            })
        else:
            # Clean punctuation for splitting but preserve it in tokens
            sentences = re.split(r'([.?!,;—–]+)', token)
            i = 0
            while i < len(sentences):
                text_part = sentences[i].strip()
                punct = sentences[i+1].strip() if i+1 < len(sentences) else ""
                i += 2
                
                if not text_part:
                    continue
                    
                full_clause = text_part + punct
                words = full_clause.split()
                chunk_size = 3
                for j in range(0, len(words), chunk_size):
                    chunk = " ".join(words[j:j+chunk_size])
                    # Strip leading/trailing quote characters to prevent display/timeline glitches
                    chunk = chunk.strip().strip('\'"“”‘’').strip()
                    if not re.search(r'[a-zA-Z0-9]', chunk):
                        continue
                    phrases.append({
                        'type': 'text',
                        'text': chunk
                    })
                    
    return phrases

def calculate_timings(phrases, total_audio_duration):
    # Timings for cue types (realistic pauses for Gemini TTS)
    cue_pauses = {
        'long pause': 0.6,
        'silence': 0.6,
        'soft sigh': 0.1,
        'voice cracks': 0.0,
        'soft whisper': 0.0,
        'catch in throat': 0.0,
        'tremble': 0.0,
        'grounded with warmth': 0.0
    }
    
    # Timings for punctuation (realistic pauses for Gemini TTS)
    punct_pauses = {
        '.': 0.4,
        '?': 0.4,
        '!': 0.4,
        ',': 0.2,
        ';': 0.2,
        ':': 0.2,
        '—': 0.2,
        '–': 0.2
    }
    
    segments = []
    total_fixed_pause = 0.0
    total_est_spoken = 0.0
    
    for item in phrases:
        if item['type'] == 'cue':
            cue_name = item['cue']
            dur = cue_pauses.get(cue_name, 0.4)
            segments.append({
                'type': 'pause',
                'duration': dur
            })
            total_fixed_pause += dur
        else:
            text = item['text']
            words = re.sub(r'[^\w\s]', '', text).split()
            word_count = len(words)
            
            # Baseline word reading duration (0.35s per word)
            spoken_dur = word_count * 0.35
            
            # Look for trailing punctuation pause
            punct_dur = 0.0
            for char in reversed(text):
                if char in punct_pauses:
                    punct_dur = punct_pauses[char]
                    break
            
            segments.append({
                'type': 'text',
                'text': text,
                'spoken_dur_est': spoken_dur,
                'punct_dur': punct_dur
            })
            total_est_spoken += spoken_dur
            total_fixed_pause += punct_dur
            
    # Calculate word scale factor to fit the remaining time
    target_spoken = total_audio_duration - total_fixed_pause
    if target_spoken > 0 and total_est_spoken > 0:
        scale_factor = target_spoken / total_est_spoken
    else:
        # Fallback to scaling everything if pauses exceed audio length
        scale_factor = total_audio_duration / (total_est_spoken + total_fixed_pause)
        
    print(f"Timing Alignment Stats:")
    print(f"  Total Audio Duration: {total_audio_duration:.2f}s")
    print(f"  Fixed Pause Time: {total_fixed_pause:.2f}s")
    print(f"  Target Spoken Time: {target_spoken:.2f}s")
    print(f"  Estimated Spoken Time: {total_est_spoken:.2f}s")
    print(f"  Word Scale Factor: {scale_factor:.4f}")
    
    current_time = 0.0
    timed_segments = []
    
    for seg in segments:
        if seg['type'] == 'pause':
            current_time += seg['duration']
        else:
            start = current_time
            if target_spoken > 0:
                duration = seg['spoken_dur_est'] * scale_factor
                end = start + duration + seg['punct_dur']
                current_time = end
            else:
                duration = (seg['spoken_dur_est'] + seg['punct_dur']) * scale_factor
                end = start + duration
                current_time = end
                
            if end - start < 0.8:
                end = start + 0.8
                if current_time < end:
                    current_time = end
                    
            timed_segments.append({
                'text': seg['text'],
                'start': start,
                'end': end
            })
            
    return timed_segments

def format_time_ass(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centiseconds = int(round((seconds - int(seconds)) * 100))
    if centiseconds >= 100:
        centiseconds = 99
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"

def apply_hormozi_highlight(text):
    words = text.upper().split()
    highlighted_words = []
    for idx, w in enumerate(words):
        # Highlight every 3rd word in yellow {\c&H0000FFFF&}
        if idx % 3 == 1:
            highlighted_words.append(f"{{\\c&H0000FFFF&}}{w}{{\\c&H00FFFFFF&}}")
        else:
            highlighted_words.append(w)
    return " ".join(highlighted_words)

def generate_ass_file(segments, title, output_ass_path):
    # Arial Black, bold, uppercase, thick outline, aligned top-center just below title card
    title_font = "Arial"
    title_size = "48"
    title_color = "&H00EDF9FF"   # Soft cream title
    title_outline = "3"
    title_shadow = "0"
    title_margin_v = "180"
    
    caption_font = "Arial"
    caption_size = "64"          # Slightly smaller than 76 to fit cleanly under title card
    caption_color = "&H00FFFFFF"  # White text
    caption_outline = "4"         # Thick black outline
    caption_shadow = "0"
    caption_italic = "0"
    caption_border_style = "1"
    caption_back_color = "&H00000000"
    caption_alignment = "8"       # Aligned top-center below title card
    caption_margin_v = "380"      # Positioned below title card (at 180)

    ass_template = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: TitleCard,{title_font},{title_size},{title_color},&H00000000,&H80000000,&H00000000,1,0,0,0,100,100,0,0,1,{title_outline},{title_shadow},8,60,60,{title_margin_v},1
Style: ActiveCaptions,{caption_font},{caption_size},{caption_color},&H0000FFFF,&H00000000,{caption_back_color},1,{caption_italic},0,0,100,100,1,0,{caption_border_style},{caption_outline},{caption_shadow},{caption_alignment},80,80,{caption_margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    end_time_str = format_time_ass(segments[-1]['end'] + 1.0)
    title_escaped = title.replace("\n", "\\N")
    
    events_section = []
    events_section.append(
        f"Dialogue: 0,0:00:00.00,{end_time_str},TitleCard,,0,0,0,,{title_escaped}"
    )
    
    for seg in segments:
        start_str = format_time_ass(seg['start'])
        end_str = format_time_ass(seg['end'])
        text = seg['text']
        
        # Apply Hormozi styled highlighting
        text = apply_hormozi_highlight(text)
            
        events_section.append(
            f"Dialogue: 1,{start_str},{end_str},ActiveCaptions,,0,0,0,,{text}"
        )
        
    full_ass = ass_template + "\n".join(events_section)
    
    with open(output_ass_path, 'w', encoding='utf-8') as f:
        f.write(full_ass)

def create_yoyo_loop_video(input_video_path, temp_reversed_path, temp_yoyo_path):
    print("Step A: Creating reversed segment of the video...")
    cmd_rev = [
        ffmpeg_bin, "-y",
        "-i", input_video_path,
        "-vf", "reverse",
        "-an",
        temp_reversed_path
    ]
    subprocess.run(cmd_rev, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    
    print("Step B: Stitching forward and reversed video together to make a seamless yo-yo loop...")
    cmd_concat = [
        ffmpeg_bin, "-y",
        "-i", input_video_path,
        "-i", temp_reversed_path,
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
        "-map", "[v]",
        temp_yoyo_path
    ]
    subprocess.run(cmd_concat, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    print(f"Yo-yo seamless loop segment created at: {temp_yoyo_path}")

def render_video(video_path, audio_path, ass_path, output_path, duration):
    print(f"Rendering Hormozi styled video reel...")
    cmd = [
        ffmpeg_bin,
        "-y",
        "-stream_loop", "-1",          # Loop the input video infinitely
        "-i", video_path,              # Input yo-yo looped video
        "-i", audio_path,              # Input audio (mixed voiceover)
        "-vf", f"subtitles={ass_path}",# Burn ASS subtitles
        "-c:v", "libx264",             # H.264 video codec
        "-preset", "fast",             # Encoding speed preset
        "-crf", "22",                  # Constant Rate Factor for good quality
        "-c:a", "aac",                 # AAC audio codec
        "-b:a", "192k",                # Audio bitrate
        "-map", "0:v:0",               # Map video stream from video file
        "-map", "1:a:0",               # Map audio stream from audio file
        "-t", f"{duration:.2f}",       # Cap video length to match audio exactly
        output_path
    ]
    
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    print(f"Successfully rendered video: {output_path}")

def main():
    video_file = os.path.join(workspace, "Animate_head_top_visual_effect_202606071706.mp4")
    audio_file = os.path.join(workspace, "generated-audio/mixed-voiceover-latest.wav")
    script_file = os.path.join(workspace, "generated-audio/marketing-script-latest.md")
    
    temp_reversed = os.path.join(workspace, "generated-audio/temp_reversed.mp4")
    temp_yoyo = os.path.join(workspace, "generated-audio/temp_yoyo.mp4")
    
    if not os.path.exists(video_file) or not os.path.exists(audio_file):
        print("Missing required source video or audio assets.", file=sys.stderr)
        sys.exit(1)
        
    duration = get_audio_duration(audio_file)
    voiceover_text = parse_markdown_script(script_file)
    phrases = split_into_phrases(voiceover_text)
    
    # Run the advanced alignment timing calculator (prevents caption drift)
    timed_segments = calculate_timings(phrases, duration)
    
    # Generate the Yo-Yo loop video segment once
    create_yoyo_loop_video(video_file, temp_reversed, temp_yoyo)
    
    # Parse title dynamically from the markdown script (updates Part number on every run)
    title = parse_markdown_title(script_file)
    print(f"Dynamic Title parsed: {title.replace(chr(10), ' ')}")
    
    # Generate only the HORMOZI style video
    ass_path = os.path.join(workspace, "generated-audio/captions_hormozi.ass")
    output_video_path = os.path.join(workspace, "generated-audio/rendered_reel_hormozi.mp4")
    latest_video_path = os.path.join(workspace, "generated-audio/rendered_reel_latest.mp4")
    
    generate_ass_file(timed_segments, title, ass_path)
    render_video(temp_yoyo, audio_file, ass_path, output_video_path, duration)
    
    # Also save as rendered_reel_latest.mp4 for convenience
    import shutil
    shutil.copyfile(output_video_path, latest_video_path)
    print(f"Saved shortcut copy to: {latest_video_path}")
        
    # Clean up temporary yoyo assets
    if os.path.exists(temp_reversed):
        os.remove(temp_reversed)
    if os.path.exists(temp_yoyo):
        os.remove(temp_yoyo)
        
    print("\nHormozi styled captioned reel generated successfully!")

if __name__ == "__main__":
    main()
