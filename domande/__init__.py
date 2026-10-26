"""
Banca domande per patente.py, divisa per categoria (un file per categoria).
Generata da importa.py: listato ministeriale ufficiale A/B.

Ogni file ha:
    CATEGORIA = "Nome categoria"
    QUESTIONS = [ {...}, {...}, ... ]   # un dizionario per domanda

Campi di ogni domanda (solo i primi due sono obbligatori):
    "domanda":      il testo
    "risposta":     True = VERO, False = FALSO
    "riassunto":    la domanda in breve, mostrata col tasto r2
    "spiegazione":  spiegazione lunga, mostrata quando sbagli
    "regola":       regola breve, mostrata premendo ? dopo la spiegazione
    "trabocchetti": parole della domanda da evidenziare quando sbagli
    "immagine":     nome di un file in domande/immagini/ oppure un URL

Per controllare di non aver sbagliato qualcosa: python3 patente.py --controlla
Per una nuova categoria: crea un nuovo file, importalo qui sotto
e aggiungilo alla lista CATEGORIE.
"""

from . import (
    definizioni_veicoli_e_doveri_del_conducente,
    segnali_di_pericolo,
    segnali_di_precedenza,
    segnali_di_divieto,
    segnali_di_obbligo,
    segnali_di_indicazione,
    pannelli_integrativi_dei_segnali,
    segnali_complementari_temporanei_e_di_cantiere,
    segnaletica_orizzontale,
    semafori_e_agenti_del_traffico,
    velocita_e_passaggi_a_livello,
    distanza_di_sicurezza,
    circolazione_posizione_e_manovre,
    precedenza_agli_incroci,
    norme_sul_sorpasso,
    fermata_sosta_arresto_e_partenza,
    veicolo_fermo_autostrade_e_strade_extraurbane,
    luci_clacson_spie_e_simboli,
    cinture_bambini_casco_e_dispositivi_di_sicurezza,
    patenti_documenti_e_sanzioni,
    prevenzione_e_comportamento_in_caso_di_incidente,
    condizioni_del_conducente_e_primo_soccorso,
    responsabilita_e_assicurazione,
    consumi_ambiente_e_inquinamento,
    meccanica_manutenzione_e_tenuta_di_strada,
)

CATEGORIE = [
    definizioni_veicoli_e_doveri_del_conducente,
    segnali_di_pericolo,
    segnali_di_precedenza,
    segnali_di_divieto,
    segnali_di_obbligo,
    segnali_di_indicazione,
    pannelli_integrativi_dei_segnali,
    segnali_complementari_temporanei_e_di_cantiere,
    segnaletica_orizzontale,
    semafori_e_agenti_del_traffico,
    velocita_e_passaggi_a_livello,
    distanza_di_sicurezza,
    circolazione_posizione_e_manovre,
    precedenza_agli_incroci,
    norme_sul_sorpasso,
    fermata_sosta_arresto_e_partenza,
    veicolo_fermo_autostrade_e_strade_extraurbane,
    luci_clacson_spie_e_simboli,
    cinture_bambini_casco_e_dispositivi_di_sicurezza,
    patenti_documenti_e_sanzioni,
    prevenzione_e_comportamento_in_caso_di_incidente,
    condizioni_del_conducente_e_primo_soccorso,
    responsabilita_e_assicurazione,
    consumi_ambiente_e_inquinamento,
    meccanica_manutenzione_e_tenuta_di_strada,
]

# Lista finale usata da patente.py: ogni domanda con tutti i campi
QUESTIONS = []
for modulo in CATEGORIE:
    nome_file = modulo.__name__.split(".")[-1]   # es. "segnali_di_pericolo"
    for d in modulo.QUESTIONS:
        if "domanda" not in d or "risposta" not in d:
            raise ValueError(
                f"domande/{nome_file}.py: manca \"domanda\" o \"risposta\" in:\n  {d}"
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
