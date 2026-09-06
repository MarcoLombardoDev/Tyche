# Registro delle modifiche

Le modifiche degne di nota, versione per versione. La sezione di una versione è
ciò che compare sulla pagina della release: `tools/release_notes.py` la legge da
questo file e la compone con la premessa fissa di `.github/release-body.md`, così
le note e questo file non possono divergere.

Il formato segue [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) e la
numerazione il [versionamento semantico](https://semver.org/spec/v2.0.0.html).

## [Non rilasciato]

Allineamento alle convenzioni degli altri cinque prodotti della famiglia.

### Aggiunto

- **Pacchetti per macOS e Linux**, oltre a quello per Windows. Ognuno è
  compilato sul proprio runner — PyInstaller non compila per altre
  piattaforme — e nessuno viene caricato prima di aver avviato Tk davvero,
  essersi presentato sul backend giusto per il suo sistema, aver dimostrato di
  contenere TimesFM ed essere stato avviato dal proprio launcher.
- **`packaging/start.sh`**, il launcher per macOS e Linux: verifica l'impronta
  dell'eseguibile prima di avviarlo, come già faceva `start.cmd` su Windows.
  Su macOS viaggia come `start.command`, così il Finder lo esegue con un
  doppio clic invece di aprirlo in un editor.
- **I testi di licenza dentro ogni archivio**, in `licenses/`, insieme
  all'inventario di quale binario appartiene a quale progetto, generato dalla
  macchina che ha costruito l'archivio. Fino alla 0.3.3 un archivio non
  conteneva nessun testo di licenza, nemmeno quello di Tyche — e non è una
  formalità: PyTorch, NumPy e le altre librerie BSD e MIT chiedono che la loro
  nota accompagni il binario. Lo assemblano `tools/collect_licences.py` e
  `tools/licence_inventory.py`.
- **Il font dell'interfaccia scelto invece che ereditato** (`core/fonts.py`),
  la stessa lista di preferenze degli altri prodotti. Prima ogni etichetta
  prendeva il predefinito di CustomTkinter, che è Roboto su Linux e il font di
  sistema altrove: la stessa finestra sembrava tre programmi diversi sulle tre
  piattaforme a cui adesso Tyche arriva.
- **La finestra si apre massimizzata**, con `1280x840` come misura di ripiego.
- Modelli per issue e pull request, e `.gitattributes` che fissa i fine riga
  dei due launcher: CRLF per `start.cmd`, LF per `start.sh`, perché una
  `autocrlf` locale può rompere l'uno o l'altro.
- `tests/test_docs.py`, `tests/test_packaging.py` e
  `tests/test_third_party_licences.py`, che erano gli unici tre guardiani
  condivisi che Tyche non aveva.
- La CI esegue la suite anche su Windows, e i guardiani sui documenti in un
  job a parte che risponde in venti secondi con pytest e PyYAML soli. Perché
  ci riesca, il test che confronta il messaggio «Nessun archivio in» con
  quello che la CI cerca legge la costante dal sorgente invece di importare
  `main`, che tira dentro numpy.

  Sul runner Windows Tk non parte: il Python di `actions/setup-python` importa
  `tkinter` e poi non riesce a leggere il proprio `tcl8.6/init.tcl`. È un
  difetto dell'immagine, non di Tyche, quindi quel job prova ad aprire una
  `Tk()` e decide da lì se pretendere l'interfaccia — invece di saltarla in
  silenzio, che sarebbe l'altro modo di sbagliare. Se una versione futura
  dell'immagine lo sistema, il job ricomincia a pretenderla da solo.

### Modificato

- `THIRD-PARTY-LICENSES.md` riscritto secondo lo scheletro condiviso, e dice
  esplicitamente che l'inventario che conta è quello dentro l'archivio
  scaricato, non questo.
- `Tyche.spec` sceglie l'icona in base alla piattaforma: `.icns` su macOS,
  `.ico` su Windows, niente su Linux. Un `.ico` fisso è ciò che ha fatto
  fallire la prima release macOS di XIP, perché PyInstaller accetta solo
  `.icns` lì e converte soltanto se Pillow è installato.

## [0.7.0] — 2026-09-06

Tyche è software libero: AGPL-3.0-or-later.

### Licenza

- **`LICENSE` è ora la AGPL-3.0**, al posto di «tutti i diritti riservati», e
  tutti e 43 i file sorgente — i 42 moduli Python e `Tyche.spec` — portano
  l'intestazione `SPDX-License-Identifier: AGPL-3.0-or-later`.
- Si può usare, studiare, modificare e ridistribuire per qualunque scopo. Chi
  lo distribuisce, o lo espone come servizio di rete, deve consegnare il
  sorgente alle stesse condizioni.
- **Nessuna licenza commerciale e nessun CLA.** Una contribuzione si offre
  sotto la stessa licenza, che è quello che l'AGPL prevede di suo: un CLA
  serve a poter rilicenziare il codice altrui sotto termini che chi l'ha
  scritto non ha scelto, ed è quello che serve a chi vende.
- **Il motivo per cui non c'è una parte commerciale è misurato, non
  supposto.** Il job `checkpoint-licence` ha chiesto alle model card: i pesi
  `google/timesfm-3.0-pytorch` dichiarano
  `timesfm-non-commercial-license-v1.0`, mentre il 2.5 e l'1.0 sono
  Apache-2.0. Vendere una licenza commerciale su un programma il cui metodo
  principale gira su pesi che lo vietano non si può fare onestamente.

### Aggiunto

- **`THIRD-PARTY-LICENSES.md`**: che cosa Tyche richiede, sotto quale licenza,
  e che cosa ognuna chiede a chi ridistribuisce. Con la distinzione che conta
  di più — i pesi del modello non sono il codice del modello — e la tabella
  delle licenze dichiarate dai tre checkpoint.
- **`CONTRIBUTING.md`**: come si prepara una modifica, che cosa deve portare, e
  le tre cose che non si toccano perché farebbero sembrare vincibile una
  lotteria.

### Invariato

Il funzionamento del programma. Nessun metodo, nessuna impostazione, nessun
checkpoint è cambiato: la 0.7.0 dice sotto quali condizioni si può avere
Tyche, non che cosa Tyche fa.

## [0.6.3] — 2026-09-06

L'icona, la stessa famiglia degli altri strumenti.

### Aggiunto

- **Tyche ha un'icona**: l'iniziale in un carattere con grazie, nera su bianco
  dentro una cornice sottile — lo stesso disegno di Argus, una lettera di
  differenza, così una barra delle applicazioni con più strumenti aperti si
  legge come una famiglia sola.
- La disegna `tools/make_icon.py`, che è una **copia** di quello di Argus e non
  una variante: prende il nome del prodotto e ne ricava la lettera. I file
  sono committati e non generati durante la build, così nessuna release
  dipende da quali caratteri tipografici si trovano sulla macchina che compila.
- L'eseguibile Windows porta l'icona come propria risorsa, e la finestra la
  imposta a parte all'avvio: sono due meccanismi diversi e servono entrambi.

## [0.6.2] — 2026-09-06

La documentazione allineata a quello che il programma fa davvero.

### Documentazione

- **La premessa che compare su ogni pagina di release descriveva la 0.1.0.**
  Non nominava il percorso in quattro passi, né i sistemi, né il SuperStar, né
  il costo della giocata, né la calibrazione della validazione. Riscritta.
- Il README mostra ora anche la scheda **Previsione**, che è il punto di
  arrivo del percorso ed era l'unica delle sette a non comparire mai. La
  descrizione del passo 4 non promette più «sei numeri», visto che può essere
  un sistema fino a dodici.
- Gli elenchi dei comandi in README e premessa includono `--import` e usano
  `--forecast ritardo`, che non richiede di scaricare 1,3 GB di pesi per
  vedere come funziona.

### Corretto

- **Il docstring di `main.py` consigliava `--forecast gap`**, un metodo che non
  esiste più dalla 0.2.0: eseguirlo esce con codice 2 e un errore. Ora dice
  `ritardo`, che è come si chiama.
- I conteggi dei test nella documentazione dicevano 187 dove la suite ne
  eseguiva 194. Erano incrementati a mano invece che misurati; ora sono quelli
  veri, e `CLAUDE.md` avverte che vanno misurati.

## [0.6.1] — 2026-09-06

Una combinazione sola, e il perché misurato.

### Cambiato

- **Il valore predefinito delle combinazioni passa da 5 a 1.** La seconda
  combinazione è la settima scelta del metodo al posto della sesta, la terza
  l'ottava, e così via: sono le preferenze che il metodo aveva scartato.
- Su 1.000 estrazioni reali le cinque combinazioni segnano lo stesso
  punteggio, perché un metodo che non sa niente non ha preferenze da
  rispettare. Contro un previsore a cui è stato dato un vantaggio vero, però,
  la prima segna 1,486 centri per estrazione e la quinta 0,304 — appena sopra
  il caso.
- **Quindi più di una combinazione non vale mai di più per euro speso, e se il
  metodo sapesse qualcosa varrebbe di meno.** La scheda Previsione lo dice
  adesso, invece di offrire cinque combinazioni senza spiegare cosa siano.
- Chi vuole comunque puntare più di una colonna trova la risposta meglio
  argomentata in un sistema, che resta in cima alla graduatoria invece di
  scendere lungo di essa.

## [0.6.0] — 2026-09-05

Quanto costa la giocata, e dove finiscono i soldi.

### Costo

- **La scheda Previsione stampa quanto costa la giocata che mostra**, e lo
  ripete sotto ai pulsanti insieme alla forma della giocata. Anche `--forecast`
  lo dice.
- I prezzi sono **due impostazioni** — un euro a colonna e cinquanta centesimi
  per il SuperStar — perché li decide il concessionario e non la matematica.
  Il SuperStar si aggiunge a *ogni* colonna, non una volta sola: su un sistema
  costa quanto il sistema moltiplicato per il suo prezzo.
- **Il conto mostra una cosa che non è ovvia.** Le combinazioni proposte
  scorrono di un posto lungo la graduatoria, quindi si sovrappongono: cinque
  sistemi da dodici numeri fanno pagare 4.620 colonne e ne coprono 2.772 di
  diverse. Il 40% della spesa va in colonne comprate due volte. Giocandone una
  sola non si spreca niente, e adesso il programma lo dice invece di stampare
  un totale che lo nasconde.

### Corretto

- **Il pannello delle Impostazioni non sapeva salvare un decimale.** Gestiva
  booleani e interi e per tutto il resto teneva il testo grezzo, quindi un
  prezzo scritto lì tornava come stringa e il primo calcolo su di esso sarebbe
  stato quello che sollevava l'errore. Ora accetta anche la virgola, che è
  quello che produce una tastiera italiana.

## [0.5.0] — 2026-09-05

Sistemi e SuperStar, con la matematica dichiarata.

### Sistemi

- **Nelle Impostazioni si sceglie quanti numeri per combinazione**, da sei a
  dodici. Sei è una colonna singola; di più è un sistema integrale, e la
  previsione produce sistemi invece di colonne.
- La scheda Previsione stampa quante colonne copre il sistema, quanto costa
  rispetto a una giocata singola e quali vincite minori accompagnerebbero
  quella grande — con dieci numeri e sei indovinati: un 6, ventiquattro 5 e
  novanta 4.
- **Dice anche la cosa che di solito non viene detta:** giocare più numeri
  accorcia le probabilità del 6 e moltiplica il costo esattamente dello stesso
  fattore. La probabilità per euro giocato non cambia. Un test verifica che
  quel rapporto resti costante a ogni dimensione, così nessuna modifica futura
  può far sembrare un sistema un affare migliore di quello che è.
- **La Validazione segue la dimensione scelta**: con nove numeri il caso vale
  0,600 centri per estrazione invece di 0,400, perché è un'altra scommessa.
  Misurarne sei mentre se ne giocano nove misurerebbe un gioco diverso da
  quello che si sta facendo.

### SuperStar

- **Si può giocare anche il SuperStar**, con un interruttore nelle
  Impostazioni. Era già letto, validato e archiviato da sempre, ma nessuna
  previsione lo usava.
- Viene scelto sulla storia della **sua** urna, non su quella dei sei: sono
  estrazioni separate e indipendenti, tanto che il SuperStar ripete uno dei sei
  247 volte sull'archivio reale, contro 223 attese. Indovinarlo è 1 su 90,
  qualunque numero si scelga.
- Contano solo le estrazioni che ne registrano uno. Il gioco è partito il 28
  marzo 2006 e le 914 precedenti salvano 0, che vuol dire «non a registro»:
  contarle avrebbe messo un picco su un numero mai uscito.

## [0.4.0] — 2026-09-05

Un percorso, invece di sei schede senza un ordine.

### La scheda Percorso

- **Il programma si apre su una mappa.** Quattro passi numerati — porta i
  dati, guarda se c'è qualcosa da prevedere, metti alla prova i metodi, genera
  le combinazioni — ognuno con la domanda a cui risponde, quello che ha
  prodotto finora e un pulsante che ci porta.
- Il problema non erano le spiegazioni, che c'erano: era che **nessuna scheda
  diceva l'ordine**. Sei schermate indipendenti, ognuna che descriveva sé
  stessa e nessuna che dicesse da dove si parte, che cosa dipende da che cosa
  e dove sia la previsione.
- I passi portano uno stato vivo: al primo avvio il passo 1 dice che l'archivio
  manca e gli altri tre che serve prima quello; dopo aver eseguito i test il
  passo 2 riassume l'esito; dopo la validazione il passo 3 dice se qualche
  metodo ha battuto il caso.
- La scheda non esegue niente per conto suo. Ogni passo apre il pannello che
  fa il lavoro: due posti per lanciare la stessa cosa richiederebbero una
  regola su chi vince, e non ce n'è una.

### Il resto dell'interfaccia

- **Ogni pannello dice a che passo si trova e che cosa viene dopo**, così chi
  ci arriva di lato non resta senza riferimenti. Statistiche e Impostazioni
  sono marcate «fuori percorso», perché lo sono.
- La Prova del nove non è stata retrocessa: è il passo 2 di 4 sulla strada per
  le combinazioni, che è un posto migliore di una scheda che si può non aprire
  mai.
- Corretto un difetto di impaginazione della nuova scheda che teneva il passo
  4 — la destinazione — sotto la piega: un frame con la propagazione
  disattivata resta alto 200 px, che è l'altezza predefinita di `CTkFrame`.

## [0.3.3] — 2026-09-05

Una sola release, tenuta dal workflow invece che a mano.

### Release

- **Il repository conserva ora esattamente una release: l'ultima.** Finita la
  pubblicazione, il workflow cancella le release precedenti e i loro tag. È
  quello che si stava facendo a mano dopo ogni pubblicazione.
- Il passo è l'ultimo dell'ultimo job e **non** gira in caso di errore: se
  qualcosa fallisce prima, resta in piedi la release vecchia invece di essere
  sostituita da una nuova rotta. Si rifiuta inoltre di cancellare alcunché se
  la release che sta tenendo non ha un archivio allegato — un caricamento
  fallito in silenzio costerebbe altrimenti tutte le versioni scaricabili in
  una volta sola.
- Cinque test tengono ferme quelle proprietà, e falliscono davvero: verificato
  spostando il passo prima del caricamento e aggiungendoci `if: always()`.
- Il `CHANGELOG.md` conserva la sezione di ogni versione, quindi la storia del
  progetto non dipende dalla sopravvivenza di quelle pagine.

## [0.3.2] — 2026-09-05

Le tabelle spiegate dove si leggono, e la riga di comando finalmente coperta.

### Interfaccia

- **Le note che spiegano le tabelle stanno ora sopra le tabelle** quando queste
  non ci stanno nel riquadro. La tabella delle frequenze è di novanta righe in
  uno spazio che ne mostra ventidue, quindi la nota che spiega il segno `<`
  usato su quelle righe era irraggiungibile senza scorrere oltre tutto ciò che
  descriveva. Stessa cosa per le venticinque coppie. La tabella delle decine,
  che di righe ne ha nove, tiene la sua nota sotto: lì ci arrivi, e si legge
  come una conclusione.
- **La tabella della validazione ha una legenda.** `vs caso`, `z`, `p`, `max`,
  `>=3`, `att.>=3` e `rango medio` non erano spiegati da nessuna parte: erano
  sette statistiche che ti si chiedeva di credere sulla parola, che è
  l'opposto di quello a cui serve quella scheda.
- **La colonna `σ` delle statistiche si chiama ora `z`.** Indica di quanti
  scarti tipo le uscite di un numero distano dall'attesa, e chiamarla con il
  simbolo dello scarto tipo invitava a leggerla come se lo fosse.

### Test

- **La riga di comando era il file meno coperto del progetto**, al 34%. Non era
  un problema teorico: la traduzione in italiano di 0.2.0 aveva lasciato la CI
  a cercare nell'uscita di `--check` un inglese che il programma non stampava
  più, e la build è andata rossa su un passo che non verificava più niente.
  Adesso è al 90% — tutte le modalità, la regola della prova a vuoto, il codice
  di uscita su un metodo sconosciuto, il file che non c'è.
- Coperti anche `core/paths.py`, che decide dove un pacchetto Windows scrive i
  dati dell'utente, e il percorso della sorgente in blocco che onora davvero
  l'interruttore sulla correzione delle etichette — il test precedente
  controllava un attributo, che non dimostra niente.
- La suite passa da 171 a 189 test e la copertura complessiva dall'84% al 90%.

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
