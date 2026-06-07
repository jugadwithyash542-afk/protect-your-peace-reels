import wave
import struct
import sys
import os

def mix_wavs(voice_path, bg_path, output_path, voice_volume=1.0, bg_volume=0.15):
    if not os.path.exists(voice_path):
        print(f"Error: Voice file {voice_path} does not exist!")
        return False
    if not os.path.exists(bg_path):
        print(f"Error: Background music file {bg_path} does not exist!")
        return False
        
    print(f"Mixing:\n - Voiceover: {voice_path} (volume: {voice_volume})\n - Background: {bg_path} (volume: {bg_volume})\n - Target Output: {output_path}")
    
    voice_wav = wave.open(voice_path, 'rb')
    bg_wav = wave.open(bg_path, 'rb')
    
    # Check properties
    if voice_wav.getnchannels() != bg_wav.getnchannels():
        print("Warning: Channels do not match! Simple mono mix will assume source channels.")
    if voice_wav.getframerate() != bg_wav.getframerate():
        print(f"Warning: Sample rates do not match! Voice: {voice_wav.getframerate()}Hz, BG: {bg_wav.getframerate()}Hz. Please make sure they match.")
        
    out_wav = wave.open(output_path, 'wb')
    out_wav.setparams(voice_wav.getparams())
    
    total_frames = voice_wav.getnframes()
    chunk_size = 2048
    frames_written = 0
    
    fmt = '<h'
    sample_bytes = 2 # 16-bit PCM
    
    while frames_written < total_frames:
        to_read = min(chunk_size, total_frames - frames_written)
        
        voice_data = voice_wav.readframes(to_read)
        bg_data = bg_wav.readframes(to_read)
        
        # Pad background track if it's shorter than the voiceover
        if len(bg_data) < len(voice_data):
            bg_data = bg_data + b'\x00' * (len(voice_data) - len(bg_data))
            
        packed_out = bytearray()
        
        for offset in range(0, len(voice_data), sample_bytes):
            voice_val = struct.unpack_from(fmt, voice_data, offset)[0]
            bg_val = struct.unpack_from(fmt, bg_data, offset)[0]
            
            # Mix with volume settings
            mixed_val = int(voice_val * voice_volume + bg_val * bg_volume)
            
            # Clamp limits for 16-bit signed int
            mixed_val = max(-32768, min(32767, mixed_val))
            
            packed_out.extend(struct.pack(fmt, mixed_val))
            
        out_wav.writeframes(packed_out)
        frames_written += to_read
        
    voice_wav.close()
    bg_wav.close()
    out_wav.close()
    print(f"Successfully mixed! Saved output to {output_path}")
    return True

if __name__ == "__main__":
    # If running with command line arguments
    if len(sys.argv) >= 4:
        voice = sys.argv[1]
        bg = sys.argv[2]
        out = sys.argv[3]
        bg_vol = float(sys.argv[4]) if len(sys.argv) >= 5 else 0.15
        mix_wavs(voice, bg, out, bg_volume=bg_vol)
    else:
        # Default fallback to testing
        mix_wavs(
            "generated-audio/marketing-voiceover-the-sorry-reflex.wav",
            "generated-audio/bg-lofi-arpeggio.wav",
            "generated-audio/mixed-voiceover-test.wav",
            bg_volume=0.15
        )
