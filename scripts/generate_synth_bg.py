import wave
import math
import struct
import random

# ==========================================
# 1. Warm Rhodes/Lofi Arpeggio Generator
# ==========================================
def generate_lofi_arpeggio(filename, duration, sample_rate):
    print(f"Generating Lofi Arpeggio: {filename}...")
    wav_file = wave.open(filename, 'w')
    wav_file.setnchannels(1)
    wav_file.setsampwidth(2)
    wav_file.setframerate(sample_rate)
    
    notes = []
    for loop_start in range(0, int(duration) + 16, 16):
        overlap = 0.2
        notes.append((loop_start + 0.0, 4.0 + overlap, 87.31, 0.25, 'pad'))    # F2
        notes.append((loop_start + 4.0, 4.0 + overlap, 110.00, 0.25, 'pad'))   # A2
        notes.append((loop_start + 8.0, 4.0 + overlap, 116.54, 0.25, 'pad'))   # Bb2
        notes.append((loop_start + 12.0, 4.0 + overlap, 65.41, 0.25, 'pad'))    # C2
        
        # Arpeggios (pluck)
        notes.append((loop_start + 0.0, 4.0, 174.61, 0.12, 'pluck'))
        notes.append((loop_start + 1.0, 3.0, 261.63, 0.10, 'pluck'))
        notes.append((loop_start + 2.0, 2.0, 329.63, 0.09, 'pluck'))
        notes.append((loop_start + 3.0, 1.0, 440.00, 0.08, 'pluck'))
        
        notes.append((loop_start + 4.0, 4.0, 220.00, 0.12, 'pluck'))
        notes.append((loop_start + 5.0, 3.0, 329.63, 0.10, 'pluck'))
        notes.append((loop_start + 6.0, 2.0, 392.00, 0.09, 'pluck'))
        notes.append((loop_start + 7.0, 1.0, 523.25, 0.08, 'pluck'))
        
        notes.append((loop_start + 8.0, 4.0, 233.08, 0.12, 'pluck'))
        notes.append((loop_start + 9.0, 3.0, 349.23, 0.10, 'pluck'))
        notes.append((loop_start + 10.0, 2.0, 440.00, 0.09, 'pluck'))
        notes.append((loop_start + 11.0, 1.0, 587.33, 0.08, 'pluck'))
        
        notes.append((loop_start + 12.0, 4.0, 130.81, 0.12, 'pluck'))
        notes.append((loop_start + 13.0, 3.0, 196.00, 0.10, 'pluck'))
        notes.append((loop_start + 14.0, 2.0, 261.63, 0.09, 'pluck'))
        notes.append((loop_start + 15.0, 1.0, 349.23, 0.08, 'pluck'))

    total_frames = int(duration * sample_rate)
    chunk_size = 1024
    frames_written = 0
    
    while frames_written < total_frames:
        chunk_frames = min(chunk_size, total_frames - frames_written)
        packed_data = bytearray()
        for i in range(chunk_frames):
            t = float(frames_written + i) / sample_rate
            sample_val = 0.0
            for start, dur, freq, vol, note_type in notes:
                if start <= t < start + dur:
                    note_t = t - start
                    if note_type == 'pad':
                        fade_time = 0.6
                        env = note_t / fade_time if note_t < fade_time else ((dur - note_t) / fade_time if note_t > (dur - fade_time) else 1.0)
                        sample_val += vol * env * (math.sin(2 * math.pi * freq * t) + 0.35 * math.sin(2 * math.pi * (freq * 2.005) * t))
                    elif note_type == 'pluck':
                        env = math.exp(-note_t * 1.6)
                        sample_val += vol * env * (math.sin(2 * math.pi * freq * t) + 0.25 * math.sin(2 * math.pi * freq * 2.0 * t) + 0.10 * math.sin(2 * math.pi * freq * 3.0 * t))
            
            sample_val = sample_val / 2.2
            # Global fade
            if t < 2.0: sample_val *= (t / 2.0)
            elif t > (duration - 2.0): sample_val *= ((duration - t) / 2.0)
            
            int_val = int(sample_val * 32767.0)
            packed_data.extend(struct.pack('<h', max(-32768, min(32767, int_val))))
        wav_file.writeframes(packed_data)
        frames_written += chunk_frames
    wav_file.close()

# ==========================================
# 2. Deep Meditation Drone Generator
# ==========================================
def generate_meditation_drone(filename, duration, sample_rate):
    print(f"Generating Meditation Drone: {filename}...")
    wav_file = wave.open(filename, 'w')
    wav_file.setnchannels(1)
    wav_file.setsampwidth(2)
    wav_file.setframerate(sample_rate)
    
    # Beautiful rich low chords (C minor chord elements: C2, G2, C3, Eb3, G3)
    frequencies = [65.41, 98.00, 130.81, 155.56, 196.00]
    total_frames = int(duration * sample_rate)
    chunk_size = 1024
    frames_written = 0
    
    while frames_written < total_frames:
        chunk_frames = min(chunk_size, total_frames - frames_written)
        packed_data = bytearray()
        for i in range(chunk_frames):
            t = float(frames_written + i) / sample_rate
            sample_val = 0.0
            
            # Combine frequencies with slow, independent breathing LFOs
            for idx, freq in enumerate(frequencies):
                lfo = 0.5 + 0.4 * math.sin(2 * math.pi * (0.04 + 0.02 * idx) * t)
                # Adding slight warmth/harmonic detune
                sample_val += 0.20 * lfo * (math.sin(2 * math.pi * freq * t) + 0.25 * math.sin(2 * math.pi * (freq * 2.003) * t))
            
            # Low pass hum
            sample_val = sample_val / 1.0
            
            # Global fade
            if t < 3.0: sample_val *= (t / 3.0)
            elif t > (duration - 3.0): sample_val *= ((duration - t) / 3.0)
            
            int_val = int(sample_val * 32767.0)
            packed_data.extend(struct.pack('<h', max(-32768, min(32767, int_val))))
        wav_file.writeframes(packed_data)
        frames_written += chunk_frames
    wav_file.close()

