"""Impostazioni, percorsi dei file e colori del terminale. Li usano tutti gli altri file."""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent   # cartella del progetto (dove c'è patente.py)

ERRORS_FILE = HERE / "errori.json"

# Impostazioni modificabili in impostazioni.json; se manca un valore vale il default.
SETTINGS_FILE = HERE / "impostazioni.json"
DEFAULT_SETTINGS = {
    "domande_quiz": 30,                 # domande dell'esame (e massimo per --review)
    "errori_ammessi": 3,                # errori oltre i quali l'esame è bocciato
    "ripasso_giuste_di_fila": 2,        # risposte giuste di fila per uscire dal ripasso
    "ripasso_domande_per_errore": 10,   # --review: 1 errore ammesso ogni N domande
}
MIN_SETTINGS = {"domande_quiz": 1, "errori_ammessi": 0,
                "ripasso_giuste_di_fila": 1, "ripasso_domande_per_errore": 1}

def load_settings():
    settings = dict(DEFAULT_SETTINGS)
    if not SETTINGS_FILE.exists():
        return settings
    try:
        saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"{SETTINGS_FILE.name} non valido ({e}): uso i valori di default")
        return settings
    for name, value in saved.items():
        if name not in settings:
            print(f"{SETTINGS_FILE.name}: impostazione sconosciuta '{name}', la ignoro")
        elif not isinstance(value, int) or isinstance(value, bool) or value < MIN_SETTINGS[name]:
            print(f"{SETTINGS_FILE.name}: '{name}' deve essere un numero intero "
                  f">= {MIN_SETTINGS[name]}, uso {settings[name]}")
        else:
            settings[name] = value
    return settings

SETTINGS = load_settings()
EXAM_QUESTIONS = SETTINGS["domande_quiz"]
EXAM_MAX_ERRORS = SETTINGS["errori_ammessi"]
REVIEW_QUESTIONS_PER_ERROR = SETTINGS["ripasso_domande_per_errore"]

# Tempo: nell'esame vero 20 minuti per 30 domande = 40 secondi a domanda.
# Il limite segue domande_quiz; è solo indicativo, non viene forzato.
SECONDS_PER_QUESTION = 20 * 60 // 30
EXAM_TIME_LIMIT_S = EXAM_QUESTIONS * SECONDS_PER_QUESTION

# Padronanza: quante volte ogni domanda è stata risposta correttamente.
# Quando TUTTE le domande superano la soglia, scatta l'alert.
MASTERY_FILE = HERE / "padronanza.json"
MASTERY_THRESHOLD = 5

# Ripasso: risposte giuste di fila dopo l'ultimo errore, per ogni domanda sbagliata.
# Quando arrivano a REVIEW_DONE la domanda esce da --review (errori.json resta lo storico).
REVIEW_FILE = HERE / "ripasso.json"
REVIEW_DONE = SETTINGS["ripasso_giuste_di_fila"]

# Storico: un record per ogni quiz fatto (esame o pratica), per contare i quiz.
HISTORY_FILE = HERE / "storico.json"

QUESTIONS_DIR = HERE / "domande"
IMAGES_DIR = QUESTIONS_DIR / "immagini"

# ---- stile terminale --------------------------------------------------------
G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"
C = "\033[96m"; B = "\033[1m"; D = "\033[2m"; U = "\033[4m"; X = "\033[0m"

# ---- banca domande (vedi cartella domande/, un file per categoria) ----------
from domande import QUESTIONS, CATEGORIE   # gli altri file le prendono da qui
