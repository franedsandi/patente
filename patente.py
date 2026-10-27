#!/usr/bin/env python3
"""
patente.py — Simulatore quiz patente B italiana da terminale.

Uso (patente = python3 patente.py):
  pq                          modalità libera (= patente --libero)
  patente                     esame simulato: 30 domande, max 3 errori
  patente --forzato           esame senza uscita: q e Ctrl+C disattivati
  patente --libero [N]        modalità libera: N domande (default: tutte)
  patente --categoria         elenca le categorie
  patente --categoria NOME [N]  solo una categoria (es. sorpasso, segnali)
  patente --review            ripassa le domande sbagliate, max 30 per volta
                              (escono dopo 2 risposte giuste di fila)
  patente --padronanza        i tuoi progressi, in totale e per categoria
  patente --stats             errori per categoria
  patente --reset             cancella gli errori (errori.json, ripasso.json)
  patente --reset-padronanza  cancella i progressi (padronanza.json)
  patente --count             quante domande ci sono
  patente --controlla         controlla i file delle domande
  patente --sixel             prova le immagini dentro al terminale

Quiz automatici (Windows Task Scheduler, orari in pianificazione.json):
  patente --pianifica         applica pianificazione.json
  patente --pianifica stato   mostra orari e prossima esecuzione
  patente --pianifica rimuovi toglie tutti i quiz automatici

Risposte:  VERO = y / v / t / s       FALSO = n / f
           p = salta   q = esci   - = spiegazione della domanda precedente
           immagini: nel terminale da sole se supporta Sixel
           i = mostra di nuovo (o apri fuori)   o = apri fuori
Aiuti prima di rispondere (non nel --forzato):
           r1 = parole chiave   r2 = trabocchetto evidenziato   r3 = riassunto
  (nell'esame non puoi saltare; nel --forzato non puoi uscire)

Quando sbagli: vedi la spiegazione; premi ? per la regola breve,
invio per continuare. Fuori dal --forzato vedi anche il trabocchetto.

In --libero, --categoria e --review escono più spesso le domande deboli:
quelle con poche risposte giuste e quelle delle categorie dove sbagli di più.
L'esame resta casuale, come quello vero.

Domande: listato ministeriale ufficiale A/B (cartella domande/).
Nuovo listato pubblicato?  python3 importa.py
"""

import json
import math
import os
import random
import re
import signal
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

ERRORS_FILE = Path(__file__).resolve().parent / "errori.json"
EXAM_QUESTIONS = 30         # come esame reale
EXAM_MAX_ERRORS = 3         # soglia promossi
EXAM_TIME_LIMIT_MIN = 20    # solo indicativo, non viene forzato

# Padronanza: quante volte ogni domanda è stata risposta correttamente.
# Quando TUTTE le domande superano la soglia, scatta l'alert.
MASTERY_FILE = Path(__file__).resolve().parent / "padronanza.json"
MASTERY_THRESHOLD = 5

# Ripasso: risposte giuste di fila dopo l'ultimo errore, per ogni domanda sbagliata.
# Quando arrivano a REVIEW_DONE la domanda esce da --review (errori.json resta lo storico).
REVIEW_FILE = Path(__file__).resolve().parent / "ripasso.json"
REVIEW_DONE = 2

# Storico: un record per ogni quiz fatto (esame o pratica), per contare i quiz.
HISTORY_FILE = Path(__file__).resolve().parent / "storico.json"

QUESTIONS_DIR = Path(__file__).resolve().parent / "domande"
IMAGES_DIR = QUESTIONS_DIR / "immagini"

# ---- stile terminale --------------------------------------------------------
G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"
C = "\033[96m"; B = "\033[1m"; D = "\033[2m"; U = "\033[4m"; X = "\033[0m"

# ---- banca domande (vedi cartella domande/, un file per categoria) ----------
from domande import QUESTIONS, CATEGORIE

