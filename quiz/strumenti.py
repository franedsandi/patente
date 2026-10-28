"""Comandi di servizio: --controlla (file delle domande) e --pianifica (quiz automatici)."""

import subprocess
from collections import Counter

from .config import HERE, QUESTIONS_DIR, IMAGES_DIR, QUESTIONS, CATEGORIE, G, R, D, X

# ---- controllo banca domande ------------------------------------------------
def check_bank():
    """Cerca errori comuni nei file delle domande. Ritorna True se è tutto ok."""
    problems = []

    # file nella cartella che non sono stati aggiunti a CATEGORIE in __init__.py
    registered = {m.__name__.split(".")[-1] for m in CATEGORIE}
    for f in sorted(QUESTIONS_DIR.glob("*.py")):
        if f.stem != "__init__" and f.stem not in registered:
            problems.append(f"domande/{f.name}: non è nella lista CATEGORIE di domande/__init__.py")

    # stesso nome di categoria in due file diversi
    for name, count in Counter(m.CATEGORIA for m in CATEGORIE).items():
        if count > 1:
            problems.append(f"la categoria '{name}' è usata in {count} file")

    seen = {}
    for q in QUESTIONS:
        where = f"domande/{q['file']}.py"
        text = q["domanda"]
        short = text if len(text) < 60 else text[:57] + "..."
        if not isinstance(text, str) or not text.strip():
            problems.append(f"{where}: domanda vuota")
        if not isinstance(q["risposta"], bool):
            problems.append(f"{where}: risposta deve essere True o False → {short}")
        for field in ("riassunto", "spiegazione", "regola", "immagine"):
            if not isinstance(q[field], str):
                problems.append(f"{where}: \"{field}\" deve essere un testo tra virgolette → {short}")
        if not isinstance(q["trabocchetti"], list):
            problems.append(f"{where}: \"trabocchetti\" deve essere una lista, es. [\"sempre\"] → {short}")
        # stesso testo va bene solo se l'immagine è diversa
        if q["chiave"] in seen:
            problems.append(f"{where}: domanda duplicata (anche in domande/{seen[q['chiave']]}.py) → {short}")
        seen[q["chiave"]] = q["file"]
        image = q["immagine"]
        if image and not image.startswith(("http://", "https://")) and not (IMAGES_DIR / image).exists():
            problems.append(f"{where}: immagine non trovata in domande/immagini/: {image}")

    if not problems:
        print(f"{G}✓ banca domande ok{X} {D}— {len(QUESTIONS)} domande, {len(CATEGORIE)} categorie{X}")
        return True
    print(f"{R}{len(problems)} problemi trovati:{X}")
    for p in problems:
        print(f"  {R}•{X} {p}")
    return False

# ---- quiz automatici (Windows Task Scheduler) -------------------------------
def schedule(action):
    """Lancia setup_quiz_scheduler.ps1 su Windows. Gli orari sono in pianificazione.json."""
    script = HERE / "setup_quiz_scheduler.ps1"
    flags = {"": [], "stato": ["-Status"], "rimuovi": ["-Uninstall"]}
    if action not in flags:
        print("uso: patente --pianifica [stato|rimuovi]")
        return
    if action == "":
        print(f"{D}applico pianificazione.json ...{X}", flush=True)
    try:
        windows_path = subprocess.run(["wslpath", "-w", str(script)], capture_output=True,
                                      text=True, check=True).stdout.strip()
        subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-File", windows_path,
                        "-QuizDir", str(script.parent)] + flags[action])
    except (OSError, subprocess.CalledProcessError):
        print(f"{R}non riesco ad avviare powershell.exe: funziona solo da WSL su Windows{X}")
