# Quiz patente B da terminale

Quiz per la teoria della patente A/B con le 7.098 domande ufficiali del Ministero,
tutto nel terminale. Può anche aprirti in automatico un esame simulato a orari fissi.

## 1. Cosa serve

- **Windows con WSL** (Ubuntu). Se non ce l'hai, apri PowerShell e lancia
  `wsl --install`, poi riavvia il PC.
- **Python 3**: su Ubuntu c'è già. Controlla nel terminale WSL:
  ```bash
  python3 --version
  ```
  Se dice "command not found": `sudo apt install python3`

Non serve installare nient'altro: il programma usa solo quello che arriva con Python.

## 2. Mettere il progetto in WSL

Il progetto deve stare **dentro WSL** (es. `~/patente`), non in una cartella Windows.

- **Da una cartella copiata** (es. scaricata in Download):
  ```bash
  cp -r /mnt/c/Users/TUO_UTENTE_WINDOWS/Downloads/patente ~/patente
  ```
- **Da git**, se l'hai messo su GitHub o simili:
  ```bash
  git clone URL_DEL_REPOSITORY ~/patente
  ```

Controlla che sia tutto a posto:
```bash
cd ~/patente
python3 patente.py --controlla
```
Deve rispondere `✓ banca domande ok — 7098 domande, 25 categorie`.
Se mancano le domande (cartella `domande/` vuota), scaricale con `python3 importa.py`.

## 3. Comandi brevi (consigliato)

Aggiungi due alias al tuo `~/.bashrc`, così scrivi `pq` invece di `python3 ~/patente/patente.py --libero`:
```bash
cat >> ~/.bashrc <<'EOF'

# quiz patente: pq = modalità libera, patente = tutti i comandi
alias pq='python3 ~/patente/patente.py --libero'
alias patente='python3 ~/patente/patente.py'
EOF
source ~/.bashrc
```

## 4. Usarlo

```bash
pq                            # modalità libera: tutte le domande, esci quando vuoi
patente                       # esame simulato: 30 domande, promosso con max 3 errori
patente --categoria           # elenco delle categorie
patente --categoria sorpasso  # solo una categoria
patente --review              # ripassa le domande sbagliate
patente --padronanza          # i tuoi progressi
patente --help                # tutti i comandi
```

Durante il quiz:

