"""
Create a simple notification sound file (beep)
"""
import struct
import math
import wave
import os

# Navigate to project root
script_dir = os.path.dirname(__file__)
project_root = os.path.dirname(script_dir)
sound_path = os.path.join(project_root, 'core', 'static', 'core', 'sounds', 'notification.mp3')

# Audio parameters
rate = 44100  # Sample rate (Hz)
duration = 0.3  # Duration in seconds
frequency = 800  # Frequency of the beep (Hz)
samples = int(rate * duration)

# Create WAV file (note: we'll save as .mp3 extension but it's actually WAV format)
# For a true MP3, you'd need additional libraries like pydub
wav_file = wave.open(sound_path, 'w')
wav_file.setnchannels(1)  # Mono
wav_file.setsampwidth(2)  # 16-bit
wav_file.setframerate(rate)

# Generate a simple sine wave beep
for i in range(samples):
    value = int(32767 * 0.3 * math.sin(2 * math.pi * frequency * i / rate))
    wav_file.writeframes(struct.pack('h', value))

wav_file.close()

print(f"✅ Created notification sound file at: {sound_path}")
print("   Note: This is a WAV file with .mp3 extension. For production, consider using a real MP3.")
