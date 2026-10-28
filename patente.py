#!/usr/bin/env python3
"""
patente.py — Simulatore quiz patente B italiana da terminale.

Uso (patente = python3 patente.py):
  pq                          modalità libera (= patente --libero)
  patente                     esame simulato: 30 domande, max 3 errori (*)
  patente --forzato           esame senza uscita: q e Ctrl+C disattivati
  patente --libero [N]        modalità libera: N domande (default: tutte)
  patente --categoria         elenca le categorie
  patente --categoria NOME [N]  solo una categoria (es. sorpasso, segnali)
  patente --review            ripassa le domande sbagliate, max 30 per volta,
                              1 errore ammesso ogni 10 domande (*)
                              (escono dopo 2 risposte giuste di fila) (*)
  patente --padronanza        i tuoi progressi, in totale e per categoria
  patente --stats             errori per categoria
  patente --reset             cancella gli errori (errori.json, ripasso.json)
  patente --reset-padronanza  cancella i progressi (padronanza.json)
  patente --reset --all       cancella TUTTI i progressi (errori, ripasso,
                              padronanza, quiz fatti), dopo conferma
  patente --count             quante domande ci sono
  patente --controlla         controlla i file delle domande
  patente --sixel             prova le immagini dentro al terminale

Quiz automatici (Windows Task Scheduler, orari in pianificazione.json):
  patente --pianifica         applica pianificazione.json
  patente --pianifica stato   mostra orari e prossima esecuzione
  patente --pianifica rimuovi toglie tutti i quiz automatici

(*) valori di default: si cambiano in impostazioni.json

Risposte:  VERO = y / v / t / s       FALSO = n / f
           p = salta   q = esci   - = spiegazione della domanda precedente
           (a fine quiz, - = spiegazione dell'ultima domanda)
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

import sys

from quiz.config import QUESTIONS
from quiz.immagini import sixel_check
from quiz.progressi import show_mastery, reset_mastery, show_stats, reset_errors, reset_all
from quiz.sessioni import exam_session, free_quiz, list_categories, category_quiz, review
from quiz.strumenti import check_bank, schedule

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
        if "--all" in args[1:]:
            reset_all()
        else:
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