| Tasto | Cosa fa |
|---|---|
| `y` `v` `t` `s` | VERO (yes, vero, true, sì) |
| `n` `f` | FALSO (no, falso, false) |
| `p` | salta la domanda (non nell'esame) |
| `q` | esci (non nel `--forzato`) |
| `i` | mostra di nuovo l'immagine nel terminale (se supporta Sixel l'immagine compare già da sola sotto la domanda); altrimenti la apre fuori |
| `o` | apre l'immagine fuori, con il visualizzatore di Windows |
| `r1` | prima di rispondere: evidenzia le parole chiave (sempre, solo, non, numeri…) e mostra una stima statistica % VERO / % FALSO (indicativa, spesso vicina al 50%); non nel `--forzato` |
| `r2` | prima di rispondere: la domanda con la parola trabocchetto evidenziata; non nel `--forzato` |
| `r3` | prima di rispondere: riassunto della domanda (vedi sezione 8); non nel `--forzato` |
| `?` | dopo un errore: mostra la regola breve |
| `-` | alla domanda dopo: risposta, spiegazione e regola della domanda precedente (utile se l'hai indovinata senza esserne sicuro); funziona anche nel `--forzato` |

Nel terminale di VS Code puoi anche aprire l'immagine con **Ctrl+click** sul percorso.

### Immagini dentro al terminale (Sixel)

1. Genera le immagini per il terminale (una volta, e di nuovo dopo ogni `importa.py`):
   ```bash
   cd ~/patente
   python3 -m venv .venv               # solo la prima volta
   .venv/bin/pip install pillow        # solo la prima volta
   .venv/bin/python sixel.py
   ```
2. Attiva le immagini nel terminale:
   - **VS Code**: nelle impostazioni (`settings.json`) aggiungi
     `"terminal.integrated.enableImages": true` e riapri il terminale.
   - **Windows Terminal**: le supporta dalla versione 1.22, senza impostazioni.
   - La vecchia console di Windows (`cmd.exe` senza Windows Terminal) non le supporta:
     lì `i` apre l'immagine fuori.
3. Prova: `patente --sixel` dice se il terminale le supporta e ne mostra una.

La variabile d'ambiente `PATENTE_SIXEL` decide come mostrare le immagini:

| Valore | Cosa succede |
|---|---|
| non impostata | rilevamento automatico: se il terminale supporta Sixel le immagini compaiono da sole |
| `1` | Sixel sempre attivo (se il rilevamento automatico sbaglia) |
| `0` | niente immagini nel terminale: `i` le apre fuori, con il visualizzatore di Windows, come prima |

Per renderla permanente aggiungi la riga in fondo al file indicato, poi apri un nuovo terminale:
- nei tuoi terminali: `export PATENTE_SIXEL=0` in `~/.bashrc`
- anche nei quiz automatici: `export PATENTE_SIXEL=0` in `~/.profile` (i quiz automatici non leggono `~/.bashrc`)

I tuoi progressi sono in `errori.json`, `padronanza.json`, `ripasso.json` e `storico.json`
(i quiz fatti: data, tipo, corrette, errate, esito), nella cartella del progetto.
**Non sono in git**: se cambi PC e vuoi tenerli, copiali a mano.

`patente --review` ti ripropone le domande sbagliate, al massimo 30 per volta come un esame
(prima quelle sbagliate più spesso). Una domanda esce dal ripasso quando
la indovini 2 volte di fila (in qualsiasi modalità); se la sbagli di nuovo, ci rientra.

## 5. Quiz automatici a orari fissi

Il PC ti apre da solo una finestra con un esame simulato in modalità `--forzato`
(30 domande, non puoi uscire finché non finisci; poi la finestra si chiude dopo 8 secondi).
Usa l'Utilità di pianificazione di Windows. Non servono permessi di amministratore.

**1. Scegli orari e giorni** in `pianificazione.json`:
```json
{
  "attivo": true,
  "orari": ["11:00", "14:30", "16:00"],
  "weekend": false
}
```
- `orari`: quanti ne vuoi, formato `HH:mm`
- `weekend`: `true` per farli anche sabato e domenica
- `attivo`: `false` per spegnerli tutti senza perdere gli orari

**2. Applica** (dal terminale WSL):
```bash
patente --pianifica
```

**3. Controlla**:
```bash
patente --pianifica stato
```
Mostra ogni orario e la prossima esecuzione.

Ogni volta che modifichi `pianificazione.json`, rilancia `patente --pianifica`.
Per togliere tutto: `patente --pianifica rimuovi`.

I quiz partono solo se il PC è acceso e hai fatto l'accesso a Windows.
Li vedi anche in Windows: *Utilità di pianificazione* → cartella *QuizPatente*.

**Senza WSL a portata di mano**, lo stesso script si lancia da PowerShell:
```powershell
powershell -ExecutionPolicy Bypass -File \\wsl.localhost\Ubuntu\home\TUO_UTENTE_LINUX\patente\setup_quiz_scheduler.ps1
```
(con `-Status` o `-Uninstall` alla fine per stato e rimozione)

## 6. Problemi frequenti

| Problema | Soluzione |
|---|---|
| `pq: command not found` | Hai aperto il terminale prima di aggiungere gli alias: `source ~/.bashrc` |
| `non riesco ad avviare powershell.exe` | `--pianifica` e il tasto `i` funzionano solo in WSL su Windows |
| La finestra del quiz automatico si apre e si chiude subito | Lancia a mano `python3 ~/patente/patente.py --forzato` per vedere l'errore |
| `--controlla` trova problemi | Leggi il messaggio: dice file e domanda da correggere |

## 7. Aggiornare le domande

Quando il Ministero pubblica un nuovo listato (e il progetto
[patente-zero](https://github.com/AaronGreedy/patente-zero) lo aggiorna):
```bash
cd ~/patente
python3 importa.py
python3 patente.py --controlla
```
**Attenzione:** `importa.py` cancella e riscrive tutta la cartella `domande/`.

Le domande, le risposte e le immagini sono quelle ufficiali.
Spiegazioni, regole brevi e trabocchetti sono generati con AI: aiutano a capire, ma non sono ufficiali.

## 8. Riassunti delle domande (tasto r3)

I riassunti sono nel campo `"riassunto"` di ogni domanda e il quiz li usa senza internet.
`importa.py` li conserva quando riscarica le domande. Sono già generati; `riassumi.py`
serve solo se un giorno arrivano domande nuove senza riassunto: genera solo quelle mancanti.
Serve una API key di Anthropic (si paga a consumo).

```bash
cd ~/patente
python3 -m venv .venv                 # solo la prima volta
.venv/bin/pip install anthropic       # solo la prima volta
export ANTHROPIC_API_KEY=...          # la tua chiave

.venv/bin/python riassumi.py prova    # 20 riassunti di prova: guardi la qualità e il costo stimato
.venv/bin/python riassumi.py invia    # manda tutte le altre domande (Batch API, costa la metà)
.venv/bin/python riassumi.py scarica  # dopo circa un'ora: salva i riassunti
```

Usa Claude Haiku 5.5, economico. Con `--opus` (es. `riassumi.py prova --opus`)
usa Claude Opus 5.5, più caro: utile solo se la qualità di Haiku non ti basta.
Anche i riassunti sono generati con AI: non rivelano la risposta, ma non sono ufficiali.
