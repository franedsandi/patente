"""Le modalità di quiz: esame (anche --forzato), libera, per categoria, ripasso errori."""

import random
import signal
import time
from collections import Counter
from datetime import datetime

from .aiuti import ask_last_explanation
from .config import (
    EXAM_QUESTIONS, EXAM_MAX_ERRORS, EXAM_TIME_LIMIT_S, SECONDS_PER_QUESTION,
    REVIEW_QUESTIONS_PER_ERROR,
    MASTERY_THRESHOLD, REVIEW_DONE, ERRORS_FILE, QUESTIONS, CATEGORIE, G, R, B, C, D, X,
)
from .domanda import ask_question
from .progressi import (
    load_errors, load_mastery, load_review, save_review, record_quiz,
    mastery_progress_line, history_line, mastery_alert_if_complete,
)

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

def min_sec(seconds, always_seconds=False):
    """400 → "6 min 40 s", 1200 → "20 min" (o "20 min 00 s" con always_seconds)."""
    minutes, seconds = divmod(round(seconds), 60)
    if seconds or always_seconds:
        return f"{minutes} min {seconds:02d} s"
    return f"{minutes} min"

# ---- esame simulato (30 domande, esperienza reale) --------------------------
def exam_session(forzato=False):
    """EXAM_QUESTIONS domande casuali in stile esame reale. forzato=True disabilita q e Ctrl+C."""
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
        rules = f"{EXAM_QUESTIONS} domande · promosso con massimo {EXAM_MAX_ERRORS} errori"
        print(f"{B}{R}║  {rules:<60}║{X}")   # :<60 = riempie di spazi fino al bordo
        print(f"{B}{R}║  Ctrl+C disabilitato · completa l'esame per poter continuare ║{X}")
        print(f"{B}{R}║  i = apri immagine                                           ║{X}")
        print(f"{B}{R}╚{bar}╝{X}\n")
    else:
        print(f"{B}{C}┌─ Esame Patente B simulato — {datetime.now().strftime('%d/%m/%Y %H:%M')}{X}")
        print(f"{D}│  {EXAM_QUESTIONS} domande casuali · promosso con max {EXAM_MAX_ERRORS} errori · tempo: {min_sec(EXAM_TIME_LIMIT_S)}{X}")
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
    elapsed = time.time() - start_ts
    passed = (answered == EXAM_QUESTIONS) and (wrong <= EXAM_MAX_ERRORS)
    print(f"{B}{C}┌─ Esito{X}")
    print(f"│  Risposte: {answered}/{EXAM_QUESTIONS}")
    print(f"│  {G}Corrette: {correct}{X}")
    print(f"│  {R}Errate:   {wrong}{X}  {D}(soglia promosso: ≤{EXAM_MAX_ERRORS}){X}")
    print(f"│  Tempo: {min_sec(elapsed, always_seconds=True)}  {D}(limite: {min_sec(EXAM_TIME_LIMIT_S)}, "
          f"{SECONDS_PER_QUESTION} s a domanda come nell'esame vero){X}")
    if answered == EXAM_QUESTIONS:
        if passed:
            print(f"│  {G}{B}PROMOSSO{X}")
        else:
            print(f"│  {R}{B}✗ BOCCIATO{X}  {D}(troppi errori){X}")
    print(f"{D}└──────────────────────────────────────{X}")
    if wrong > 0:
        print(f"\n{D}errori salvati in {ERRORS_FILE.name} · totale archiviati: {len(all_errors)}{X}")
        print(f"{D}ripassali con:  python patente.py --review{X}")
    record_quiz("forzato" if forzato else "esame", correct, wrong,
                passed if answered == EXAM_QUESTIONS else None)
    print(mastery_progress_line(mastery))
    print(history_line())
    mastery_alert_if_complete(mastery)
    try:
        ask_last_explanation(forzato)
    except KeyboardInterrupt:
        pass

# ---- sessione di pratica (usata da --libero e --review) ---------------------
def practice_session(pool, title, tipo="pratica"):
    """Fa le domande di `pool` nell'ordine dato; puoi saltare (s) o uscire (q)."""
    total = len(pool)
    correct = wrong = 0
    all_errors = load_errors()
    mastery = load_mastery()

    print(f"{B}{C}┌─ {title} — {total} domande{X}")
    print(f"{D}│  y/v/t/s = VERO · n/f = FALSO · p = salta · q = esci{X}")
    print(f"{D}│  aiuti: r1 = parole chiave · r2 = trabocchetto · r3 = riassunto · i = immagine{X}")
    print(f"{D}└──────────────────────────────────────────────────────────────{X}\n")

    # ripasso: come un esame, con 1 errore ammesso ogni REVIEW_QUESTIONS_PER_ERROR domande,
    # arrotondato per difetto (con 10: 30 → 3, 29 → 2, 9 → 0)
    max_errors = total // REVIEW_QUESTIONS_PER_ERROR

    for i, q in enumerate(pool, 1):
        header = f"{i:>3}/{total}"
        if tipo == "ripasso":
            header += f" · errori {wrong}/{max_errors}"
        result = ask_question(q, header, ["y", "n", "p", "q"], all_errors, mastery)
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
    passed = None
    if tipo == "ripasso":
        print(f"│  {R}Errate:   {wrong}{X}  {D}(soglia promosso: ≤{max_errors}){X}")
    else:
        print(f"│  {R}Errate:   {wrong}{X}")
    if answered:
        print(f"│  Precisione: {correct/answered*100:.1f}%")
    if tipo == "ripasso" and answered == total:
        passed = wrong <= max_errors
        print(f"│  {G}{B}PROMOSSO{X}" if passed else f"│  {R}{B}✗ BOCCIATO{X}  {D}(troppi errori){X}")
    print(f"{D}└──────────────────────────────────────{X}")
    # un ripasso conta come quiz solo se è lungo come un esame
    if tipo != "ripasso" or total >= EXAM_QUESTIONS:
        record_quiz(tipo, correct, wrong, passed)
    print(mastery_progress_line(mastery))
    print(history_line())
    mastery_alert_if_complete(mastery)
    ask_last_explanation()

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
    practice_session(weighted_order(pool)[:EXAM_QUESTIONS], title, tipo="ripasso")
