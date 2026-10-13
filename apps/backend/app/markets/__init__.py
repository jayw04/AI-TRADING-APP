"""Market identity shared by every market subsystem.

``context`` names the market a dataset, run or result belongs to. ``source_classification`` records,
per data source, what access and use are established. Market-specific code lives in a subpackage
(``cn_ashare``); the existing US code is unchanged and is described by ``context.US_EQUITY``.
"""
