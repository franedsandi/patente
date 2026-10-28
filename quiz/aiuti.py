"""Aiuti: r1 (parole chiave e stima %), r2 (trabocchetto), r3 (riassunto),
? (regola breve dopo un errore), - (spiegazione della domanda precedente)."""

import math
import re
import select
import sys
import time
from collections import Counter

from .config import QUESTIONS, B, D, U, X, Y

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
# La aggiorna domanda.py (aiuti.previous = q) dopo ogni risposta.
previous = None

def show_previous(forzato=False):
    q = previous
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

def ask_last_explanation(forzato=False):
    """A fine quiz: "-" mostra la spiegazione dell'ultima domanda (non c'è una domanda dopo).
    Nel --forzato la finestra si chiude da sola dopo 8 secondi se non premi niente."""
    if previous is None:
        if forzato:
            time.sleep(8)
        return
    if forzato:
        print(f"\n{D}la finestra si chiuderà tra 8 secondi · - + invio = spiegazione "
              f"dell'ultima domanda{X}")
        sys.stdout.flush()
        # select: aspetta al massimo 8 secondi che arrivi una riga dalla tastiera
        ready, _, _ = select.select([sys.stdin], [], [], 8)
        if not ready or sys.stdin.readline().strip() != "-":
            return
        show_previous(forzato)
        prompt = f"\n       {D}invio = chiudi la finestra{X} "
    else:
        prompt = f"\n       {Y}▸ - = spiegazione dell'ultima domanda · invio = fine{X} "
        try:
            if input(prompt).strip() != "-":
                return
        except (EOFError, KeyboardInterrupt):
            return
        show_previous(forzato)
        prompt = f"\n       {D}invio = fine{X} "
    try:
        input(prompt)
    except (EOFError, KeyboardInterrupt):
        pass
