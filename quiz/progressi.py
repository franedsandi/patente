"""I tuoi progressi, salvati nei file .json della cartella del progetto:
errori.json (errori), padronanza.json (risposte giuste), ripasso.json (--review),
storico.json (quiz fatti)."""

import json
from collections import Counter
from datetime import datetime

from .config import (
    ERRORS_FILE, MASTERY_FILE, MASTERY_THRESHOLD, REVIEW_FILE, REVIEW_DONE, HISTORY_FILE,
    QUESTIONS, CATEGORIE, G, R, Y, B, C, D, X,
)

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
    by_type = Counter(h["tipo"] for h in history)
    exams = [h for h in history if h["tipo"] == "esame"]
    finished = [h for h in exams if "promosso" in h]   # gli esami interrotti non hanno esito
    passed = sum(1 for h in finished if h["promosso"])
    promossi = Counter(h["tipo"] for h in history if h.get("promosso"))
    answers = sum(h["corrette"] + h["errate"] for h in history)
    return (f"{D}Quiz fatti: {len(history)} · esami {len(exams)} "
            f"(completati {len(finished)}, promossi {passed}) · "
            f"forzati {by_type['forzato']} (promossi {promossi['forzato']}) · "
            f"ripasso {by_type['ripasso']} (promossi {promossi['ripasso']}) · "
            f"pratica {by_type['pratica']} · "
            f"risposte {answers}{X}")

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

def reset_all():
    """--reset --all: cancella tutti i progressi (non le impostazioni), dopo conferma."""
    files = [f for f in (ERRORS_FILE, REVIEW_FILE, MASTERY_FILE, HISTORY_FILE) if f.exists()]
    if not files:
        print(f"{D}nessun progresso da cancellare.{X}")
        return
    print(f"{R}{B}Cancello tutti i tuoi progressi:{X} {', '.join(f.name for f in files)}")
    print(f"{D}errori, ripasso, padronanza e quiz fatti tornano a zero; non si può annullare.{X}")
    try:
        answer = input(f"{Y}▸ scrivi si per confermare:{X} ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = ""
    if answer not in ("si", "sì"):
        print(f"{D}annullato, non ho cancellato niente.{X}")
        return
    for f in files:
        f.unlink()
    print(f"{D}cancellati: {', '.join(f.name for f in files)}{X}")
