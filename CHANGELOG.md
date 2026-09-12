# Registro delle modifiche

Le modifiche degne di nota, versione per versione. La sezione di una versione è
ciò che compare sulla pagina della release: `tools/release_notes.py` la legge da
questo file e la compone con la premessa fissa di `.github/release-body.md`, così
le note e questo file non possono divergere.

Il formato segue [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) e la
numerazione il [versionamento semantico](https://semver.org/spec/v2.0.0.html).

## [Non rilasciato]

Niente, per ora.

## [1.0.3] — 2026-09-12

I pesi scaricati a mano adesso si possono usare.

L'utente ha fatto la cosa giusta: dopo l'ennesimo download interrotto ha preso
il file dal browser, l'ha messo in una cartella insieme agli altri — e Tyche
continuava a dire che i pesi non c'erano. Aveva ragione lui: non c'era alcun
modo di dirglielo.

### Aggiunto

- **Impostazioni → «Cartella dei pesi TimesFM»**, con il pulsante «Sfoglia…».
  Indica una cartella e Tyche carica da lì: niente download, nessuna rete, né
  al primo avvio né dopo. È la via d'uscita quando il download non arriva in
  fondo, e adesso il passo 2 del Percorso la nomina.

- **Servono due file, non cinque, e non è una stima.** `config.json` e
  `model.safetensors`, presi dalla scheda «Files» della pagina del modello su
  Hugging Face. È quello che il codice legge davvero: `timesfm3` passa una
  cartella a `PyTorchModelHubMixin.from_pretrained`, che apre quei due nomi e
  nessun altro. Il `config.json` non è facoltativo — costruisce il modello che
  i pesi poi riempiono — e una cartella che contiene solo il file da 1,23 GB
  viene segnalata come incompleta, per nome, invece di fallire al caricamento.

- **La cartella sbagliata lo dice.** Se non esiste, se non è una cartella o se
  manca uno dei due file, la schermata iniziale scrive quale manca e dove lo
  stava cercando. E lo dice **anche quando il download aveva funzionato**:
  altrimenti l'impostazione verrebbe ignorata in silenzio.

### Corretto

- **Il modello viene caricato dal disco, non dal nome del repository.** Finora
  Tyche passava `google/timesfm-3.0-pytorch` a TimesFM anche con i pesi già in
  cache, e a quel punto la libreria tornava comunque su Hugging Face a
  risolvere la revisione. Adesso, quando i pesi sono su questa macchina, quello
  che viene passato è la loro cartella: il caricamento non apre più una
  connessione, che è ciò che «dopo il download non c'è più rete» ha sempre
  promesso.

- **Le spiegazioni sotto i campi delle Impostazioni uscivano dal riquadro.**
  Rientrano di 200 pixel ma si misuravano sull'intera larghezza, quindi ogni
  riga andava a capo 200 pixel troppo tardi e l'ultima parte finiva fuori dal
  bordo destro. Si vedeva nella schermata e in nessun test.

- **Una cache che huggingface_hub non riconosce viene letta lo stesso.** Una
  cartella riempita a mano, o una cui si sono persi i `refs`, contiene i pesi e
  risponde «non c'è niente» alla domanda della libreria. La libreria resta la
  prima a essere interrogata; se declina, adesso la cartella viene guardata
  direttamente — e mai la radice della cache, che appartiene anche agli altri
  modelli.

## [1.0.2] — 2026-09-08 — `cb22b04`

Il download si interrompeva, e nessuno lo diceva.

La diagnosi ha risposto a tutte e tre le domande in una volta, e nessuna delle
risposte era quella che pensavamo.

### Corretto

- **Il download si fermava al 72% e il programma non se ne accorgeva.** Sul
  computer dell'utente la cache conteneva 882 MB del `model.safetensors` da
  1,23 GB: la chiamata tornava, il pannello proseguiva, e la schermata dopo
  diceva «pesi assenti» senza un accenno al fatto che tre quarti erano già lì.
  Ora quello che è arrivato viene confrontato con quello che l'Hub dice che il
  repository pesa, e il download **riprende** — huggingface_hub continua da
  ciò che trova, quindi un secondo tentativo costa il resto e non tutto. Se
  rinuncia, dice a quanto è arrivato e che ripremere riprende; e anche il
  passo 2 del Percorso adesso scrive «si è fermato a 882 MB di 1,23 GB»
  invece di «non ancora scaricati».
- **Non si vedeva alcun avanzamento perché non ce n'era.** La percentuale era
  costruita agganciando `tqdm_class` di huggingface_hub — parametro
  documentato, aritmetica coperta da dieci test — e su quella macchina la
  barra di stato è rimasta ferma su «TimesFM…» per tutto il download. Che
  hf_hub rispetti quell'aggancio era un'affermazione sulla libreria di
  qualcun altro, e nessun test qui poteva verificarla.

  Adesso i byte si contano **sul disco**, nella cartella di cache del
  repository. Un download ripreso parte dal 72% perché è lì che è, il
  denominatore viene chiesto all'Hub una volta sola e quindi non si muove, e
  la percentuale non può più scendere.

### Chiarito

- **I «migliaia di file» non sono di questo repository.** L'Hub dice che
  `google/timesfm-3.0-pytorch` sono **cinque file, 1,23 GB**:
  `model.safetensors`, la licenza, il README, `.gitattributes` e
  `config.json`. L'esclusione dei formati introdotta nella 1.0.1 qui non
  corrisponde a niente, e infatti non ha cambiato né il numero né la
  dimensione. Resta perché il checkpoint è un'impostazione e un altro
  repository può davvero portare quattro formati — ma qui non c'era niente da
  snellire, e dirlo è più utile che vantare un risparmio che non c'è stato.

## [1.0.1] — 2026-09-08 — `d82aaff`

Scoprire perché TimesFM non parte, e scaricare meno roba.

### Aggiunto

- **Un pulsante «Diagnosi» al passo 2 del Percorso, e `--model-check` da riga
  di comando.** Dice quello che serve per capire perché il modello non parte e
  che finora nessuno dei due poteva sapere: quale Python sta girando, se
  `timesfm3`, `huggingface_hub` e `torch` sono importabili e in che versione,
  dov'è la cache e che cosa contiene, quanti file di pesi ci sono e quanto
  sono grandi, quanto spazio libero c'è sul disco, e che cosa risponde l'Hub
  quando gli si chiede del checkpoint. Scrive tutto in
  `data/diagnosi-timesfm.txt`.

  Il pulsante c'è perché il pacchetto Windows non ha una console: lì
  `--model-check` è irraggiungibile, e un rapporto che si può ottenere solo
  dalla riga di comando su una macchina che non ce l'ha non è un rapporto.

- **Uno step della CI che elenca il contenuto del repository dei pesi** con le
  dimensioni, e quanto risparmia l'esclusione. Era una domanda a cui da qui
  non si poteva rispondere — huggingface.co risponde 403 attraverso il proxy
  di questo ambiente — e adesso la risposta è stampata invece che supposta.

### Modificato

- **Il download salta i formati che PyTorch non legge**: TensorFlow (`.h5`),
  Flax (`.msgpack`), ONNX, TFLite e le immagini. Un repository di modelli
  porta gli stessi pesi in più formati perché ogni framework trovi il suo, e
  prenderli tutti è come «1,3 GB» diventa parecchio più di 1,3 GB.

  **Ed è un'esclusione, non una lista di cose da prendere**, di proposito: una
  lista che dimentica un file che al caricatore serve produce un download che
  sembra completo e fallisce alla prima previsione. Se l'esclusione dovesse
  comunque portare via tutti i pesi, il download viene rifatto per intero:
  è quello che rende sicuro l'aver tirato a indovinare.

- **L'aiuto del campo Token dice come ottenerlo**, in due righe, e ripete che
  per il checkpoint predefinito non serve.

### Corretto

- **`.msgpack` era contemporaneamente un formato di pesi accettato e uno
  escluso dal download.** L'ha trovato un test nuovo. Contare come prova che
  il download è riuscito un formato che il download salta di proposito è il
  genere di contraddizione che finisce in una cache che il programma dichiara
  pronta per sempre e non riesce a caricare.

## [1.0.0] — 2026-09-08 — `bc7cf6f`

La prima versione che si legge senza spiegazioni.

Il numero non promette funzioni nuove: dice che l'interfaccia ha smesso di
cambiare forma a ogni giro. Quattro schede, un percorso di tre passi, una
previsione che mostra tutti e quattro i metodi affiancati, e un archivio che
contiene anche le sue statistiche.

### Modificato

- **Una sola dimensione per tutti i testi**, con due eccezioni: i pulsanti,
  che se la dà CustomTkinter, e i titoli, che sono in grassetto. Prima sullo
  stesso schermo convivevano 11, 12, 13 e il valore predefinito del toolkit —
  perché un'etichetta senza `font=` lo prende in silenzio — e il risultato si
  leggeva come quattro tipi di testo che dicono la stessa cosa.
- **Nella Previsione il pulsante per scaricare il modello non c'è più**: ce
  n'è già uno al passo 2 del Percorso, e due pulsanti per un download sono due
  posti dove cercarlo. Resta lo stato di TimesFM, che ha preso il posto della
  frase sulle combinazioni: se il quarto metodo può girare o no vale più di
  quello spazio.
- **La riga «Archivio: …» sopra i quattro riquadri è confluita nel riquadro
  finale.** Quello che i quattro hanno in comune si dice in un posto solo, e
  ora è sotto, dove c'è già il costo.
- **Il riquadro finale usa tutta la larghezza della finestra.** Prima il testo
  veniva piegato a una colonna decisa in anticipo; adesso va a capo sulle
  parole, dove finisce la finestra.

## [0.11.0] — 2026-09-08 — `0610144`

Una scheda in meno, due colonne in più, e il motivo per cui TimesFM non partiva.

### Corretto

- **«TimesFM è pronto» nel Percorso e «non si è caricato» nella Previsione,
  senza una parola sul perché.** Due difetti sovrapposti, entrambi risolti.
  Il motivo del fallimento finiva nella barra di stato e il messaggio
  successivo lo cancellava: ora il forecaster se lo tiene e il riquadro di
  TimesFM lo stampa, con il nome dell'eccezione. E il controllo della cache
  diceva «pronto» anche su uno scaricamento interrotto — offline
  `snapshot_download` confronta solo con l'elenco di file che ha già, quindi
  una cartella con la configurazione e senza pesi passava. Adesso deve
  contenere almeno un file di pesi.
- **La barra di stato e la riga del copyright mancavano in Archivio e
  Previsione.** Erano impacchettate dopo il corpo della finestra, che si
  espande, e `pack` taglia via quello che viene dopo: sparivano esattamente
  sulle due schede con più contenuto. Ora sono le prime a essere riservate e
  ci sono su tutte.
- **La riga del copyright aveva il colore di un filetto di separazione** e non
  si leggeva. Ora è quello del testo secondario, un punto più grande.
- **I testi andavano a capo a metà finestra.** Ogni pannello portava una
  larghezza fissa scritta a mano — 760, 780, 1000, 1080 — quindi su uno
  schermo grande la prosa si fermava a metà riga. Ora si adatta alla finestra.
- **Il messaggio durante il caricamento dice che cosa sta aspettando**: i pesi
  sono già su disco, non c'è niente da scaricare e nessuna percentuale da
  mostrare — quello che impiega tempo è torch che legge 1,3 GB dal disco.

### Modificato

- **La scheda Statistiche non c'è più: è la colonna destra dell'Archivio.**
  A sinistra che cosa non va nell'archivio e le ultime estrazioni, a destra
  l'archivio in cifre con le tre tabelle. Sono metà della stessa domanda, e
  come scheda separata era un posto dove si andava una volta sola.
- **I quattro riquadri della Previsione sono alti il doppio e hanno un bordo
  viola.** A 120 pixel mostravano tre righe di tabella e la pagina si leggeva
  come rumore. Sono più alti della finestra, quindi la griglia scorre.
- **Tolto «— che valgono esattamente quanto lui»** dal passo 2 del Percorso.

### Rimosso

- **I pulsanti «Mirror storico» e «Scansiona le pagine».** Il mirror si ferma
  a gennaio 2020 e non è d'accordo con estrazioni.it su dodici estrazioni; la
  scansione non ha mai letto una pagina vera e i suoi indirizzi sono
  congetture. Stavano accanto a un pulsante che scarica l'archivio giusto in
  una richiesta, il che li rendeva trappole più che alternative. Restano come
  ripieghi dentro `--update`, dove nessuno deve sceglierli.
- **Con loro se ne vanno due impostazioni**, `bulk_archive_url` e
  `html_archive_url`, e la casella «salva le pagine scaricate».

## [0.10.0] — 2026-09-08 — `a4f5f16`

Meno schede, e i quattro metodi tutti insieme.

### Rimosso

- **Le schede «Prova del nove» e «Validazione» non ci sono più.** Erano
  incomprensibili a chi usa il programma, ed è un difetto della scheda, non
  della misura: cinque test di indipendenza e un backtest walk-forward sono
  la cosa giusta da fare e la cosa sbagliata da mettere davanti a chi voleva
  una giocata.
- **La misura però è rimasta, fuori dalla finestra.** `python main.py
  --validate` fa ancora il backtest di ogni metodo contro il caso e
  `--power` ne misura la sensibilità. Le tabelle del README si rifanno da lì.
- **Tre impostazioni sparite perché non le legge più nessuno**:
  `prediction_method`, `validation_draws`, `validation_baselines`. Un vecchio
  `settings.json` che le contiene continua a funzionare — vengono
  semplicemente ignorate.

### Modificato

- **Nella Previsione non si sceglie più il metodo: girano tutti e quattro e
  ognuno prende un quarto della pagina**, con le sue combinazioni e i suoi
  punteggi. Scegliere significava vederne uno, e vederne uno solo trasforma
  quattro misure in una preferenza: prendi quello di cui ti fidi, ottieni i
  suoi numeri, e non scopri mai che gli altri tre — generatore casuale
  compreso — producono una schedina altrettanto convincente e che vale
  esattamente lo stesso. Affiancati, si vede senza bisogno di un avviso.
- **Quello che i quattro hanno in comune è scritto una volta sola**: forma
  della giocata, costo e probabilità stanno sopra e sotto la griglia, non
  ripetuti quattro volte. E il costo dice esplicitamente di essere quello di
  **una** delle quattro proposte, che sono alternative e non una giocata da
  moltiplicare per quattro.
- **Il Percorso ha tre passi invece di quattro**, e sono condizioni anziché
  domande: archivio aggiornato, modello scaricato, previsione. Il passo 2 è
  l'unico che agisce invece di aprire una scheda — il download dei pesi non
  appartiene a nessuna scheda — e il pulsante si spegne quando non c'è niente
  da scaricare.
- **`--forecast` non è cambiato.** Dalla riga di comando il metodo si sceglie
  ancora, perché lì il metodo è l'argomento del comando.

## [0.9.1] — 2026-09-08 — `9293f24`

Ripubblicare una versione già rilasciata non funzionava.

### Corretto

- **Cancellare un tag e ricrearlo faceva fallire la release**, con
  «CHANGELOG.md has no section for 0.9.0» su un changelog che quella sezione
  ce l'aveva. Il difetto è che **il workflow scriveva un'intestazione che il
  suo stesso lettore non sapeva rileggere**: dopo aver pubblicato, registra
  nell'intestazione della versione il commit da cui gli archivi sono stati
  costruiti — `## [0.9.0] — 2026-09-07 — ⟨commit⟩` — e l'espressione regolare
  di `tools/release_notes.py` ammetteva la data e nient'altro dopo di essa.
  Alla prima pubblicazione non si vede, perché la lettura avviene prima della
  riscrittura; si vede alla seconda.

  È costato la 0.9.0: la sua pagina è rimasta senza note e senza archivi. Chi
  scrive un file deve saperlo rileggere, e ora tre test lo verificano —
  compreso uno che confronta la forma attesa con quella che il workflow
  compone davvero, perché un test che si inventasse la propria ortografia
  passerebbe mentre la release continua a fallire.

  La data non può più iniziare con un backtick, così un'intestazione che porta
  il commit e non la data non spaccia il commit per una data.

## [0.9.0] — 2026-09-07 — `f1cec1f`

TimesFM dice se può funzionare prima che tu glielo chieda.

### Corretto

- **Premere «Esegui» con TimesFM spuntato e i pesi non scaricati dava un
  errore generico.** Un download da 1,3 GB che non è ancora avvenuto non è un
  errore: è un fatto sulla macchina, che si può sapere *prima* di avviare
  qualsiasi cosa. Ora Validazione e Previsione lo chiedono mentre si
  disegnano, e dicono quale dei tre casi è — TimesFM non installato in questa
  copia, pesi non ancora scaricati, oppure pronto.
- **Finché i pesi non ci sono, TimesFM non è selezionabile.** La casella in
  Validazione è disattivata e non spuntata; in Previsione il metodo non
  compare nel menu, perché un menu a tendina non ha uno stato disattivato per
  singola voce. Lo stato viene riletto a ogni cambio di scheda, quindi un
  download avviato da un pannello sblocca anche l'altro.
- **Il download ha una percentuale.** Compare nella barra di stato in basso,
  al posto del vecchio «Carico google/…» che restava fermo per minuti. Accanto
  alla percentuale c'è sempre il totale — `546 MB di 1,29 GB (42%) — 2 file su
  5` — perché huggingface_hub crea una barra per file man mano che ci arriva:
  il denominatore cresce durante il download e senza averlo sotto gli occhi
  una percentuale che scende sembra un difetto.

### Modificato

- **«TimesFM», non «timesfm», ovunque un utente legga.** L'identificativo non
  si tocca — è quello che `settings.json` salva e che `--forecast` accetta, e
  rinominarlo romperebbe entrambi — ma le caselle, il menu dei metodi, le
  tabelle dei risultati e il verdetto ora usano i nomi come li scrive il resto
  dell'applicazione: TimesFM, Frequenza, Ritardo, Casuale.
- **La riga sul costo di TimesFM in Validazione dice di che costo si tratta.**
  Diceva «costa una chiamata al modello per estrazione — parti basso», che
  lasciava intendere un consumo esterno. Il modello gira in locale: dopo il
  download non c'è più rete, e la spesa è tempo di CPU sulla macchina di chi
  usa il programma.
- **Il titolo è `Tyche — Analisi e previsione SuperEnalotto`**, ovunque: la
  prima riga del README, la barra della finestra, l'intestazione della pagina
  di rilascio e la sottoscritta nella barra in alto. Prima il README apriva con
  un `# Tyche` scarno e la frase stava sotto, da sola, e quella frase nominava
  TimesFM — che è uno dei quattro metodi, quello che tutto il resto del README
  esiste per ridimensionare. Il README ora apre come gli altri cinque prodotti:
  icona, `Nome — payoff`, poi i badge.

### Aggiunto

- **`core/model_store.py`** — sa se TimesFM può girare, e scarica i pesi. Non
  importa né torch né timesfm: risponde da `importlib.util.find_spec` e dalla
  cache di Hugging Face, così un pannello può chiederglielo mentre si disegna.
  Importare il modello per sapere se il modello è importabile costa qualche
  secondo e, la prima volta, un gigabyte.
- **Un chiarimento che era una convinzione sbagliata**: per il checkpoint
  predefinito **non serve alcun token Hugging Face**, né un account. Le tre
  model card sono state interrogate dal job `checkpoint-licence` e nessuna è
  ad accesso ristretto. Il messaggio di errore nomina il token solo su un
  rifiuto di autorizzazione, mai su un problema di rete: dire «serve un token»
  a ogni intoppo manda l'utente ad aprire un account per niente.
- **`it_bytes`** in `core/localise.py`, con la virgola decimale italiana e le
  potenze di 1024.
- **Uno step della CI che misura il download vero.** L'aritmetica della
  percentuale è coperta da test unitari su una macchina senza torch e senza
  huggingface_hub; quello che lì non si può provare è se hf_hub rispetti
  `tqdm_class`. Il job `forecast` ora scarica il checkpoint attraverso
  `core/model_store.py`, stampa ogni riga di avanzamento e l'elenco dei file
  ottenuti, e fallisce se l'ultima percentuale non è 100%.
- **La release registra da quale commit è stata costruita**, nell'intestazione
  della propria sezione del changelog. È quello che la cancellazione del tag
  distruggerebbe: chi ha scaricato un archivio ormai superato lo tiene molto
  dopo che la pagina della release è sparita, il commit resta nella storia di
  `main`, ma senza il tag niente dice *quale*. Il passo gira **prima** della
  cancellazione, così se fallisce la release precedente resta in piedi invece
  di sparire portandosi via il riferimento.

## [0.8.0] — 2026-09-07

Allineamento alle convenzioni degli altri cinque prodotti della famiglia.

### Aggiunto

- **La barra della licenza in fondo alla finestra**, la stessa che portano
  gli altri prodotti: `© 2026 Marco Lombardo — Tyche | Distribuito con licenza
  AGPL-3.0 | Contatti:` e l'indirizzo, cliccabile, che apre il client di
  posta. Tyche non ne aveva nessuna. In italiano, a differenza degli altri:
  Tyche fa previsioni su un concorso che esiste solo in Italia, quindi chi lo
  usa legge italiano. `AGPL-3.0` resta com'è, perché un identificatore non è
  una frase da tradurre.

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

  Sul runner Windows Tk non è affidabile: il Python di `actions/setup-python`
  importa `tkinter` e poi non riesce a leggere la propria libreria Tcl — due
  run di fila su due file diversi, `tcl8.6/init.tcl` e la libreria di icone di
  `tk8.6/tk.tcl`. È un difetto dell'immagine, non di Tyche. Lì l'interfaccia
  non viene pretesa e il job lo dichiara nel log; a testarla è la gamba Linux,
  sotto un server X vero. La gamba Windows resta per quello che verifica
  davvero, e che prima non verificava nessuno: percorsi, codifiche e fine
  riga sulla piattaforma da cui viene la maggior parte dei download.

### Corretto

- `core/localise.py` apriva con la riga di prodotto **in italiano** —
  `APP_TITLE`, che è testo per l'utente — mentre gli altri quarantasette file
  portavano quella inglese. Il guard sull'intestazione controllava solo che la
  riga cominciasse per `# Tyche`, quindi non se ne accorgeva: adesso confronta
  i file fra loro e pretende che la riga sia la stessa ovunque.

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
