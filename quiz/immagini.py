"""Immagini delle domande: link, apertura con il visualizzatore di Windows,
disegno dentro al terminale (Sixel)."""

import os
import re
import subprocess
import sys
from pathlib import Path

from .config import IMAGES_DIR, QUESTIONS, D, X

def image_link(immagine):
    """URL così com'è, oppure percorso completo del file in domande/immagini/.
    Nel terminale di VS Code basta Ctrl+click per aprirlo."""
    if immagine.startswith(("http://", "https://")):
        return immagine
    return str(IMAGES_DIR / immagine)

def open_image(immagine):
    """Apre l'immagine con il visualizzatore di Windows (o il browser, se è un URL).
    Funziona anche nella finestra aperta dal Task Scheduler, dove il Ctrl+click no."""
    target = image_link(immagine)
    try:
        if not target.startswith(("http://", "https://")):
            # /home/... → \\wsl.localhost\Ubuntu\home\... (percorso che Windows capisce)
            target = subprocess.run(["wslpath", "-w", target], capture_output=True,
                                    text=True, check=True).stdout.strip()
        subprocess.Popen(["explorer.exe", target],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        print(f"       {D}non riesco ad aprirla: copia il percorso qui sopra{X}")

# ---- immagini dentro al terminale (Sixel) -----------------------------------
# I file .six si generano una volta con:  .venv/bin/python sixel.py
SIXEL_DIR = IMAGES_DIR / "sixel"
_sixel_ok = None

def terminal_has_sixel():
    """Il terminale sa disegnare immagini Sixel? Lo chiede al terminale stesso
    (risposta "DA1": il parametro 4 vuol dire Sixel). Si può forzare con la
    variabile d'ambiente PATENTE_SIXEL=1 (sì) oppure PATENTE_SIXEL=0 (no)."""
    global _sixel_ok
    if _sixel_ok is None:
        forced = os.environ.get("PATENTE_SIXEL")
        _sixel_ok = forced == "1" if forced in ("0", "1") else ask_terminal_sixel()
    return _sixel_ok

def ask_terminal_sixel():
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return False
    try:
        import select, termios, tty
    except ImportError:   # Windows senza WSL
        return False
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    reply = ""
    try:
        tty.setcbreak(fd)   # legge la risposta carattere per carattere, senza mostrarla
        sys.stdout.write("\x1b[c")
        sys.stdout.flush()
        while select.select([fd], [], [], 0.5)[0]:   # mezzo secondo al massimo
            ch = os.read(fd, 1).decode(errors="ignore")
            reply += ch
            if ch == "c":
                break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    m = re.search(r"\[\?([\d;]*)c", reply)
    return bool(m) and "4" in m.group(1).split(";")

def show_sixel(immagine):
    """Disegna l'immagine nel terminale. Ritorna False se non è possibile."""
    path = SIXEL_DIR / f"{Path(immagine).stem}.six"
    if immagine.startswith(("http://", "https://")) or not path.exists() or not terminal_has_sixel():
        return False
    # l'immagine parte dal cursore: 7 spazi come il rientro delle righe di testo
    sys.stdout.write("       " + path.read_text(encoding="ascii"))
    sys.stdout.write("\n")
    sys.stdout.flush()
    return True

def show_image(immagine):
    """Tasto i: nel terminale se si può, altrimenti apre il visualizzatore."""
    if not show_sixel(immagine):
        if os.environ.get("PATENTE_SIXEL") == "0":
            pass   # scelta dell'utente: sempre fuori, senza avvisi
        elif not (SIXEL_DIR / f"{Path(immagine).stem}.six").exists():
            print(f"       {D}immagini per il terminale non generate (sixel.py): la apro fuori{X}")
        elif not terminal_has_sixel():
            print(f"       {D}questo terminale non mostra immagini Sixel: la apro fuori{X}")
        open_image(immagine)

def sixel_check():
    """patente --sixel: dice se il terminale supporta Sixel e mostra un'immagine di prova."""
    n = len(list(SIXEL_DIR.glob("*.six"))) if SIXEL_DIR.exists() else 0
    print(f"file .six pronti: {n}" + ("" if n else "  →  generali con: .venv/bin/python sixel.py"))
    forced = os.environ.get("PATENTE_SIXEL")
    print(f"PATENTE_SIXEL: {forced if forced in ('0', '1') else 'non impostata (rilevamento automatico)'}")
    ok = terminal_has_sixel()
    print(f"il terminale supporta Sixel: {'sì' if ok else 'no'}")
    sample = next((q["immagine"] for q in QUESTIONS if q["immagine"]), None)
    if ok and sample and show_sixel(sample):
        print("se qui sopra vedi un'immagine, funziona")
    elif not ok:
        print("in VS Code: impostazione  \"terminal.integrated.enableImages\": true  e riapri il terminale")
