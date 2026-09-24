# TEXT-WEB

Website arsip teks dengan struktur folder bebas.

## Struktur

```text
TEXT-WEB/
├── index.html
├── style.css
├── script.js
├── update.py
├── update.bat
├── files.json
└── texts/
```

Kamu bebas membuat folder dan subfolder di dalam `texts/` sedalam apa pun.

Contoh:

```text
texts/
├── Kuliah/
│   └── Tauhid/
│       └── Muhadharah 1/
│           ├── 1.txt
│           └── 2.txt
└── Bahasa Arab/
    └── Nahwu/
        └── Jurumiyah/
            └── 1.txt
```

## Update

Setelah menambah/mengubah file `.txt`:

```bash
python update.py
```

Atau di Windows cukup klik:

```text
update.bat
```

Script akan membuat ulang `files.json`.

## Online

Upload/deploy seluruh folder project ke Netlify.

Jika memakai GitHub + Netlify, setelah update:

```bash
git add .
git commit -m "Update texts"
git push
```

Netlify akan melakukan deploy otomatis.

## Catatan

Tombol di website hanya untuk navigasi dan membaca teks. Python tidak dapat dijalankan langsung oleh website Netlify di laptop kamu. `update.bat` adalah tombol update lokal.
