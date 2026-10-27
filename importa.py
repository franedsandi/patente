#!/usr/bin/env python3
"""
importa.py — Scarica le domande ufficiali della patente A/B e rigenera la cartella domande/.

Fonte: https://github.com/AaronGreedy/patente-zero
  - domande, risposte e figure: listato ministeriale ufficiale (Portale dell'Automobilista)
  - spiegazioni, regole brevi e trabocchetti: generati con AI,
    aiutano a capire ma NON sono testo ufficiale

Uso:
    python3 importa.py

ATTENZIONE: cancella e riscrive tutti i file .py in domande/ e le immagini in domande/immagini/.
"""

import io
import json
import re
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

ZIP_URL = "https://github.com/AaronGreedy/patente-zero/archive/refs/heads/main.zip"
QUESTIONS_DIR = Path(__file__).resolve().parent / "domande"
IMAGES_DIR = QUESTIONS_DIR / "immagini"


# Contenuto di domande/__init__.py; {NAMES} viene sostituito con l'elenco dei file.
INIT_TEMPLATE = '''"""
Banca domande per patente.py, divisa per categoria (un file per categoria).
Generata da importa.py: listato ministeriale ufficiale A/B.

Ogni file ha:
    CATEGORIA = "Nome categoria"
    QUESTIONS = [ {...}, {...}, ... ]   # un dizionario per domanda

Campi di ogni domanda (solo i primi due sono obbligatori):
    "domanda":      il testo
    "risposta":     True = VERO, False = FALSO
    "riassunto":    la domanda in breve, mostrata col tasto r3
    "spiegazione":  spiegazione lunga, mostrata quando sbagli
    "regola":       regola breve, mostrata premendo ? dopo la spiegazione
    "trabocchetti": parole della domanda da evidenziare quando sbagli
    "immagine":     nome di un file in domande/immagini/ oppure un URL

Per controllare di non aver sbagliato qualcosa: python3 patente.py --controlla
Per una nuova categoria: crea un nuovo file, importalo qui sotto
e aggiungilo alla lista CATEGORIE.
"""

from . import (
{NAMES}
)

CATEGORIE = [
{NAMES}
]

# Lista finale usata da patente.py: ogni domanda con tutti i campi
QUESTIONS = []
for modulo in CATEGORIE:
    nome_file = modulo.__name__.split(".")[-1]   # es. "segnali_di_pericolo"
    for d in modulo.QUESTIONS:
        if "domanda" not in d or "risposta" not in d:
            raise ValueError(
                f"domande/{nome_file}.py: manca \\"domanda\\" o \\"risposta\\" in:\\n  {d}"
            )
        immagine = d.get("immagine", "")
        QUESTIONS.append({
            "categoria": modulo.CATEGORIA,
            "file": nome_file,
            "domanda": d["domanda"],
            "risposta": d["risposta"],
            "riassunto": d.get("riassunto", ""),
            "spiegazione": d.get("spiegazione", ""),
            "regola": d.get("regola", ""),
            "trabocchetti": d.get("trabocchetti", []),
            "immagine": immagine,
            # identifica la domanda in errori.json e padronanza.json: lo stesso testo
            # ("Il segnale raffigurato...") può comparire con immagini diverse
            "chiave": f"{d['domanda']} [{immagine}]" if immagine else d["domanda"],
        })
'''


def slug(title):
    """'Segnali di pericolo' → 'segnali_di_pericolo' (nome valido per un file Python)."""
    accents = str.maketrans("àèéìòù", "aeeiou")
    return re.sub(r"[^a-z0-9]+", "_", title.lower().translate(accents)).strip("_")


def py_value(value):
    """Valore → testo Python. json.dumps scrive stringhe e liste in modo valido anche per Python."""
    if isinstance(value, bool):
        return repr(value)   # True / False (in JSON sarebbe true / false)
    return json.dumps(value, ensure_ascii=False)


def trap_words(question_text, focus):
    """Le parole tra virgolette nel 'focus' che compaiono davvero nella domanda.
    Es. focus: "La frase 'anche in curva' è spesso una parola trappola..." → ["anche in curva"]"""
    found = []
    for phrase in re.findall(r"['\"«]([^'\"«»]{3,40})['\"»]", focus or ""):
        phrase = phrase.strip()
        if phrase.lower() in question_text.lower() and phrase.lower() not in map(str.lower, found):
            found.append(phrase)
    return found


def key_of(text, image):
    """Stessa chiave di domande/__init__.py: il testo, più l'immagine se c'è."""
    return f"{text} [{image}]" if image else text


# ordine dei campi nei file generati
FIELDS = ("domanda", "risposta", "riassunto", "spiegazione", "regola", "trabocchetti", "immagine")


def write_category_file(name, title, list_date, questions):
    lines = [
        f'"""Domande — {title}.',
        "",
        f"Generato da importa.py dal listato ministeriale A/B del {list_date}.",
        "Riassunti, spiegazioni, regole e trabocchetti sono generati con AI: "
        "aiutano a capire ma non sono ufficiali.",
        '"""',
        "",
        f"CATEGORIA = {py_value(title)}",
        "",
        "QUESTIONS = [",
    ]
    for q in questions:
        lines.append("    {")
        for field in FIELDS:
            value = q.get(field)
            if value or field == "risposta":   # i campi vuoti non si scrivono
                lines.append(f"        {py_value(field)}: {py_value(value)},")
        lines.append("    },")
    lines.append("]")
    (QUESTIONS_DIR / f"{name}.py").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_init(file_names):
    names = "\n".join(f"    {n}," for n in file_names)
    (QUESTIONS_DIR / "__init__.py").write_text(
        INIT_TEMPLATE.replace("{NAMES}", names), encoding="utf-8")


