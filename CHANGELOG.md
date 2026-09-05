# Registro delle modifiche

Le modifiche degne di nota, versione per versione. La sezione di una versione è
ciò che compare sulla pagina della release: `tools/release_notes.py` la legge da
questo file e la compone con la premessa fissa di `.github/release-body.md`, così
le note e questo file non possono divergere.

Il formato segue [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) e la
numerazione il [versionamento semantico](https://semver.org/spec/v2.0.0.html).

## [Non rilasciato]

Niente, per ora.

## [0.3.1] — 2026-09-05

Quattro impostazioni che non facevano niente.

### Corretto

- **`auto_repair_labels` adesso funziona.** Era dichiarata come un
  interruttore sulla correzione delle nove estrazioni che il mirror storico
  etichetta 1998 invece di 1999, ma la correzione veniva applicata comunque.
  Ora arriva davvero alla sorgente, e c'è un interruttore nelle Impostazioni.
  Resta attiva per impostazione predefinita: quelle nove sono davvero
  sbagliate. Disattivandola si importano i byte del mirror così come sono, che
  è il modo per confrontarli con un'altra fonte.
- **`validation_baselines` adesso funziona.** Decide quali metodi trovi già
  spuntati nella scheda Validazione, e la scelta di una prova viene ricordata.
  TimesFM resta fuori dal valore predefinito: una chiamata al modello per ogni
  estrazione valutata non è quello che dovrebbe costare il primo clic.
- **`numbers_per_combination` e `last_archive_update` sono state rimosse.**
  Nessuna delle due veniva letta: la prima duplicava una costante — chi
  l'avesse messa a 7 non avrebbe visto né un effetto né un errore — e la
  seconda l'indicatore di freschezza, che legge l'archivio e quindi non può
  disallinearsi da esso.
- Due test impediscono che succeda di nuovo, in entrambe le direzioni: uno
  fallisce se una chiave dei valori predefiniti non viene letta da nessuna
  parte, l'altro se una chiave che un utente dovrebbe poter impostare non è
  raggiungibile dal pannello.

Un `config/settings.json` esistente continua a funzionare: le due chiavi
rimosse restano nel file e vengono semplicemente ignorate.

## [0.3.0] — 2026-09-04

Quanto piccolo dev'essere un vantaggio perché la validazione lo veda.

### La sensibilità dell'esperimento

- **`--power`, e il pulsante Calibra nella scheda Validazione.** Rifanno la
  stessa prova contro previsori il cui vantaggio è noto perché ce l'ha messo
  il programma, e riportano con quale frequenza la validazione se ne accorge.
  «Non abbiamo trovato niente» e «non avremmo potuto trovarlo» producevano
  finora lo stesso tabellone; adesso c'è un numero che li distingue.
- La riga a dimensione zero è il controllo e non contiene alcun vantaggio:
  segnala qualcosa nel 4% e nel 5% dei casi contro il 5% nominale. Le
  ripetizioni per riga sono cento, perché con venti l'errore su ogni
  percentuale è di undici punti e il controllo sembrava rotto quando non lo
  era.

### La graduatoria completa, non solo i primi sei

- **Il backtest riporta ora anche il rango medio dei numeri usciti** sulla
  graduatoria di tutti e novanta, accanto al conteggio dei centri. Il caso
  vale 45,5.
- Serve perché il conteggio dei centri guarda solo i primi sei numeri di
  novanta: un vantaggio che esiste e non arriva fin lassù è invisibile per
  costruzione. La calibrazione lo mostra su una delle tre forme di vantaggio
  provate, dove lo z dei centri resta lo stesso identico numero a ogni
  dimensione mentre il rango arriva a +11.
- **Non è una misura migliore, è una seconda lettura.** Sulla forma dove il
  vantaggio arriva in cima il conteggio dei centri è nettamente più sensibile.
  Sono cieche in punti diversi e vengono stampate entrambe.
- I pari merito usano il rango medio del gruppo. `frequenza` assegna a novanta
  numeri solo quattordici punteggi distinti, con gruppi fino a diciassette, e
  senza questo la statistica leggerebbe il criterio di spareggio — che ordina
  per numero — come una preferenza per i numeri bassi.

### Test multipli

- Il riepilogo dei cinque test di indipendenza applica ora la **correzione di
  Holm-Bonferroni** e stampa i valori p corretti, invece di lasciare al
  lettore il conto a mente. Dichiara anche la probabilità che almeno uno dei
  cinque scenda sotto il 5% per puro caso, che è il 23%.
- Lo sbilanciamento nella somma dei sei numeri sopravvive alla correzione
  (p corretto 0,0009). Resta quello che era: reale nei dati vecchi, assente
  negli ultimi sei anni, e troppo piccolo per interessare a un giocatore.

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
