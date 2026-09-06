#!/bin/sh
# Avvia Tyche dopo aver verificato che l'eseguibile sia quello con cui questo
# archivio è stato costruito.
#
# Accanto all'eseguibile l'archivio porta un `Tyche.sha256`. Questo script
# ricalcola quell'impronta e la confronta. Quello che intercetta è un download
# troncato, uno scompattamento a metà, un disco che ha iniziato a marcire —
# danni, cioè il guasto che alle persone capita davvero.
#
# Quello che NON intercetta è la manomissione. L'impronta viaggia dentro lo
# stesso archivio del file che descrive, quindi chi potesse sostituire l'uno
# potrebbe sostituire l'altra nello stesso momento. La verifica che conta
# contro quello è sull'archivio, contro lo SHA-256 stampato nelle note di
# rilascio, che arriva per una strada diversa da quella dell'archivio.
#
# /bin/sh portabile di proposito: gira sulla build Linux e, rinominato
# start.command perché il Finder lo esegua con un doppio clic, su quella
# macOS. Il gemello per Windows è start.cmd, che fa le stesse due cose con
# certutil.
#
# A differenza di start.cmd questo non aspetta la finestra: su macOS e Linux
# il programma viene avviato da un terminale che resta lì, e `exec` gli lascia
# il processo invece di aggiungerne uno che sorveglia.

set -eu

APP="Tyche"

# La cartella in cui vive questo script, non quella da cui è stato invocato:
# un doppio clic da un gestore di file parte da tutt'altra parte.
#
# Ritagliata con l'espansione dei parametri invece che con dirname, e tutto il
# resto è scritto allo stesso modo: a parte lo strumento che calcola
# l'impronta, questo script non chiama nulla di esterno. Un lanciatore è
# l'ultima cosa che dovrebbe fallire perché l'ambiente che ha ereditato era
# insolito.
case "$0" in
    */*) dir=${0%/*} ;;
    *)   dir=. ;;
esac
here=$(CDPATH= cd -- "$dir" && pwd)

exe="$here/$APP"
sums="$here/$APP.sha256"

if [ -f "$exe" ] && [ ! -x "$exe" ]; then
    chmod +x "$exe" 2>/dev/null || true
fi

if [ ! -f "$exe" ]; then
    echo "$APP: nessun eseguibile in $exe" >&2
    echo "L'archivio non si è scompattato del tutto. Riprovare." >&2
    exit 1
fi

digest_of() {
    # Tre strumenti, perché nessuno singolo è su ogni sistema: sha256sum è
    # coreutils (Linux), shasum arriva con macOS, openssl di solito è su
    # entrambi. I primi due stampano "<hex>  <percorso>", quindi l'esadecimale
    # è tutto ciò che precede il primo spazio; openssl stampa
    # "SHA2-256(percorso)= <hex>", quindi è tutto ciò che segue l'ultimo.
    if command -v sha256sum > /dev/null 2>&1; then
        line=$(sha256sum "$1") && printf '%s\n' "${line%% *}"
    elif command -v shasum > /dev/null 2>&1; then
        line=$(shasum -a 256 "$1") && printf '%s\n' "${line%% *}"
    elif command -v openssl > /dev/null 2>&1; then
        line=$(openssl dgst -sha256 "$1") && printf '%s\n' "${line##* }"
    else
        return 1
    fi
}

# Una via d'uscita, esplicita di proposito. Chi ha modificato l'eseguibile
# apposta deve poterlo avviare; chi non l'ha fatto non deve mai vedere questa
# strada presa in silenzio.
if [ "${TYCHE_SKIP_VERIFY:-}" = "1" ]; then
    echo "$APP: verifica dell'impronta saltata (TYCHE_SKIP_VERIFY=1)" >&2
elif [ ! -f "$sums" ]; then
    echo "$APP: manca $APP.sha256, avvio senza verifica" >&2
elif ! actual=$(digest_of "$exe"); then
    echo "$APP: nessuno strumento sha256 disponibile, avvio senza verifica" >&2
else
    # Il file è nel formato che legge sha256sum -c: "<hex>  <percorso>".
    # `read` segnala EOF su un file senza newline finale, ma a quel punto ha
    # già assegnato: si ignora il suo stato e si controlla il vuoto.
    expected=""
    read -r expected _ < "$sums" || :
    if [ -z "$expected" ]; then
        echo "$APP: $APP.sha256 non contiene nulla, avvio senza verifica" >&2
    elif [ "$actual" != "$expected" ]; then
        echo "$APP: l'eseguibile non corrisponde a $APP.sha256." >&2
        echo "  atteso  $expected" >&2
        echo "  trovato $actual" >&2
        echo "" >&2
        echo "Riscompattare l'archivio da un download nuovo. Se ancora non" >&2
        echo "corrisponde, controllare lo SHA-256 dell'archivio riportato" >&2
        echo "nelle note di rilascio prima di avviare qualsiasi cosa." >&2
        exit 1
    fi
fi

exec "$exe" "$@"
