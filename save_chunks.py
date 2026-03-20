"""
save_chunks.py — Saves each cookie chunk to a separate file for easy copy-paste.
"""

import os

CHUNK_SIZE = 50_000
INPUT_FILE = "cookies_b64.txt"
OUTPUT_DIR = "chunks"

if not os.path.exists(INPUT_FILE):
    print(f"ERROR: {INPUT_FILE} not found.")
    raise SystemExit(1)

with open(INPUT_FILE, "r", encoding="utf-8") as f:
    data = f.read().strip()

os.makedirs(OUTPUT_DIR, exist_ok=True)

chunks = [data[i:i+CHUNK_SIZE] for i in range(0, len(data), CHUNK_SIZE)]

print(f"Total base64 length: {len(data):,} chars")
print(f"Number of chunks: {len(chunks)}")
print()

for idx, chunk in enumerate(chunks, start=1):
    filename = os.path.join(OUTPUT_DIR, f"chunk_{idx}.txt")
    with open(filename, "w", encoding="utf-8") as f:
        f.write(chunk)
    print(f"  Saved: {filename}  ({len(chunk):,} chars)")

print()
print("=" * 50)
print("Now open each chunk_N.txt file, select all (Ctrl+A),")
print("copy (Ctrl+C), and paste as the value for")
print("INSTAGRAM_COOKIES_B64_N in Koyeb.")
print()
print("REMEMBER: Delete the old INSTAGRAM_COOKIES_B64 variable!")
print("=" * 50)
