#!/usr/bin/env python3
"""
sixel.py — Converte le immagini delle domande in formato Sixel, per vederle dentro al terminale.

Si fa UNA volta sola (e dopo ogni importa.py). Il quiz poi legge i file .six già pronti,
quindi patente.py continua a non avere bisogno di librerie esterne.

Preparazione (una volta):
    python3 -m venv .venv
    .venv/bin/pip install pillow

Uso:
    .venv/bin/python sixel.py

Crea domande/immagini/sixel/<nome>.six per ogni immagine.
"""

from pathlib import Path

from PIL import Image

IMAGES_DIR = Path(__file__).resolve().parent / "domande" / "immagini"
SIXEL_DIR = IMAGES_DIR / "sixel"
MAX_SIDE = 300    # pixel: le immagini più grandi vengono rimpicciolite
COLORS = 256      # colori della palette: 256 è il massimo che i terminali (VS Code,
                  # Windows Terminal) accettano; Sixel non supporta i 16 milioni di colori


def encode_sixel(img):
    """Immagine Pillow → testo Sixel (sequenza di escape che il terminale disegna)."""
    img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    # FASTOCTREE conserva anche i colori presenti in poche aree (es. il verde scuro del
    # semaforo, che MEDIANCUT trasformava in marrone); senza dithering: segnali a colori pieni
    q = img.quantize(colors=COLORS, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
    width, height = q.size
    pixels = q.load()
    palette = q.getpalette()

    # P0;1;0q: il secondo parametro 1 = i pixel non disegnati restano trasparenti
    # (con 0 il terminale li riempie di nero: la striscia nera sotto l'immagine)
    out = ["\x1bP0;1;0q", f'"1;1;{width};{height}']
    used = sorted({pixels[x, y] for y in range(height) for x in range(width)})
    for c in used:   # definizione dei colori: #indice;2;rosso;verde;blu in percentuale
        r, g, b = palette[c * 3:c * 3 + 3]
        out.append(f"#{c};2;{r * 100 // 255};{g * 100 // 255};{b * 100 // 255}")

    # Sixel disegna a strisce alte 6 pixel: per ogni colore una riga di caratteri,
    # dove ogni carattere dice quali dei 6 pixel della colonna hanno quel colore.
    for top in range(0, height, 6):
        rows = {}
        for x in range(width):
            for dy in range(min(6, height - top)):
                c = pixels[x, top + dy]
                rows.setdefault(c, [0] * width)[x] |= 1 << dy
        lines = []
        for c, bits in rows.items():
            row = "".join(chr(63 + b) for b in bits).rstrip("?")   # "?" finali = niente da disegnare
            lines.append(f"#{c}" + run_length(row))
        out.append("$".join(lines) + "-")   # $ = torna a inizio riga, - = striscia successiva
    out.append("\x1b\\")
    return "".join(out)


def run_length(s):
    """Comprime i caratteri ripetuti: 'AAAAA' → '!5A'."""
    result, i = [], 0
    while i < len(s):
        j = i
        while j < len(s) and s[j] == s[i]:
            j += 1
        n = j - i
        result.append(f"!{n}{s[i]}" if n > 3 else s[i] * n)
        i = j
    return "".join(result)


def main():
    SIXEL_DIR.mkdir(exist_ok=True)
    images = sorted(p for p in IMAGES_DIR.iterdir() if p.suffix.lower() in (".jpg", ".png"))
    total = 0
    for i, path in enumerate(images, 1):
        with Image.open(path) as img:
            data = encode_sixel(img)
        (SIXEL_DIR / f"{path.stem}.six").write_text(data, encoding="ascii")
        total += len(data)
        if i % 50 == 0:
            print(f"  {i}/{len(images)}")
    print(f"fatto: {len(images)} immagini in {SIXEL_DIR}, {total / 1_000_000:.1f} MB")


if __name__ == "__main__":
    main()
