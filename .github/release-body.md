**Tyche — analisi dell'archivio SuperEnalotto e previsioni con TimesFM 3.0.**

Un'applicazione desktop che scarica lo storico completo delle estrazioni del
SuperEnalotto dal dicembre 1997, lo esamina in cerca di struttura sfruttabile,
mette alla prova ogni metodo di previsione sulle estrazioni già avvenute e poi
genera delle combinazioni, dicendo quanto valgono e quanto costano.

La versione breve di quella misura: **niente**. Le estrazioni sono
indipendenti, i test lo dicono, e ogni metodo del programma segna 0,4 numeri
indovinati su sei, che è esattamente il caso. Tyche è costruito per dimostrarlo
con cura anziché per affermarlo, ed è per questo che la linea di base casuale
sta nello stesso menu del modello da 330 milioni di parametri, alla stessa
dimensione.

⚠️ **Questo programma non può aiutarti a vincere.** Non ha alcun potere
predittivo e non pretende di averne. Le probabilità che stampa sono esatte e
immutabili: 1 su 622.614.630 per sei numeri, 1 su 327 per tre. I premi sono a
totalizzatore, quindi il concessionario trattiene una quota fissa di ogni euro
giocato e il rendimento atteso di una schedina è inferiore al suo prezzo
qualunque cosa si giochi.

## Un percorso in quattro passi

Il programma si apre su una mappa, non su un pannello. Ogni passo porta la
domanda a cui risponde e quello che ha prodotto finora, e apre la scheda che
fa il lavoro.

| | Passo | La domanda |
|---|---|---|
| 1 | **Archivio** | Ci sono i dati? Scarica, importa e ispeziona lo storico, e dice che cosa non va. |
| 2 | **Prova del nove** | C'è qualcosa da prevedere? Cinque test dell'ipotesi che le estrazioni siano indipendenti e uniformi. |
| 3 | **Validazione** | I metodi battono il caso? Backtest walk-forward, senza che nessuno possa sbirciare il futuro. |
| 4 | **Previsione** | Il punto di arrivo: i numeri, con accanto quello che i passi precedenti hanno stabilito che valgono. |

L'ordine è l'argomento del programma: si arriva alle combinazioni *attraverso*
le prove, non saltandole.

## Quanto vale la prova, e quanto costa la giocata

**La validazione dichiara la propria sensibilità.** «Non abbiamo trovato
niente» e «non avremmo potuto trovarlo» producono lo stesso tabellone, quindi
il pulsante *Calibra* rifà la stessa prova contro previsori il cui vantaggio è
noto, e riporta quale vantaggio si sarebbe accorta di vedere.

**Sistemi e SuperStar.** Si sceglie quanti numeri per combinazione, da sei a
dodici, e se giocare anche il SuperStar. La Validazione segue la dimensione
scelta. Un sistema accorcia le probabilità del 6 e moltiplica il costo dello
stesso identico fattore — la probabilità per euro non si muove — e il
programma lo dice invece di lasciarlo intendere.

**Il costo è calcolato**, ai prezzi che si impostano, e mostra dove finiscono
i soldi: le combinazioni proposte si sovrappongono, quindi giocandone cinque
da dodici numeri il 40% della spesa compra colonne già comprate. Il valore
predefinito è una combinazione sola, perché la seconda è la settima scelta del
metodo al posto della sesta.

## Eseguirlo dai sorgenti

Sotto è allegato un pacchetto per Windows; su tutto il resto si esegue dai
sorgenti.

```
git clone https://github.com/MarcoLombardoDev/Tyche.git
cd Tyche
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
python main.py
```

Su Debian o Ubuntu `tkinter` è un pacchetto di sistema a parte e deve
corrispondere all'interprete con cui si esegue Tyche: `sudo apt install
python3-tk`.

La prima previsione con TimesFM scarica circa 1,3 GB di pesi da Hugging Face.
Tutto il resto — l'archivio, i test di indipendenza, le statistiche, le linee di
base e l'intera validazione — funziona senza.

C'è una riga di comando per le parti che vale la pena automatizzare:

```
python main.py --update --yes         # aggiorna l'archivio
python main.py --import FILE --yes    # importa un file scaricato a mano
python main.py --check                # i cinque test di indipendenza
python main.py --validate 500         # backtest walk-forward
python main.py --power                # sensibilita' della validazione
python main.py --forecast ritardo     # una giocata, senza scaricare il modello
python main.py --export-sqlite data/tyche.db
```

`--update` e `--import` mostrano che cosa cambierebbero e non scrivono nulla
senza `--yes`.

## Che cosa è stato verificato prima di pubblicare

Sul commit taggato, prima che la release fosse creata:

- `ruff check .` su tutto il repository;
- l'intera suite di test con `TYCHE_REQUIRE_GUI=1` sotto Xvfb, così
  l'interfaccia viene davvero esercitata invece di essere saltata;
- un controllo che la versione dichiarata dal programma coincida con il tag di
  questa pagina.

E sul pacchetto Windows, prima che venisse allegato:

- avvia Tk per davvero e si presenta sul backend `win32`, costruisce le matrici
  delle caratteristiche, esegue i cinque test di indipendenza e fa un giro
  completo di scrittura e rilettura di un archivio con il proprio codice di
  persistenza — questo è `--self-check`, e `--version` da solo non dimostrerebbe
  niente di tutto ciò;
- TimesFM è davvero dentro il pacchetto, non silenziosamente perduto;
- l'avviatore fa partire il programma, e si rifiuta di farlo quando l'impronta
  registrata non corrisponde.

Questa pagina è l'unica release pubblicata: finita la build, il workflow
cancella la precedente e il suo tag. `CHANGELOG.md` nel repository conserva la
storia di ogni versione.

## Licenza

**AGPL-3.0-or-later.** Puoi usarlo, studiarlo, modificarlo e ridistribuirlo;
se lo distribuisci o lo esponi come servizio devi consegnare il sorgente alle
stesse condizioni. Nessuna licenza commerciale, nessun CLA.

I **pesi del modello sono un'altra cosa dal codice.** Il pacchetto `timesfm` è
Apache-2.0; i pesi `google/timesfm-3.0-pytorch` che il programma scarica al
primo uso dichiarano `timesfm-non-commercial-license-v1.0` — uso non
commerciale e non di produzione. Quel permesso non è di Tyche da concedere, e
`THIRD-PARTY-LICENSES.md` lo spiega per esteso. Tutto il resto del programma
funziona senza scaricare alcun peso.
