"""Process evaluation across three applications, computed by the library.

This subpackage holds what Section 5 and Appendix B of the paper refer to:

``adapters``
    The domain adapters and their configurations: BPI Challenge 2019
    (purchase-to-pay), BPI Challenge 2013 incidents (service management) and
    BPI Challenge 2017 (lending).
``norms/native``
    The serialised native norms: identity metric constraints over the
    prepared assessments, loadable with :meth:`wise.Norm.load`.
``data_catalog.json`` and :mod:`~wise.evaluation.data`
    The input catalogue with source identities and input hashes, and the
    check made before a log is read.
:mod:`~wise.evaluation.native`
    The carrier log and the bridge from prepared assessments to the library.
:mod:`~wise.evaluation.reference` and :mod:`~wise.evaluation.replay`
    The reference arithmetic and the replay with the numerical checks of
    Section 5.6.
:mod:`~wise.evaluation.paper` and :mod:`~wise.evaluation.figures`
    One function per result item, table and figure of the paper, and the
    comparison of computed with printed values.
``expected``
    The printed values of every result item and compact aggregate reference
    results.

No log is part of this repository; see the README for where each is obtained.
"""

from .data import DATA_ENVIRONMENT, DataMismatch, DataNotAvailable

__all__ = ["DATA_ENVIRONMENT", "DataMismatch", "DataNotAvailable"]
