#!/usr/bin/env python3
"""
riassumi.py — Genera con Claude i riassunti delle domande (tasto r2 nel quiz).

Si fa UNA volta sola; i riassunti finiscono nel campo "riassunto" delle domande
e poi il quiz li usa senza internet. Serve una API key di Anthropic (si paga a consumo).
Genera solo le domande che non hanno ancora un riassunto.

Preparazione (una volta):
    python3 -m venv .venv
    .venv/bin/pip install anthropic
    export ANTHROPIC_API_KEY=...        # la tua chiave

Uso:
    .venv/bin/python riassumi.py prova [N]    # N riassunti di prova (default 20): qualità + costo stimato
    .venv/bin/python riassumi.py invia        # manda TUTTE le domande senza riassunto (Batch API, -50%)
    .venv/bin/python riassumi.py scarica      # controlla il batch e, se finito, salva nelle domande

Modello: Claude Haiku 5.5 (economico). Opzione --opus: Claude Opus 5.5 (più caro).
"""

import json
import random
import sys
from pathlib import Path

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

from domande import QUESTIONS
from importa import merge_summaries

HERE = Path(__file__).resolve().parent
BATCH_FILE = HERE / "riassunti_batch.json"   # id del batch in corso + quale domanda è quale

MODELS = {
    # prezzi in dollari per milione di token (input, output); il Batch API costa la metà
    "claude-opus-5-5": (4.00, 20.00),
    "claude-haiku-5-5": (0.10, 0.50),
}

SYSTEM_PROMPT = """Sei un tutor per l'esame di teoria della patente italiana.
Ricevi una domanda vero/falso del quiz ministeriale.
Riscrivila in una sola riga breve (massimo 15 parole) che metta in evidenza
solo gli elementi chiave da valutare per rispondere, separati da " → ".

Regole:
- NON dire se l'affermazione è vera o falsa e non dare indizi sulla risposta.
- Niente spiegazioni, niente premesse: scrivi solo la riga.
- Mantieni le parole decisive della domanda (sempre, solo, non, numeri, colori...).

Esempio:
Domanda: L'attraversamento pedonale è una parte della strada, separata dalla carreggiata mediante una striscia gialla
Riga: Attraversamento pedonale → separato dalla carreggiata? → con striscia gialla?"""


def request_params(model, question_text):
    return MessageCreateParamsNonStreaming(
        model=model,
        max_tokens=1024,
        output_config={"effort": "low"},   # compito semplice: poco ragionamento, meno token
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Domanda: {question_text}"}],
    )


def text_of(message):
    """La riga di riassunto, oppure "" se il modello ha rifiutato o non ha risposto."""
    if message.stop_reason == "refusal":
        return ""
    text = next((b.text for b in message.content if b.type == "text"), "")
    return " ".join(text.split())   # una riga sola, senza spazi doppi


def missing_questions():
    return [q for q in QUESTIONS if not q["riassunto"]]


def cost(model, input_tokens, output_tokens):
    price_in, price_out = MODELS[model]
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000


# ---- prova: pochi riassunti subito, per vedere qualità e costo ---------------
def try_some(client, model, n):
    todo = missing_questions()
    sample = random.sample(todo, min(n, len(todo)))
    summaries = {}
    tokens_in = tokens_out = 0
    for q in sample:
        message = client.messages.create(**request_params(model, q["domanda"]))
        tokens_in += message.usage.input_tokens
        tokens_out += message.usage.output_tokens   # include il ragionamento (thinking)
        summary = text_of(message)
        print(f"\n{q['domanda']}\n  → {summary or '(nessun riassunto)'}")
        if summary:
            summaries[q["chiave"]] = summary
    merge_summaries(summaries)

    per_question = cost(model, tokens_in, tokens_out) / len(sample)
    remaining = len(todo) - len(sample)
    print(f"\nprova: {len(sample)} domande, costo {cost(model, tokens_in, tokens_out):.4f} $")
    print(f"stima per le altre {remaining}: {per_question * remaining:.2f} $ normale, "
          f"{per_question * remaining / 2:.2f} $ con il Batch API (invia)")


