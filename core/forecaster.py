# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# Private project. All rights reserved; see LICENSE.
# Distributed WITHOUT ANY WARRANTY.

"""
forecaster.py — Tyche

Wraps TimesFM 3.0 and turns its output into one score per number.

What this module actually does, stated plainly, because the rest of the
program depends on nobody being confused about it: it hands a 330-million
parameter time-series foundation model ninety series derived from past draws,
asks for the next value of each, and ranks the ninety numbers by the answer.
It is a competent implementation of a question that has no answer. Lottery
draws are independent, :mod:`core.randomness` demonstrates that on this
archive, and :mod:`core.validation` measures what the ranking is worth against
chance — which is nothing, reliably, to three decimal places.

That is not a reason to build it badly. A wrong implementation would produce
the same worthless numbers while leaving open the excuse that a better one
might have worked.

**Use the Evaluator, not the Forecaster.** ``TimesFM3Forecaster`` is the
natural-looking entry point and the wrong one here. TimesFM 3.0 attends over
at most 32 variates in a single forward pass (``_MAX_VARIATES_PER_FORWARD`` in
``timesfm3/evaluator.py``); ``TimesFM3Evaluator`` is the subclass that splits a
wider input into chunks and reassembles the result. Ninety numbers means three
chunks — 1–32, 33–64, 65–90, the last padded by repetition and trimmed — so
the model sees cross-number structure *within* each block of 32 and not
across them. Tyche's context is therefore not quite the single joint context
the multivariate story suggests, and anyone reading "TimesFM 3.0 does
multivariate, so all ninety numbers are modelled together" should know it is
three groups of thirty-two. Since there is no cross-number structure to find,
this costs nothing measurable; it would matter on a real problem.

The model is loaded lazily and on a worker thread. The checkpoint is roughly
1.3 GB and the first call downloads it from Hugging Face; doing that on the
GUI thread would look like a hang.
"""

from __future__ import annotations

import numpy as np

from core.archive import ALL_NUMBERS, NUMBER_MAX, Draw
from core.features import DEFAULT_WINDOW, build_context
from core.version import DEFAULT_TIMESFM_CHECKPOINT

# TimesFM 3.0's own limit, restated so the reason for the chunking is visible
# from this file. Do not raise it: it is the model's, not a policy.
MAX_VARIATES_PER_FORWARD = 32

# Below this many draws a context is too short for the rolling-frequency
# window to have stabilised, and the forecast is dominated by the warm-up.
MIN_CONTEXT_DRAWS = 200


class ForecasterUnavailable(RuntimeError):
    """TimesFM is not installed, or the checkpoint could not be loaded."""


class TimesFMForecaster:
    """Scores the ninety numbers for the next draw with TimesFM 3.0."""

    def __init__(
        self,
        checkpoint: str = DEFAULT_TIMESFM_CHECKPOINT,
        device: str = "cpu",
        context_length: int = 1024,
        representation: str = "frequenza",
        window: int = DEFAULT_WINDOW,
        hf_token: str = "",
    ):
        self.checkpoint = checkpoint
        self.device = device
        self.context_length = context_length
        self.representation = representation
        self.window = window
        self.hf_token = hf_token
        self._model = None

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def load_model(self, progress=None) -> bool:
        """Download and instantiate the checkpoint. Safe to call repeatedly.

        Returns True on success and False on failure, rather than raising,
        because the caller is a GUI worker thread whose job is to put a
        message on screen either way. :meth:`score_numbers` is the one that
        raises, since by then a caller has already been told.
        """
        if self._model is not None:
            return True
        _report(progress, "Importo timesfm…", 0.05)
        try:
            from timesfm3 import ModelConfig, TimesFM3Evaluator
        except ImportError as exc:
            _report(progress, f"timesfm non è installato: {exc}", 0.0)
            return False

        _report(
            progress,
            f"Carico {self.checkpoint} (la prima volta scarica circa 1,3 GB)…",
            0.2,
        )
        try:
            config = ModelConfig(
                checkpoint_path=self.checkpoint,
                device=self.device,
                # One forward pass per chunk of 32 variates, three chunks for
                # ninety numbers, so a batch size of 4 already covers a whole
                # forecast with room to spare.
                per_core_batch_size=4,
                token=self.hf_token or None,
            )
            self._model = TimesFM3Evaluator(config)
        except Exception as exc:
            _report(progress, f"Checkpoint non caricato: {exc}", 0.0)
            return False
        _report(progress, "TimesFM 3.0 pronto.", 1.0)
        return True

    def score_numbers(self, draws: list[Draw], progress=None) -> dict[int, float]:
        """One score per number for the draw after ``draws``.

        The score is TimesFM's one-step forecast of that number's series. It
        is not a probability: the rolling-frequency series lives around 0.067
        and the forecasts sit in a narrow band around it, so the useful
        content is the *ordering*, and :mod:`core.predictor` is what turns an
        ordering into numbers to play.
        """
        if self._model is None:
            raise ForecasterUnavailable(
                "TimesFM non è caricato — chiama prima load_model(), oppure scegli "
                "un metodo di riferimento che non ne ha bisogno"
            )
        if len(draws) < MIN_CONTEXT_DRAWS:
            raise ForecasterUnavailable(
                f"{len(draws)} estrazioni sono troppo poche: ne servono almeno "
                f"{MIN_CONTEXT_DRAWS} perché la finestra mobile abbia senso"
            )

        context = build_context(
            draws,
            representation=self.representation,
            window=self.window,
            context_length=self.context_length,
        )
        _report(
            progress,
            f"Prevedo {context.shape[0]} serie su {context.shape[1]} estrazioni…",
            0.4,
        )
        outputs = list(
            self._model.predict_batch(
                contexts=[context],
                horizon=1,
                return_quantiles=False,
            )
        )
        forecast = np.asarray(outputs[0].forecast, dtype=np.float64)
        # (variates, horizon) with horizon 1, though some paths drop a unit
        # axis — reshape rather than index blind.
        values = forecast.reshape(NUMBER_MAX, -1)[:, 0]
        _report(progress, "Previsione completata.", 1.0)
        return {n: float(values[n - 1]) for n in ALL_NUMBERS}

    def describe(self) -> str:
        chunks = -(-NUMBER_MAX // MAX_VARIATES_PER_FORWARD)
        return (
            f"{self.checkpoint} su {self.device}, serie «{self.representation}», "
            f"contesto di {self.context_length} estrazioni, {NUMBER_MAX} variate in "
            f"{chunks} blocchi di attenzione da al massimo "
            f"{MAX_VARIATES_PER_FORWARD}"
        )


def _report(progress, message: str, fraction: float) -> None:
    if progress:
        progress(message, fraction)
    else:
        print(f"[Forecaster] {message}")
