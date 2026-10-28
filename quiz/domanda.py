"""Una domanda: la mostra, legge la risposta e salva il risultato (usata da tutte le modalità)."""

from datetime import datetime

from . import aiuti
from .aiuti import (
    highlight, show_rule_on_request, show_key_words, show_traps, show_summary, show_previous,
)
from .config import REVIEW_DONE, G, R, B, D, X, Y
from .immagini import image_link, open_image, show_image, show_sixel
from .progressi import save_errors, mark_correct, review_correct, review_wrong

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
            if aiuti.previous is not None:   # poi ripropone la domanda attuale, per non perderla
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
    aiuti.previous = q   # dalla prossima domanda, "-" ne mostra la spiegazione
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
