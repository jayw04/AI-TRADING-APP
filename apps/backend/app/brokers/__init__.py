"""Broker adapters package.

Per ADR 0002, broker access is centralized. P5 §2 adds the BrokerAdapter
Protocol + BrokerRegistry so the OrderRouter selects an adapter per account.

Only files under ``app/brokers/`` may import a broker trading SDK — enforced by
``apps/backend/scripts/check_broker_isolation.sh``.
"""

from app.brokers.base import BrokerAdapter

__all__ = ["BrokerAdapter"]
