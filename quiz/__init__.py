"""
Il codice del quiz, diviso per argomento. Si lancia sempre da patente.py.

    config.py     impostazioni (impostazioni.json), percorsi dei file, colori
    progressi.py  errori, padronanza, ripasso e storico dei quiz (file .json)
    immagini.py   link alle immagini, apertura fuori, Sixel nel terminale
    aiuti.py      r1, r2, r3, ? e -
    domanda.py    una domanda: la mostra, legge la risposta, salva il risultato
    sessioni.py   esame, --forzato, --libero, --categoria, --review
    strumenti.py  --controlla e --pianifica

Ogni file importa dagli altri solo quello che usa (le righe "from .x import ...").
"""
