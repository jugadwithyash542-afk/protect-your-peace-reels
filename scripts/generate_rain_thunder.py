import wave
import math
import struct
import random

def generate_rain_thunder(filename="generated-audio/test-ambient.wav", duration=70.0, sample_rate=24000):
    print(f"Synthesizing a realistic {duration}-second Rain & Thunder soundscape to {filename} at {sample_rate}Hz...")
    
    wav_file = wave.open(filename, 'w')
    wav_file.setnchannels(1)
    wav_file.setsampwidth(2)
    wav_file.setframerate(sample_rate)
    
    # Define thunder triggers: (start_time, duration, volume_multiplier)
    # This places thunder rumbles in specific portions of the audio
    thunders = [
        (10.0, 8.0, 0.55),  # Thunder at 10s (medium rumble)
        (32.0, 11.0, 0.85), # Big thunder at 32s (loud rumble + rolling cracks)
        (54.0, 9.0, 0.40)   # Distant thunder at 54s (low rumble)
    ]
    
    # Filter coefficients (exponential smoothing) for sound design
    # alpha_rain controls rain tone: lower means deeper/softer, higher means hissier/crisper
    alpha_rain = 0.08
    
    # alpha_thunder controls thunder bass: extremely small to filter out everything except deep rumbles (below 100Hz)
    alpha_thunder = 0.004
    
    # alpha_crack controls the sharp lightning cracks (mid-frequency rumble, around 300Hz)
    alpha_crack = 0.02
    
    # State variables for low-pass filters
    smooth_rain = 0.0
    smooth_thunder = 0.0
    smooth_crack = 0.0
    
    # List to track active raindrop clicks (to make rain sound like individual drops hitting surfaces)
    active_drops = []
    
    total_frames = int(duration * sample_rate)
    chunk_size = 1024
    frames_written = 0
    
    # Generate audio in chunks
    while frames_written < total_frames:
        chunk_frames = min(chunk_size, total_frames - frames_written)
        packed_data = bytearray()
        
        for i in range(chunk_frames):
            t = float(frames_written + i) / sample_rate
            
            # 1. GENERATE WHITE NOISE BASE
            noise_val = random.uniform(-1.0, 1.0)
            
            # 2. GENERATE CONSTANT RAIN WASH (Soft low-pass filtered noise)
            smooth_rain = alpha_rain * noise_val + (1.0 - alpha_rain) * smooth_rain
            rain_sample = smooth_rain * 0.35
            
            # Add occasional crisp raindrop splatters
            # Small chance to spawn a drop click at each frame
            if random.random() < 0.0006:
                # Store (start_time, frequency, peak_vol)
                active_drops.append([t, random.uniform(800.0, 1800.0), random.uniform(0.02, 0.07)])
            
            # Synthesize active raindrops
            drop_sample = 0.0
            still_active_drops = []
            for drop in active_drops:
                drop_t = t - drop[0]
                if drop_t < 0.015:  # raindrop lasts 15 milliseconds
                    # Fast decaying sine wave
                    env = math.exp(-drop_t * 400.0)
                    drop_sample += drop[2] * env * math.sin(2.0 * math.pi * drop[1] * drop_t)
                    still_active_drops.append(drop)
            active_drops = still_active_drops
            
            # Combine continuous rain wash and drop splatters
            total_rain = rain_sample + drop_sample
            
            # 3. GENERATE THUNDER RUMBLES (Low-pass filtered rumbling noise)
            thunder_sample = 0.0
            
            # Apply heavy low-pass to get the sub-bass rumble
            smooth_thunder = alpha_thunder * noise_val + (1.0 - alpha_thunder) * smooth_thunder
            # Apply slightly wider low-pass for the crackle/clatter of lightning
            smooth_crack = alpha_crack * noise_val + (1.0 - alpha_crack) * smooth_crack
            
            for start, dur, vol_mult in thunders:
                if start <= t < start + dur:
                    thunder_t = t - start
                    
                    # Envelope: Quick rising strike, then slow rumbling decay
                    if thunder_t < 0.5:
                        env = thunder_t / 0.5
                    else:
                        env = math.exp(-(thunder_t - 0.5) / 2.2)
                        
                    # Lightning Crack (sharp high/mid strike at start of thunder)
                    crack_env = math.exp(-thunder_t * 2.5) if thunder_t > 0.05 else (thunder_t / 0.05)
                    crack_sample = smooth_crack * crack_env * 0.45
                    
                    # Rolling/Fluttering effect of thunder (caused by sound waves bouncing off clouds/hills)
                    # We simulate this using amplitude modulation via multi-frequency LFOs
                    roll_lfo = 0.6 + 0.4 * math.sin(2.0 * math.pi * 9.0 * t) * math.sin(2.0 * math.pi * 0.7 * t)
                    rumble_sample = smooth_thunder * env * 2.2 * roll_lfo
                    
                    thunder_sample += (rumble_sample + crack_sample) * vol_mult
            
            # 4. MIX RAIN & THUNDER
            mixed_ambient = total_rain * 0.7 + thunder_sample * 0.7
            
            # Keep within stereo limits
            mixed_ambient = max(-1.0, min(1.0, mixed_ambient))
            
            # Global fade-in and fade-out to prevent clicks
            global_fade = 2.0
            if t < global_fade:
                mixed_ambient *= (t / global_fade)
            elif t > (duration - global_fade):
                mixed_ambient *= ((duration - t) / global_fade)
                
            # Scale to 16-bit signed int
            int_val = int(mixed_ambient * 32767.0)
            packed_data.extend(struct.pack('<h', max(-32768, min(32767, int_val))))
            
        wav_file.writeframes(packed_data)
        frames_written += chunk_frames
        
    wav_file.close()
    print("Done! Rain and Thunder soundscape synthesized.")

if __name__ == "__main__":
    generate_rain_thunder()