# ---- utilità file -----------------------------------------------------------
def load_errors():
    if ERRORS_FILE.exists():
        try:
            return json.loads(ERRORS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
    return []

def save_errors(errors):
    ERRORS_FILE.write_text(
        json.dumps(errors, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

# ---- padronanza (mastery tracking) -----------------------------------------
def load_mastery():
    if MASTERY_FILE.exists():
        try:
            return json.loads(MASTERY_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}

def save_mastery(m):
    MASTERY_FILE.write_text(
        json.dumps(m, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

def mark_correct(key, mastery):
    """Incrementa il contatore di risposte corrette per questa domanda."""
    mastery[key] = mastery.get(key, 0) + 1
    save_mastery(mastery)

# ---- ripasso (domande sbagliate ancora da recuperare) -----------------------
def load_review():
    if REVIEW_FILE.exists():
        try:
            return json.loads(REVIEW_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}

def save_review(r):
    REVIEW_FILE.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")

def review_correct(key):
    """Risposta giusta: se la domanda era da ripassare conta +1.
    Ritorna True se proprio ora esce dal ripasso."""
    r = load_review()
    if key not in r or r[key] >= REVIEW_DONE:
        return False
    r[key] += 1
    save_review(r)
    return r[key] == REVIEW_DONE

def review_wrong(key):
    """Risposta sbagliata: la domanda (ri)entra nel ripasso e riparte da zero."""
    r = load_review()
    r[key] = 0
    save_review(r)

def mastery_summary(mastery):
    """(dominate, totale, viste almeno una volta) rispetto alla banca attuale."""
    counts = [mastery.get(q["chiave"], 0) for q in QUESTIONS]
    total = len(counts)
    dominated = sum(1 for n in counts if n >= MASTERY_THRESHOLD)
    seen = sum(1 for n in counts if n > 0)
    return dominated, total, seen

def percent(part, total):
    return f"{part / total * 100:.1f}%" if total else "0%"

def mastery_progress_line(mastery):
    dominated, total, seen = mastery_summary(mastery)
    return (f"{D}Progressi su {total}: {seen} giuste almeno una volta ({percent(seen, total)}) "
            f"· {dominated} dominate ({percent(dominated, total)}){X}")

# ---- storico dei quiz -------------------------------------------------------
def load_history():
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
    return []

def record_quiz(tipo, correct, wrong, passed=None):
    """Aggiunge un quiz allo storico; quelli senza nessuna risposta non contano."""
    if correct + wrong == 0:
        return
    history = load_history()
    entry = {"data": datetime.now().isoformat(timespec="seconds"), "tipo": tipo,
             "corrette": correct, "errate": wrong}
    if passed is not None:
        entry["promosso"] = passed
    history.append(entry)
    HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

def history_line():
    history = load_history()
    exams = [h for h in history if h["tipo"] == "esame"]
    finished = [h for h in exams if "promosso" in h]   # gli esami interrotti non hanno esito
    passed = sum(1 for h in finished if h["promosso"])
    answers = sum(h["corrette"] + h["errate"] for h in history)
    return (f"{D}Quiz fatti: {len(history)} · esami {len(exams)} "
            f"(completati {len(finished)}, promossi {passed}) · "
            f"pratica {len(history) - len(exams)} · risposte {answers}{X}")

def mastery_alert_if_complete(mastery):
    """Se tutte le domande hanno >=MASTERY_THRESHOLD corrette, stampa un messaggio."""
    dominated, total, _ = mastery_summary(mastery)
    if total == 0 or dominated < total:
        return False
    print(f"\n{B}{G}PADRONANZA COMPLETA: hai risposto bene ≥{MASTERY_THRESHOLD} volte "
          f"a tutte le {total} domande. Sei pronto per l'esame!{X}")
    return True

def reset_mastery():
    if MASTERY_FILE.exists():
        MASTERY_FILE.unlink()
        print(f"{D}{MASTERY_FILE.name} cancellato — padronanza azzerata.{X}")
    else:
        print(f"{D}nessun file di padronanza da cancellare.{X}")

def show_mastery():
    mastery = load_mastery()
    print(mastery_progress_line(mastery).replace(D, B + C, 1))
    print(history_line() + "\n")

    # quante domande hai risposto giuste almeno una volta, per categoria
    print(f"{B}Per categoria{X} {D}(giuste almeno una volta / totale){X}")
    for modulo in CATEGORIE:
        questions = [q for q in QUESTIONS if q["categoria"] == modulo.CATEGORIA]
        seen = sum(1 for q in questions if mastery.get(q["chiave"], 0) > 0)
        bar = "█" * round(seen / len(questions) * 20) if questions else ""
        print(f"  {modulo.CATEGORIA[:45]:<45} {seen:>4}/{len(questions):<4} {G}{bar:<20}{X} "
              f"{D}{percent(seen, len(questions))}{X}")
    print()
    mastery_alert_if_complete(mastery)

# ---- ordine "intelligente" delle domande ------------------------------------
def weighted_order(pool):
    """Mescola le domande, ma quelle più deboli tendono a uscire prima.

    Ogni domanda riceve un peso (più alto = esce prima, in media):
      - poche risposte corrette finora (padronanza.json)
      - sbagliata spesso in passato (errori.json)
      - categoria in cui sbagli di più (errori.json)
    """
    mastery = load_mastery()
    errors = load_errors()
    errors_by_question = Counter(e["chiave"] for e in errors)
    errors_by_category = Counter(e["categoria"] for e in errors)
    worst_category = max(errors_by_category.values(), default=0)

    def weight(q):
        # da 0 (già dominata) a MASTERY_THRESHOLD (mai risposta giusta)
        missing = MASTERY_THRESHOLD - min(mastery.get(q["chiave"], 0), MASTERY_THRESHOLD)
        # da 0 (nessun errore nella categoria) a 1 (categoria peggiore)
        category_bonus = errors_by_category[q["categoria"]] / worst_category if worst_category else 0
        return (1 + missing + errors_by_question[q["chiave"]]) * (1 + category_bonus)

    # Sorteggio pesato: ogni domanda pesca un numero casuale tra 0 e 1,
    # "spinto" verso 1 tanto più quanto il suo peso è alto. Poi si ordina.
    return sorted(pool, key=lambda q: random.random() ** (1 / weight(q)), reverse=True)

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

def record_error(q, user_answer, all_errors):
    label_c = "VERO" if q["risposta"] else "FALSO"
    rec = {
        "data": datetime.now().isoformat(timespec="seconds"),
        "categoria": q["categoria"],
        "chiave": q["chiave"],
        "domanda": q["domanda"],
        "immagine": q["immagine"],
        "risposta_corretta": label_c,
        "tua_risposta": "VERO" if user_answer else "FALSO",
        "spiegazione": q["spiegazione"],
    }
    all_errors.append(rec)
    save_errors(all_errors)
    review_wrong(q["chiave"])
    return label_c

# ---- lettura risposta -------------------------------------------------------
# Tasti equivalenti: tutti diventano "y" (VERO) o "n" (FALSO).
TRUE_KEYS = ("y", "v", "t", "s")    # yes, vero, true, sì
FALSE_KEYS = ("n", "f")             # no, falso/false
OTHER_KEYS = {"r1": "parole chiave", "r2": "trabocchetto", "r3": "riassunto",
              "p": "salta", "q": "esci", "i": "immagine", "o": "apri fuori",
              "-": "spiegazione della precedente"}

def read_answer(prompt, allowed, forzato=False):
    """Legge un tasto tra quelli in `allowed` ("y", "n", "p", "q", "i").
    Accetta anche v/t/s per VERO e f per FALSO."""
    while True:
        try:
            ans = input(prompt).strip().lower()
        except EOFError:
            return "q" if "q" in allowed else allowed[0]
        except KeyboardInterrupt:
            if forzato:
                print(f"\n       {D}devi completare il quiz prima di uscire{X}")
                continue
            return "q"
        if ans in TRUE_KEYS:
            ans = "y"
        elif ans in FALSE_KEYS:
            ans = "n"
        if ans in allowed:
            return ans
        others = " · ".join(f"{k} = {OTHER_KEYS[k]}" for k in allowed if k in OTHER_KEYS)
        print(f"       {D}risposte valide: y/v/t/s = VERO · n/f = FALSO"
              f"{' · ' + others if others else ''}{X}")

# ---- aiuti dopo una risposta sbagliata --------------------------------------
def highlight(text, words):
    """Evidenzia (giallo sottolineato) le parole trabocchetto dentro la domanda."""
    for word in words:
        text = re.sub(re.escape(word), lambda m: f"{U}{Y}{m.group(0)}{X}", text,
                      count=1, flags=re.IGNORECASE)
    return text

def show_rule_on_request(rule):
    """Dopo la spiegazione lunga: ? mostra la regola breve, invio va avanti."""
    try:
        ans = input(f"       {D}? = regola breve · invio = continua{X} ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    if ans == "?":
        print(f"       {B}{rule}{X}")

# ---- aiuti prima di rispondere (r1, r2, r3) ---------------------------------
# r1: parole che spesso decidono la risposta (assoluti, negazioni, obblighi, numeri)
KEY_WORDS = re.compile(
    r"\b(sempre|mai|solo|soltanto|solamente|unicamente|esclusivamente|"
    r"tutti|tutte|tutto|ogni|qualsiasi|qualunque|nessun|nessuno|nessuna|"
    r"non|né|anche|almeno|oltre|entro|superiore|inferiore|massim[oaie]|minim[oaie]|"
    r"obbligatori[oaie]?|obbligo|vietat[oaie]|divieto|consentit[oaie]|"
    r"permess[oaie]|ammess[oaie]|deve|devono|può|possono)\b"
    r"|\b\d+(?:[.,]\d+)?\s*(?:km/h|km|metri|m|cm|mm|anni|anno|mesi|giorni|ore|minuti|punti|kg|g/l|%)?",
    re.IGNORECASE,
)

def key_words_of(text):
    """Le parole chiave (non i numeri) presenti nel testo, in minuscolo."""
    return {m.group(1).lower() for m in KEY_WORDS.finditer(text) if m.group(1)}

_word_stats = None

def word_stats():
    """Conteggi su tutta la banca: per parola chiave e per categoria,
    quante domande la contengono e quante di queste sono VERE. Calcolati una volta sola."""
    global _word_stats
    if _word_stats is None:
        words, words_true = Counter(), Counter()
        cats, cats_true = Counter(), Counter()
        for q in QUESTIONS:
            cats[q["categoria"]] += 1
            cats_true[q["categoria"]] += q["risposta"]
            for w in key_words_of(q["domanda"]):
                words[w] += 1
                words_true[w] += q["risposta"]
        _word_stats = (words, words_true, cats, cats_true)
    return _word_stats

def true_probability(q):
    """Stima statistica (non una certezza!) che la domanda sia VERA.
    Parte dalla % di domande VERE della categoria e la corregge con ogni parola chiave
    (es. le domande con "sempre" sono VERE meno spesso della media).
    La domanda stessa non viene contata, altrimenti la stima "conoscerebbe" la risposta.
    Ritorna (probabilità, % VERE della categoria, [(parola, % VERE, numero domande)])."""
    words, words_true, cats, cats_true = word_stats()
    own = 1 if q["risposta"] else 0

    def rate(true, total):   # +1/+2: evita 0% e 100% quando ci sono poche domande
        return (true + 1) / (total + 2)

    def logit(p):
        return math.log(p / (1 - p))

    p_all = rate(sum(cats_true.values()) - own, len(QUESTIONS) - 1)
    p_cat = rate(cats_true[q["categoria"]] - own, cats[q["categoria"]] - 1)
    score = logit(p_cat)
    details = []
    for w in sorted(key_words_of(q["domanda"])):
        p_w = rate(words_true[w] - own, words[w] - 1)
        score += logit(p_w) - logit(p_all)   # quanto la parola sposta rispetto alla media
        details.append((w, p_w, words[w] - 1))
    p = 1 / (1 + math.exp(-score))
    return min(max(p, 0.03), 0.97), p_cat, details

def show_key_words(q):
    marked, count = KEY_WORDS.subn(lambda m: f"{U}{Y}{m.group(0)}{X}", q["domanda"])
    if count:
        print(f"       {D}parole chiave:{X} {marked}")
    else:
        print(f"       {D}nessuna parola chiave trovata: prova r2 o r3{X}")
    p, p_cat, details = true_probability(q)
    for w, p_w, n in details:
        print(f"       {D}  «{w}»: VERA nel {p_w:.0%} delle {n} domande che la contengono{X}")
    print(f"       {D}stima:{X} {B}{p:.0%} VERO · {1 - p:.0%} FALSO{X} "
          f"{D}(categoria: {p_cat:.0%} VERO · solo statistica, non una certezza){X}")

# r2: la domanda con le parole trabocchetto evidenziate (come dopo un errore)
def show_traps(q):
    if q.get("trabocchetti"):
        print(f"       {D}trabocchetto:{X} {highlight(q['domanda'], q['trabocchetti'])}")
    else:
        print(f"       {D}nessun trabocchetto segnalato per questa domanda: prova r1 o r3{X}")

# r3: riassunto scritto dall'AI, nel campo "riassunto" della domanda
def show_summary(q):
    if q.get("riassunto"):
        print(f"       {D}riassunto:{X} {B}{q['riassunto']}{X}")
    else:
        print(f"       {D}riassunto non disponibile per questa domanda{X}")

# -: spiegazione della domanda precedente (utile se l'hai indovinata senza esserne sicuro)
_previous = None

def show_previous(forzato=False):
    q = _previous
    if q is None:
        print(f"       {D}nessuna domanda precedente{X}")
        return
    answer = "VERO" if q["risposta"] else "FALSO"
    print(f"       {D}domanda precedente:{X} {q['domanda']}")
    print(f"       {D}risposta corretta:{X} {B}{answer}{X}")
    if not forzato and q.get("trabocchetti"):
        print(f"       {D}trabocchetto:{X} {highlight(q['domanda'], q['trabocchetti'])}")
    if q.get("spiegazione"):
        print(f"       {D}{q['spiegazione']}{X}")
    if q.get("regola"):
        print(f"       {D}regola:{X} {B}{q['regola']}{X}")

# ---- una domanda (usata da tutte le modalità) -------------------------------
def print_question(q, header):
    """Intestazione, testo e immagine (se il terminale supporta Sixel la disegna subito)."""
    print(f"{B}[{header}]{X} {D}({q['categoria']}){X}")
    print(f"       {q['domanda']}")
    if q.get("immagine"):
        print(f"       {D}immagine: {image_link(q['immagine'])}  (i = mostra · o = apri fuori){X}")
        show_sixel(q["immagine"])

def ask_question(q, header, allowed, all_errors, mastery, hint="", forzato=False):
    """Mostra una domanda, legge la risposta e salva il risultato.
    Ritorna "corretta", "errata", "saltata" oppure "esci"."""
    global _previous
    print_question(q, header)
    # "-" anche nel --forzato: riguarda la domanda già risposta, non aiuta con questa
    allowed = allowed + ["-"]
    if not forzato:   # nel --forzato niente aiuti prima di rispondere
        allowed = allowed + ["r1", "r2", "r3"]
    if q.get("immagine"):
        allowed = allowed + ["i", "o"]
    ans = read_answer(f"       {Y}▸ {hint}{X} ", allowed, forzato=forzato)
    while ans in ("-", "i", "o", "r1", "r2", "r3"):   # aiuti: si possono usare più volte, poi si risponde
        if ans == "-":
            show_previous(forzato)
            if _previous is not None:   # poi ripropone la domanda attuale, per non perderla
                print(f"\n       {D}── torna alla domanda ──{X}")
                print_question(q, header)
        elif ans == "i":
            show_image(q["immagine"])
        elif ans == "o":
            open_image(q["immagine"])
        elif ans == "r1":
            show_key_words(q)
        elif ans == "r2":
            show_traps(q)
        else:
            show_summary(q)
        ans = read_answer(f"       {Y}▸ {hint}{X} ", allowed, forzato=forzato)
    if ans == "q":
        return "esci"
    if ans == "p":
        print(f"       {D}saltata{X}\n")
        return "saltata"
    user_answer = (ans == "y")
    _previous = q   # dalla prossima domanda, "-" ne mostra la spiegazione
    if user_answer == q["risposta"]:
        mark_correct(q["chiave"], mastery)
        if review_correct(q["chiave"]):
            print(f"       {G}✓ corretto{X} {D}— giusta {REVIEW_DONE} volte di fila: tolta dal ripasso{X}\n")
        else:
            print(f"       {G}✓ corretto{X}\n")
        return "corretta"
    label_c = record_error(q, user_answer, all_errors)
    print(f"       {R}✗ errato{X} {D}— risposta corretta: {label_c}{X}")
    # il trabocchetto evidenziato non compare nel --forzato; la regola breve (?) sì
    if not forzato and q.get("trabocchetti"):
        print(f"       {D}trabocchetto:{X} {highlight(q['domanda'], q['trabocchetti'])}")
    if q["spiegazione"]:
        print(f"       {D}{q['spiegazione']}{X}")
    if q.get("regola"):
        show_rule_on_request(q["regola"])
    print()
    return "errata"

# ---- esame simulato (30 domande, esperienza reale) --------------------------
def exam_session(forzato=False):
    """30 domande casuali in stile esame reale. forzato=True disabilita q e Ctrl+C."""
    if forzato:
        try:
            signal.signal(signal.SIGINT, signal.SIG_IGN)
        except (ValueError, AttributeError):
            pass

    if len(QUESTIONS) < EXAM_QUESTIONS:
        print(f"{R}banca domande insufficiente ({len(QUESTIONS)} < {EXAM_QUESTIONS}){X}")
        return
    pool = random.sample(QUESTIONS, EXAM_QUESTIONS)

    allowed = ["y", "n"] if forzato else ["y", "n", "q"]
    all_errors = load_errors()
    mastery = load_mastery()
    correct = wrong = 0
    start_ts = time.time()

    bar = "═" * 62
    if forzato:
        print(f"{B}{R}╔{bar}╗{X}")
        print(f"{B}{R}║  QUIZ OBBLIGATORIO — ESAME PATENTE B SIMULATO                ║{X}")
        print(f"{B}{R}║  {EXAM_QUESTIONS} domande · promosso con massimo {EXAM_MAX_ERRORS} errori          ║{X}")
        print(f"{B}{R}║  Ctrl+C disabilitato · completa l'esame per poter continuare ║{X}")
        print(f"{B}{R}║  i = apri immagine                                           ║{X}")
        print(f"{B}{R}╚{bar}╝{X}\n")
    else:
        print(f"{B}{C}┌─ Esame Patente B simulato — {datetime.now().strftime('%d/%m/%Y %H:%M')}{X}")
        print(f"{D}│  {EXAM_QUESTIONS} domande casuali · promosso con max {EXAM_MAX_ERRORS} errori · tempo esame reale: {EXAM_TIME_LIMIT_MIN} min{X}")
        print(f"{D}│  y/v/t/s = VERO · n/f = FALSO · q = esci{X}")
        print(f"{D}│  aiuti: r1 = parole chiave · r2 = trabocchetto · r3 = riassunto · i = immagine{X}")
        print(f"{D}└──────────────────────────────────────────────────────────────{X}\n")

    hint = "(VERO: y/v/t/s · FALSO: n/f)" if forzato else "(VERO/FALSO, q=esci)"
    for i, q in enumerate(pool, 1):
        header = f"{i:>2}/{EXAM_QUESTIONS} · errori {wrong}/{EXAM_MAX_ERRORS}"
        result = ask_question(q, header, allowed, all_errors, mastery, hint, forzato)
        if result == "esci":
            print(f"\n{D}esame interrotto.{X}")
            break
        if result == "corretta":
            correct += 1
        else:
            wrong += 1

    answered = correct + wrong
    minutes, seconds = divmod(round(time.time() - start_ts), 60)
    passed = (answered == EXAM_QUESTIONS) and (wrong <= EXAM_MAX_ERRORS)
    print(f"{B}{C}┌─ Esito{X}")
    print(f"│  Risposte: {answered}/{EXAM_QUESTIONS}")
    print(f"│  {G}Corrette: {correct}{X}")
    print(f"│  {R}Errate:   {wrong}{X}  {D}(soglia promosso: ≤{EXAM_MAX_ERRORS}){X}")
    print(f"│  Tempo: {minutes} min {seconds:02d} s  {D}(limite esame reale: {EXAM_TIME_LIMIT_MIN} min){X}")
    if answered == EXAM_QUESTIONS:
        if passed:
            print(f"│  {G}{B}PROMOSSO{X}")
        else:
            print(f"│  {R}{B}✗ BOCCIATO{X}  {D}(troppi errori){X}")
    print(f"{D}└──────────────────────────────────────{X}")
    if wrong > 0:
        print(f"\n{D}errori salvati in {ERRORS_FILE.name} · totale archiviati: {len(all_errors)}{X}")
        print(f"{D}ripassali con:  python patente.py --review{X}")
    record_quiz("esame", correct, wrong, passed if answered == EXAM_QUESTIONS else None)
    print(mastery_progress_line(mastery))
    print(history_line())
    mastery_alert_if_complete(mastery)
    if forzato:
        print(f"\n{D}la finestra si chiuderà tra 8 secondi. Buon lavoro.{X}")
        try:
            time.sleep(8)
        except KeyboardInterrupt:
            pass

# ---- sessione di pratica (usata da --libero e --review) ---------------------
def practice_session(pool, title):
    """Fa le domande di `pool` nell'ordine dato; puoi saltare (s) o uscire (q)."""
    total = len(pool)
    correct = wrong = 0
    all_errors = load_errors()
    mastery = load_mastery()

    print(f"{B}{C}┌─ {title} — {total} domande{X}")
    print(f"{D}│  y/v/t/s = VERO · n/f = FALSO · p = salta · q = esci{X}")
    print(f"{D}│  aiuti: r1 = parole chiave · r2 = trabocchetto · r3 = riassunto · i = immagine{X}")
    print(f"{D}└──────────────────────────────────────────────────────────────{X}\n")

    for i, q in enumerate(pool, 1):
        result = ask_question(q, f"{i:>3}/{total}", ["y", "n", "p", "q"], all_errors, mastery)
        if result == "esci":
            print(f"\n{D}sessione interrotta.{X}")
            break
        if result == "corretta":
            correct += 1
        elif result == "errata":
            wrong += 1

    answered = correct + wrong
    print(f"{B}{C}┌─ Risultato{X}")
    print(f"│  Risposte: {answered}")
    print(f"│  {G}Corrette: {correct}{X}")
    print(f"│  {R}Errate:   {wrong}{X}")
    if answered:
        print(f"│  Precisione: {correct/answered*100:.1f}%")
    print(f"{D}└──────────────────────────────────────{X}")
    record_quiz("pratica", correct, wrong)
    print(mastery_progress_line(mastery))
    print(history_line())
    mastery_alert_if_complete(mastery)

# ---- modalità libera (sessione lunga, puoi uscire quando vuoi) --------------
def free_quiz(n=None):
    pool = weighted_order(QUESTIONS)
    if n is not None:
        pool = pool[:n]
    practice_session(pool, "Modalità libera")

# ---- quiz per categoria -----------------------------------------------------
def list_categories():
    errors_by_category = Counter(e["categoria"] for e in load_errors())
    print(f"{B}{C}Categorie{X}  {D}(usa: python3 patente.py --categoria NOME){X}\n")
    for modulo in CATEGORIE:
        nome_file = modulo.__name__.split(".")[-1]
        n_errors = errors_by_category[modulo.CATEGORIA]
        errors_note = f"  {R}{n_errors} {'errore' if n_errors == 1 else 'errori'}{X}" if n_errors else ""
        print(f"  {nome_file:<50} {len(modulo.QUESTIONS):>4} domande{errors_note}")

def category_quiz(search, n=None):
    """Quiz sulle categorie il cui nome contiene `search`.
    Es. "velocita" → solo Velocità; "segnali" → tutti i tipi di segnali."""
    search = search.lower()
    pool = [q for q in QUESTIONS
            if search in q["file"] or search in q["categoria"].lower()]
    if not pool:
        print(f"{R}nessuna categoria contiene '{search}'{X}\n")
        list_categories()
        return
    names = sorted({q["categoria"] for q in pool})
    pool = weighted_order(pool)
    if n is not None:
        pool = pool[:n]
    practice_session(pool, ", ".join(names))

# ---- ripasso errori ---------------------------------------------------------
def review():
    errors = load_errors()
    progress = load_review()
    # Escono dal ripasso le domande già risposte giuste REVIEW_DONE volte di fila dopo l'errore.
    # Gli errori più vecchi di ripasso.json (senza contatore) contano come 0.
    pending = [e for e in errors if progress.get(e["chiave"], 0) < REVIEW_DONE]
    if not pending:
        print(f"{D}nessun errore da ripassare — bella!{X}")
        return
    # Usa la versione attuale della domanda (con immagine, spiegazione aggiornata...).
    # Se nel frattempo è stata tolta dalla banca, la ricostruisce da errori.json.
    by_key = {q["chiave"]: q for q in QUESTIONS}
    seen = set(); pool = []
    for e in pending:
        if e["chiave"] in seen:
            continue
        seen.add(e["chiave"])
        progress.setdefault(e["chiave"], 0)   # così review_correct le riconosce
        pool.append(by_key.get(e["chiave"]) or {
            "categoria": e["categoria"],
            "chiave": e["chiave"],
            "domanda": e["domanda"],
            "immagine": e.get("immagine", ""),
            "risposta": e["risposta_corretta"] == "VERO",
            "spiegazione": e.get("spiegazione", ""),
        })
    save_review(progress)
    # al massimo EXAM_QUESTIONS per volta, come un esame: prima le più sbagliate
    title = "Ripasso errori"
    if len(pool) > EXAM_QUESTIONS:
        title += f" (in tutto da ripassare: {len(pool)})"
    practice_session(weighted_order(pool)[:EXAM_QUESTIONS], title)

def show_stats():
    errors = load_errors()
    if not errors:
        print(f"{D}nessun errore archiviato.{X}")
        return
    by_cat = {}
    for e in errors:
        by_cat[e["categoria"]] = by_cat.get(e["categoria"], 0) + 1
    print(f"{B}{C}Errori per categoria ({len(errors)} totali){X}")
    for cat, n in sorted(by_cat.items(), key=lambda x: -x[1]):
        bar = "█" * min(n, 40)
        print(f"  {cat[:45]:<45} {n:>3}  {D}{bar}{X}")

def reset_errors():
    if ERRORS_FILE.exists():
        ERRORS_FILE.unlink()
        REVIEW_FILE.unlink(missing_ok=True)
        print(f"{D}{ERRORS_FILE.name} e {REVIEW_FILE.name} cancellati.{X}")
    else:
        print(f"{D}nessun archivio da cancellare.{X}")

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
    script = Path(__file__).resolve().parent / "setup_quiz_scheduler.ps1"
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

# ---- entrypoint -------------------------------------------------------------
def main():
    args = sys.argv[1:]
    if not args:
        exam_session(forzato=False)
        return
    cmd = args[0]
    if cmd == "--forzato":
        exam_session(forzato=True)
    elif cmd == "--libero":
        n = None
        if len(args) > 1:
            try: n = int(args[1])
            except ValueError: pass
        free_quiz(n)
    elif cmd == "--categoria":
        if len(args) < 2:
            list_categories()
        else:
            n = None
            if len(args) > 2:
                try: n = int(args[2])
                except ValueError: pass
            category_quiz(args[1], n)
    elif cmd == "--pianifica":
        schedule(args[1] if len(args) > 1 else "")
    elif cmd == "--sixel":
        sixel_check()
    elif cmd == "--controlla":
        if not check_bank():
            sys.exit(1)
    elif cmd == "--review":
        review()
    elif cmd == "--stats":
        show_stats()
    elif cmd == "--reset":
        reset_errors()
    elif cmd == "--padronanza":
        show_mastery()
    elif cmd == "--reset-padronanza":
        reset_mastery()
    elif cmd == "--count":
        print(f"{len(QUESTIONS)} domande in banca")
    elif cmd in ("-h", "--help"):
        print(__doc__)
    else:
        print(f"comando sconosciuto: {cmd}\n")
        print(__doc__)

if __name__ == "__main__":
    main()
