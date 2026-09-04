# Registro delle modifiche

Le modifiche degne di nota, versione per versione. La sezione di una versione è
ciò che compare sulla pagina della release: `tools/release_notes.py` la legge da
questo file e la compone con la premessa fissa di `.github/release-body.md`, così
le note e questo file non possono divergere.

Il formato segue [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) e la
numerazione il [versionamento semantico](https://semver.org/spec/v2.0.0.html).

## [Non rilasciato]

Niente, per ora.

## [0.2.0] — 2026-09-04

Tyche parla italiano.

### Tutto in italiano

- **Interfaccia, riga di comando, messaggi di errore, report e documentazione
  sono ora in italiano.** Il SuperEnalotto è un gioco italiano e non c'era
  motivo perché il programma che lo analizza parlasse un'altra lingua. Le sei
  schede sono *Prova del nove*, *Archivio*, *Statistiche*, *Previsione*,
  *Validazione* e *Impostazioni*; le schermate del README sono state rifatte.
- I metodi di previsione hanno nomi italiani — `timesfm`, `frequenza`,
  `ritardo`, `casuale` — e così le tre rappresentazioni passate al modello:
  `presenza`, `frequenza`, `ritardo`. Sono i nomi che si scrivono sulla riga di
  comando, quindi il cambiamento è **incompatibile** con gli script che usavano
  quelli inglesi.
- I numeri sono formattati all'italiana: `4.260 estrazioni`, date `03/09/2026`.
  I decimali mantengono il punto di proposito, perché le stesse schermate
  mostrano χ², z e valori p accanto ai conteggi e mescolare due convenzioni
  nella stessa riga si legge peggio di una sola. `core/localise.py` è l'unico
  posto dove questa scelta è scritta, e non dipende da una locale `it_IT.UTF-8`
  che i runner di CI non hanno.
- L'archivio su disco non cambia: il CSV continua a usare date ISO e interi
  nudi, perché è un formato di scambio e non una schermata.
- L'autodiagnosi del pacchetto Windows stampa ora `autodiagnosi: SUPERATA`. Il
  workflow di release cerca quella riga, ed è cambiata insieme al resto.

## [0.1.0] — 2026-09-04

Prima release.

### L'archivio

- Lo storico delle estrazioni dal **3 dicembre 1997 a oggi**, 4.260 estrazioni,
  scaricato da estrazioni.it in una sola richiesta. `--update` lo aggiorna,
  `--import` legge un file scaricato a mano, un CSV di riepilogo su mirror
  costruisce un archivio vuoto senza configurare niente, e lo scraping HTML
  anno per anno è l'ultima risorsa.
- Ogni scrittura viene prima simulata. Le righe che contraddirebbero
  un'estrazione già archiviata, e gli errori di integrità che l'unione
  introdurrebbe, sono segnalati prima che venga scritto qualcosa; le fonti il
  cui indirizzo è stato dedotto anziché documentato chiedono sempre conferma.
- `integrity_report` controlla la sequenza, non solo le singole righe: date
  duplicate, numeri di concorso duplicati, buchi dentro un anno completo. Ha
  trovato nove estrazioni del 1999 etichettate 1998 nel mirror, e
  `repair_year_offset` le rimette a posto — verificato contro una fonte
  indipendente, comprese le due che condividono la data con il proprio
  duplicato.
- Di quanto l'archivio è indietro, in estrazioni, si legge sullo schermo e non
  nella documentazione, misurato sulla cadenza dell'archivio stesso.

### La misura

- Cinque test dell'ipotesi che le estrazioni siano indipendenti e uniformi:
  uniformità dei singoli numeri, distribuzione dei ritardi, indipendenza
  seriale, ripetizioni fra estrazioni consecutive e somma dei sei numeri.
- Backtest walk-forward senza look-ahead, valutato contro l'ipotesi nulla
  ipergeometrica in forma chiusa — il caso vale 0,4 numeri indovinati per
  estrazione, esattamente. TimesFM, i numeri caldi, il ritardo e un generatore
  di numeri casuali sono valutati sulle stesse estrazioni e riportati tutti.
- Probabilità esatte delle categorie di premio, ed esportazione SQLite per
  interrogare l'archivio in SQL.

### Come si ottiene

- Un **pacchetto Windows x64**, allegato a questa release. Si scompatta la
  cartella e si esegue `start.cmd`, che confronta l'eseguibile con l'impronta
  registrata al momento della compilazione prima di avviarlo. Non è firmato,
  quindi SmartScreen dirà che l'editore è sconosciuto — lo SHA-256 dell'archivio
  è in queste note, così il download si può verificare per una strada diversa da
  quella su cui è arrivato.
- macOS e Linux si eseguono dai sorgenti. E anche Windows, volendo.

### La previsione

- TimesFM 3.0 (`google/timesfm-3.0-pytorch`, 330 milioni di parametri) su
  novanta serie, una per numero. Verificato da capo a fondo in CI, sul
  checkpoint vero.
- Niente batte il caso. Questo è il risultato, non un'avvertenza: sulle ultime
  1.000 estrazioni il modello fondazionale, le due euristiche popolari e la
  linea di base casuale segnano tutti 0,4.
