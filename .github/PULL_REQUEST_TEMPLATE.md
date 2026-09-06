## Descrizione

<!-- Che cosa cambia, e perché. Se corregge un errore, descrivi il sintomo che hai osservato. -->

## Tipo di modifica

- [ ] Correzione di un errore
- [ ] Funzionalità nuova
- [ ] Miglioramento (prestazioni, leggibilità, interfaccia)
- [ ] Solo documentazione

## Verifiche

- [ ] `TYCHE_REQUIRE_GUI=1 xvfb-run -a python -m pytest tests/ -q` passa
- [ ] `ruff check .` passa
- [ ] Una correzione arriva con un test che fallisce senza la modifica
- [ ] `CHANGELOG.md` aggiornato sotto *Unreleased*
- [ ] Documentazione aggiornata se il comportamento è cambiato
- [ ] Se hai toccato la build o le dipendenze: `python build.py` eseguito, e il
      pacchetto che ha prodotto avviato con `--self-check`

<!--
Nessun CLA da firmare: Tyche è AGPL-3.0-or-later e basta, quindi una
contribuzione si offre sotto la stessa licenza, che è quello che l'AGPL
prevede di suo. Non c'è una licenza commerciale in cui rilicenziarla.
-->

## Note per chi rivede

<!-- Che cosa guardare, alternative considerate, limiti noti. -->
