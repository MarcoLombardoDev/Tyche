# Tyche — SuperEnalotto Archive Analysis & TimesFM Forecasting
# Copyright (C) 2026 Marco Lombardo
#
# Private project. All rights reserved; see LICENSE.
# Distributed WITHOUT ANY WARRANTY.

"""
version.py — Tyche

Single source of truth for the application's identity, mirroring the same
module in Argus so the two products stay recognisably the same codebase
family.

The TimesFM checkpoint lives here too. It is not a user preference with a
sensible fallback: 3.0 is the first TimesFM trained natively for multivariate
forecasting, and Tyche feeds it 90 series at once. Pointing this at a 2.x
checkpoint would not degrade gracefully, it would change what the model is
being asked to do.
"""

APP_NAME = "Tyche"
APP_TITLE = "Tyche — Analisi dell'archivio SuperEnalotto e previsioni con TimesFM"

# Bump by hand on a release. A frozen executable has no .py sources on disk
# to derive a date from — the same reasoning as Argus's version.py.
__version__ = "0.5.0"

# google/timesfm-3.0-pytorch, released 31 August 2026: 330M parameters, native
# multivariate forecasting, and the reason Tyche can hand TimesFM all 90
# number-series as one joint context instead of 90 separate univariate calls.
#
# The weights are covered by timesfm-non-commercial-license-v1.0 — non
# commercial, non production use only. The repository code is Apache-2.0. That
# split is fine for Tyche, which is private and not for sale; it would not be
# fine for Argus, and the two must not share a checkpoint policy by habit.
DEFAULT_TIMESFM_CHECKPOINT = "google/timesfm-3.0-pytorch"

CONTACT_EMAIL = "marco.lombardo@gmail.com"
