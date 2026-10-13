"""A-share daily-data providers.

Each adapter wraps an injected client (``tushare.pro_api(...)`` or the ``baostock`` module), so the
same parsing code runs against the real library or against the synthetic clients in ``synthetic``.
Neither library is a repository dependency yet: the ``from_*`` constructors import them lazily.
"""
