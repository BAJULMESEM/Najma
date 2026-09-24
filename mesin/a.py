import subprocess
from pathlib import Path
import re

# =========================
# PENGATURAN
# =========================

DURASI_POTONGAN = 10 * 60  # 10 menit

EXTENSI_AUDIO = {
    ".mp3",
    ".m4a",
    ".aac",
    ".wav",
    ".flac",
    ".ogg",
    ".opus",
    ".wma",
    ".webm",
    ".amr",
    ".aiff",
    ".aif",
    ".alac",
}

BASE_FOLDER = Path(__file__).parent
OUTPUT_FOLDER = BASE_FOLDER / "audio_parts"

OUTPUT_FOLDER.mkdir(exist_ok=True)


# =========================
# BERSIHKAN NAMA
# =========================

def bersihkan_nama(nama):
    """
    Membuat nama folder/file aman untuk Windows.
    """

    # Hapus spasi di awal dan akhir
    nama = nama.strip()

    # Karakter yang tidak diperbolehkan Windows
    nama = re.sub(r'[<>:"/\\|?*]', '_', nama)

    # Hapus titik/spasi di akhir
    nama = nama.rstrip(" .")

    # Kalau kosong
    if not nama:
        nama = "audio"

    return nama


# =========================
# CARI AUDIO
# =========================

audio_files = [
    file
    for file in BASE_FOLDER.iterdir()
    if file.is_file()
    and file.suffix.lower() in EXTENSI_AUDIO
]


if not audio_files:
    print("Tidak ditemukan file audio.")
    input("Tekan Enter untuk keluar...")
    exit()


print("=" * 70)
print("PEMOTONG AUDIO OTOMATIS")
print("=" * 70)
print()

print(f"Ditemukan {len(audio_files)} file audio:")
print()

for file in audio_files:
    print(f"  {file.name}")

print()


# =========================
# PROSES
# =========================

for nomor, input_path in enumerate(audio_files, start=1):

    print("=" * 70)
    print(f"[{nomor}/{len(audio_files)}] {input_path.name}")
    print("=" * 70)

    # Nama asli tanpa ekstensi
    nama_asli = input_path.stem

    # Nama yang sudah dibersihkan
    nama_aman = bersihkan_nama(nama_asli)

    # Folder khusus audio
    audio_output_folder = OUTPUT_FOLDER / nama_aman
    audio_output_folder.mkdir(parents=True, exist_ok=True)

    # Nama output
    output_pattern = (
        audio_output_folder / f"{nama_aman}_%03d.m4a"
    )

    print(f"Folder output:")
    print(audio_output_folder)
    print()

    command = [
        "ffmpeg",
        "-i", str(input_path),

        # Ambil stream audio pertama
        "-map", "0:a:0",

        # Encode ke AAC
        "-c:a", "aac",
        "-b:a", "128k",

        # Potong setiap 10 menit
        "-f", "segment",
        "-segment_time", str(DURASI_POTONGAN),

        # Timestamp setiap bagian dimulai dari 0
        "-reset_timestamps", "1",

        # Output
        str(output_pattern),
    ]

    try:

        subprocess.run(command, check=True)

        print()
        print("✓ BERHASIL")
        print(f"  {input_path.name}")
        print()

    except subprocess.CalledProcessError:

        print()
        print("✗ GAGAL")
        print(f"  {input_path.name}")
        print()

    except FileNotFoundError:

        print()
        print("✗ FFmpeg tidak ditemukan!")
        print("Pastikan FFmpeg sudah masuk PATH.")
        print()

        input("Tekan Enter untuk keluar...")
        exit()


# =========================
# SELESAI
# =========================

print("=" * 70)
print("SEMUA AUDIO SELESAI")
print("=" * 70)
print()
print(f"Hasil berada di:")
print(OUTPUT_FOLDER)
print()

input("Tekan Enter untuk keluar...")