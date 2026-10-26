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
  patente --review            ripassa le domande sbagliate
  patente --padronanza        i tuoi progressi, in totale e per categoria
  patente --stats             errori per categoria
  patente --reset             cancella gli errori (errori.json)
  patente --reset-padronanza  cancella i progressi (padronanza.json)
  patente --count             quante domande ci sono
  patente --controlla         controlla i file delle domande

Risposte:  y = VERO   n = FALSO   s = salta   q = esci
  (nell'esame non puoi saltare; nel --forzato non puoi uscire)

Quando sbagli: vedi la parola trabocchetto evidenziata e la spiegazione;
premi ? per la regola breve, invio per continuare (non nel --forzato).

In --libero, --categoria e --review escono più spesso le domande deboli:
quelle con poche risposte giuste e quelle delle categorie dove sbagli di più.
L'esame resta casuale, come quello vero.

Domande: listato ministeriale ufficiale A/B (cartella domande/).
Nuovo listato pubblicato?  python3 importa.py
"""

import json
import random
import re
import signal
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
    print(mastery_progress_line(mastery).replace(D, B + C, 1) + "\n")

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
    return label_c

# ---- lettura risposta -------------------------------------------------------
def read_answer(prompt, allowed, forzato=False):
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
        if ans in allowed:
            return ans
        print(f"       {D}risposte valide: {'/'.join(allowed)}{X}")

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

# ---- una domanda (usata da tutte le modalità) -------------------------------
def ask_question(q, header, allowed, all_errors, mastery, hint="", forzato=False):
    """Mostra una domanda, legge la risposta e salva il risultato.
    Ritorna "corretta", "errata", "saltata" oppure "esci"."""
    print(f"{B}[{header}]{X} {D}({q['categoria']}){X}")
    print(f"       {q['domanda']}")
    if q.get("immagine"):
        print(f"       {D}immagine: {image_link(q['immagine'])}{X}")
    ans = read_answer(f"       {Y}▸ {hint}{X} ", allowed, forzato=forzato)
    if ans == "q":
        return "esci"
    if ans == "s":
        print(f"       {D}saltata{X}\n")
        return "saltata"
    user_answer = (ans == "y")
    if user_answer == q["risposta"]:
        mark_correct(q["chiave"], mastery)
        print(f"       {G}✓ corretto{X}\n")
        return "corretta"
    label_c = record_error(q, user_answer, all_errors)
    print(f"       {R}✗ errato{X} {D}— risposta corretta: {label_c}{X}")
    # nel --forzato solo la spiegazione; altrimenti anche trabocchetti e regola breve
    if not forzato and q.get("trabocchetti"):
        print(f"       {D}trabocchetto:{X} {highlight(q['domanda'], q['trabocchetti'])}")
    if q["spiegazione"]:
        print(f"       {D}{q['spiegazione']}{X}")
    if not forzato and q.get("regola"):
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
        print(f"{B}{R}╚{bar}╝{X}\n")
    else:
        print(f"{B}{C}┌─ Esame Patente B simulato — {datetime.now().strftime('%d/%m/%Y %H:%M')}{X}")
        print(f"{D}│  {EXAM_QUESTIONS} domande casuali · promosso con max {EXAM_MAX_ERRORS} errori · tempo esame reale: {EXAM_TIME_LIMIT_MIN} min{X}")
        print(f"{D}│  y = VERO · n = FALSO{' · q = esci' if not forzato else ''}{X}")
        print(f"{D}└──────────────────────────────────────────────────────────────{X}\n")

    hint = "(y=VERO / n=FALSO)" if forzato else "(y/n, q=esci)"
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
    elapsed_min = (time.time() - start_ts) / 60
    passed = (answered == EXAM_QUESTIONS) and (wrong <= EXAM_MAX_ERRORS)
    print(f"{B}{C}┌─ Esito{X}")
    print(f"│  Risposte: {answered}/{EXAM_QUESTIONS}")
    print(f"│  {G}Corrette: {correct}{X}")
    print(f"│  {R}Errate:   {wrong}{X}  {D}(soglia promosso: ≤{EXAM_MAX_ERRORS}){X}")
    print(f"│  Tempo: {elapsed_min:.1f} min  {D}(limite esame reale: {EXAM_TIME_LIMIT_MIN} min){X}")
    if answered == EXAM_QUESTIONS:
        if passed:
            print(f"│  {G}{B}PROMOSSO{X}")
        else:
            print(f"│  {R}{B}✗ BOCCIATO{X}  {D}(troppi errori){X}")
    print(f"{D}└──────────────────────────────────────{X}")
    if wrong > 0:
        print(f"\n{D}errori salvati in {ERRORS_FILE.name} · totale archiviati: {len(all_errors)}{X}")
        print(f"{D}ripassali con:  python patente.py --review{X}")
    print(mastery_progress_line(mastery))
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
    print(f"{D}│  y=VERO · n=FALSO · s=salta · q=esci{X}")
    print(f"{D}└──────────────────────────────────────────────────────────────{X}\n")

    for i, q in enumerate(pool, 1):
        result = ask_question(q, f"{i:>3}/{total}", ["y", "n", "s", "q"], all_errors, mastery)
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
    print(mastery_progress_line(mastery))
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
    if not errors:
        print(f"{D}nessun errore da ripassare — bella!{X}")
        return
    # Usa la versione attuale della domanda (con immagine, spiegazione aggiornata...).
    # Se nel frattempo è stata tolta dalla banca, la ricostruisce da errori.json.
    by_key = {q["chiave"]: q for q in QUESTIONS}
    seen = set(); pool = []
    for e in errors:
        if e["chiave"] in seen:
            continue
        seen.add(e["chiave"])
        pool.append(by_key.get(e["chiave"]) or {
            "categoria": e["categoria"],
            "chiave": e["chiave"],
            "domanda": e["domanda"],
            "immagine": e.get("immagine", ""),
            "risposta": e["risposta_corretta"] == "VERO",
            "spiegazione": e.get("spiegazione", ""),
        })
    practice_session(weighted_order(pool), "Ripasso errori")

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
        print(f"{D}{ERRORS_FILE.name} cancellato.{X}")
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
        for field in ("spiegazione", "regola", "immagine"):
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