# ---- invia: tutte le domande mancanti in un batch ---------------------------
def send_batch(client, model):
    if BATCH_FILE.exists():
        sys.exit(f"c'è già un batch in corso ({BATCH_FILE.name}): prima lancia 'scarica'")
    todo = missing_questions()
    if not todo:
        sys.exit("tutte le domande hanno già un riassunto")
    # custom_id può contenere solo lettere, numeri, - e _: uso q00001... e salvo la corrispondenza
    ids = {f"q{i:05d}": q["chiave"] for i, q in enumerate(todo)}
    by_key = {q["chiave"]: q for q in todo}
    batch = client.messages.batches.create(requests=[
        Request(custom_id=cid, params=request_params(model, by_key[key]["domanda"]))
        for cid, key in ids.items()
    ])
    BATCH_FILE.write_text(json.dumps({"batch_id": batch.id, "model": model, "ids": ids},
                                     ensure_ascii=False), encoding="utf-8")
    print(f"inviato batch {batch.id} con {len(ids)} domande ({model})")
    print("di solito finisce entro un'ora (massimo 24): poi lancia  riassumi.py scarica")


# ---- scarica: salva i risultati quando il batch è finito --------------------
def fetch_batch(client):
    if not BATCH_FILE.exists():
        sys.exit("nessun batch in corso: prima lancia 'invia'")
    state = json.loads(BATCH_FILE.read_text(encoding="utf-8"))
    batch = client.messages.batches.retrieve(state["batch_id"])
    counts = batch.request_counts
    if batch.processing_status != "ended":
        print(f"non ancora finito: {counts.succeeded} pronti, {counts.processing} in lavorazione")
        return

    summaries = {}
    saved = failed = 0
    tokens_in = tokens_out = 0
    for result in client.messages.batches.results(batch.id):   # ordine casuale: uso custom_id
        key = state["ids"].get(result.custom_id)
        if result.result.type == "succeeded" and key:
            message = result.result.message
            tokens_in += message.usage.input_tokens
            tokens_out += message.usage.output_tokens
            summary = text_of(message)
            if summary:
                summaries[key] = summary
                saved += 1
                continue
        failed += 1
    merge_summaries(summaries)
    BATCH_FILE.unlink()
    print(f"salvati {saved} riassunti nelle domande ({failed} non riusciti)")
    print(f"costo: {cost(state['model'], tokens_in, tokens_out) / 2:.2f} $ (prezzo Batch API)")
    if failed:
        print("per riprovare quelli non riusciti: lancia di nuovo  riassumi.py invia")


def main():
    args = [a for a in sys.argv[1:] if a != "--opus"]
    model = "claude-opus-5-5" if "--opus" in sys.argv else "claude-haiku-5-5"
    if not args or args[0] not in ("prova", "invia", "scarica"):
        print(__doc__)
        return
    client = anthropic.Anthropic()   # legge ANTHROPIC_API_KEY (o il profilo di `ant auth login`)
    try:
        if args[0] == "prova":
            try_some(client, model, int(args[1]) if len(args) > 1 else 20)
        elif args[0] == "invia":
            send_batch(client, model)
        else:
            fetch_batch(client)
    except anthropic.AuthenticationError:
        sys.exit("API key non valida: controlla ANTHROPIC_API_KEY")
    except TypeError as e:
        if "authentication" not in str(e):   # un altro errore: lo mostro com'è
            raise
        sys.exit("API key mancante: export ANTHROPIC_API_KEY=...")
    except anthropic.RateLimitError:
        sys.exit("troppe richieste in poco tempo: riprova tra qualche minuto")
    except anthropic.APIStatusError as e:
        sys.exit(f"errore dell'API ({e.status_code}): {e.message}")
    except anthropic.APIConnectionError:
        sys.exit("niente connessione a internet?")


if __name__ == "__main__":
    main()