# ==========================================
# 3. Soft Ocean Waves / Nature Soundscape
# ==========================================
def generate_ocean_waves(filename, duration, sample_rate):
    print(f"Generating Ocean Waves: {filename}...")
    wav_file = wave.open(filename, 'w')
    wav_file.setnchannels(1)
    wav_file.setsampwidth(2)
    wav_file.setframerate(sample_rate)
    
    total_frames = int(duration * sample_rate)
    chunk_size = 1024
    frames_written = 0
    
    # State for low-pass filter (exponential smoothing)
    smooth_noise_1 = 0.0
    smooth_noise_2 = 0.0
    
    while frames_written < total_frames:
        chunk_frames = min(chunk_size, total_frames - frames_written)
        packed_data = bytearray()
        for i in range(chunk_frames):
            t = float(frames_written + i) / sample_rate
            
            # White noise
            noise = random.uniform(-1.0, 1.0)
            
            # Low-pass filter (alpha = 0.015 makes it a very deep rumble)
            alpha = 0.015
            smooth_noise_1 = alpha * noise + (1 - alpha) * smooth_noise_1
            
            # Second stage smoothing (double low-pass for a rounder sound)
            smooth_noise_2 = alpha * smooth_noise_1 + (1 - alpha) * smooth_noise_2
            
            # Modulation LFO: Swells up and down slowly like ocean breathing (every 7 seconds)
            wave_lfo = 0.5 + 0.45 * math.sin(2 * math.pi * 0.14 * t)
            
            sample_val = smooth_noise_2 * wave_lfo * 2.8
            
            # Global fade
            if t < 2.0: sample_val *= (t / 2.0)
            elif t > (duration - 2.0): sample_val *= ((duration - t) / 2.0)
            
            int_val = int(sample_val * 32767.0)
            packed_data.extend(struct.pack('<h', max(-32768, min(32767, int_val))))
        wav_file.writeframes(packed_data)
        frames_written += chunk_frames
    wav_file.close()

# ==========================================
# 4. Minimal Piano / Singing Bowl
# ==========================================
def generate_minimal_piano(filename, duration, sample_rate):
    print(f"Generating Minimal Piano: {filename}...")
    wav_file = wave.open(filename, 'w')
    wav_file.setnchannels(1)
    wav_file.setsampwidth(2)
    wav_file.setframerate(sample_rate)
    
    notes = []
    # Play a single high-quality chime/singing bowl note every 5 seconds
    chime_freqs = [261.63, 329.63, 392.00, 523.25, 587.33, 659.25] # C4, E4, G4, C5, D5, E5
    
    for note_idx, start_time in enumerate(range(0, int(duration), 5)):
        freq = chime_freqs[note_idx % len(chime_freqs)]
        notes.append((start_time, 5.0, freq, 0.20))
        
    total_frames = int(duration * sample_rate)
    chunk_size = 1024
    frames_written = 0
    
    while frames_written < total_frames:
        chunk_frames = min(chunk_size, total_frames - frames_written)
        packed_data = bytearray()
        for i in range(chunk_frames):
            t = float(frames_written + i) / sample_rate
            sample_val = 0.0
            
            # Soft continuous warm chord pad in the background so it is not pure silence
            background_pad = 0.05 * (math.sin(2 * math.pi * 130.81 * t) + 0.25 * math.sin(2 * math.pi * 261.63 * t))
            sample_val += background_pad
            
            for start, dur, freq, vol in notes:
                if start <= t < start + dur:
                    note_t = t - start
                    # Very long decay (like a crystal bowl or bell)
                    env = math.exp(-note_t * 0.7)
                    # Chime timbre: high frequency content with resonance
                    sample_val += vol * env * (
                        math.sin(2 * math.pi * freq * t) + 
                        0.4 * math.sin(2 * math.pi * freq * 2.0 * t) + 
                        0.1 * math.sin(2 * math.pi * freq * 3.0 * t) +
                        0.05 * math.sin(2 * math.pi * freq * 4.0 * t)
                    )
            
            # Global fade
            if t < 2.0: sample_val *= (t / 2.0)
            elif t > (duration - 2.0): sample_val *= ((duration - t) / 2.0)
            
            int_val = int(sample_val * 32767.0)
            packed_data.extend(struct.pack('<h', max(-32768, min(32767, int_val))))
        wav_file.writeframes(packed_data)
        frames_written += chunk_frames
    wav_file.close()

# ==========================================
# Main script trigger
# ==========================================
if __name__ == "__main__":
    import os
    os.makedirs("generated-audio", exist_ok=True)
    
    # Generate all four options so they are ready as libraries
    generate_lofi_arpeggio("generated-audio/bg-lofi-arpeggio.wav", 75.0, 24000)
    generate_meditation_drone("generated-audio/bg-meditation-drone.wav", 75.0, 24000)
    generate_ocean_waves("generated-audio/bg-ocean-waves.wav", 75.0, 24000)
    generate_minimal_piano("generated-audio/bg-minimal-piano.wav", 75.0, 24000)
    
    print("Successfully generated background audio library in 'generated-audio/'!")