def current_summaries():
    """{chiave: riassunto} dai file attuali in domande/ (vuoto se non ci sono)."""
    try:
        import domande
    except Exception:
        return {}
    return {q["chiave"]: q["riassunto"] for q in domande.QUESTIONS if q.get("riassunto")}


def merge_summaries(summaries):
    """Aggiunge i riassunti {chiave: riassunto} alle domande e riscrive i file di domande/.
    Usata da riassumi.py e da:  python3 importa.py --unisci-riassunti FILE.json"""
    import domande
    added = 0
    file_names = []
    for modulo in domande.CATEGORIE:
        name = modulo.__name__.split(".")[-1]
        file_names.append(name)
        match = re.search(r"del (\d{4}-\d{2}-\d{2})", modulo.__doc__ or "")
        questions = []
        for d in modulo.QUESTIONS:
            q = dict(d)
            new = summaries.get(key_of(q["domanda"], q.get("immagine", "")))
            if new and new != q.get("riassunto"):
                q["riassunto"] = new
                added += 1
            questions.append(q)
        write_category_file(name, modulo.CATEGORIA, match.group(1) if match else "?", questions)
    write_init(file_names)
    shutil.rmtree(QUESTIONS_DIR / "__pycache__", ignore_errors=True)
    return added


def download():
    """Scarica lo zip del repository e restituisce (bank, explanations, archive, root)."""
    print(f"scarico {ZIP_URL} ...")
    with urllib.request.urlopen(ZIP_URL, timeout=60) as resp:
        archive = zipfile.ZipFile(io.BytesIO(resp.read()))
    root = archive.namelist()[0].split("/")[0]   # es. "patente-zero-main"
    bank = json.loads(archive.read(f"{root}/data/bank.json"))
    explanations = json.loads(archive.read(f"{root}/data/explanations.json"))
    return bank, explanations, archive, root


def main():
    bank, explanations, archive, root = download()
    meta = bank["metadata"]
    chapters = bank["chapters"]

    # raggruppa le domande per capitolo, saltando i doppioni esatti (stesso testo e immagine)
    by_chapter = {c["id"]: [] for c in chapters}
    seen = set()
    skipped = 0
    for q in bank["questions"]:
        image = Path(q["image"]).name if q.get("image") else ""
        if (q["text"], image) in seen:
            skipped += 1
            continue
        seen.add((q["text"], image))
        if image and not re.fullmatch(r"[0-9a-f]+\.(jpg|png)", image):
            sys.exit(f"nome immagine inatteso, interrompo: {image}")
        e = explanations.get(q["id"]) or {}
        by_chapter[q["chapterId"]].append({
            "domanda": q["text"],
            "risposta": q["answer"],
            "spiegazione": e.get("text", "").strip(),
            "regola": e.get("rule", "").strip(),
            "trabocchetti": trap_words(q["text"], e.get("focus", "")),
            "immagine": image,
        })

    # i riassunti (tasto r3) non arrivano dal download: li tengo da quelli che ci sono già
    old_summaries = current_summaries()
    for qs in by_chapter.values():
        for q in qs:
            q["riassunto"] = old_summaries.get(key_of(q["domanda"], q["immagine"]), "")

    # svuota la cartella domande/ (tranne immagini/LEGGIMI.txt)
    for f in QUESTIONS_DIR.glob("*.py"):
        f.unlink()
    shutil.rmtree(QUESTIONS_DIR / "__pycache__", ignore_errors=True)
    for f in IMAGES_DIR.glob("*"):
        if f.is_dir():              # immagini/sixel/: da rigenerare con sixel.py
            shutil.rmtree(f)
        elif f.name != "LEGGIMI.txt":
            f.unlink()
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    # un file per capitolo
    file_names = []
    for c in chapters:
        name = slug(c["title"])
        file_names.append(name)
        write_category_file(name, c["title"], meta["sourceListDate"], by_chapter[c["id"]])

    # immagini usate dalle domande
    used_images = {q["immagine"] for qs in by_chapter.values() for q in qs if q["immagine"]}
    for image in used_images:
        (IMAGES_DIR / image).write_bytes(archive.read(f"{root}/images/{image}"))

    write_init(file_names)

    all_questions = [q for qs in by_chapter.values() for q in qs]
    with_traps = sum(1 for q in all_questions if q["trabocchetti"])
    print(f"fatto: {len(all_questions)} domande in {len(chapters)} file, {len(used_images)} immagini "
          f"({skipped} doppioni saltati, {with_traps} con trabocchetti evidenziabili)")
    print("controlla con:  python3 patente.py --controlla")
    print("immagini nel terminale (Sixel):  .venv/bin/python sixel.py")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--unisci-riassunti":
        summaries = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        print(f"aggiunti {merge_summaries(summaries)} riassunti alle domande")
    else:
        main()
