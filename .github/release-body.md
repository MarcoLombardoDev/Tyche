**Tyche — analisi dell'archivio SuperEnalotto e previsioni con TimesFM 3.0.**

Un'applicazione desktop che scarica lo storico completo delle estrazioni del
SuperEnalotto dal dicembre 1997, lo esamina in cerca di struttura sfruttabile,
lo consegna a TimesFM 3.0 — il modello fondazionale per serie temporali di
Google — e misura onestamente quanto valgano le previsioni che ne escono.

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
python main.py --check                # i cinque test di indipendenza
python main.py --validate 500         # backtest walk-forward
python main.py --forecast timesfm     # sei numeri
python main.py --export-sqlite data/tyche.db
```

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

## Licenza

Privato, tutti i diritti riservati. Il pacchetto `timesfm` è Apache-2.0; i
**pesi** `google/timesfm-3.0-pytorch` che scarica sono coperti da
`timesfm-non-commercial-license-v1.0` e sono limitati a un uso non commerciale e
non di produzione.
