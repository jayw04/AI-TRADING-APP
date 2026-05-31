#!/usr/bin/env python3
"""generate_master_key.py — emit a fresh Fernet master key.

Usage:
    python scripts/generate_master_key.py

Prints the key to stdout. Copy this into your .env file as
WORKBENCH_MASTER_KEY. DO NOT commit your .env. DO NOT share the key.

Rotating the master key is a non-trivial operation: every existing
ciphertext must be re-encrypted. See docs/runbook/credentials.md
(P5+ polish; not in §4 MVP).
"""
from cryptography.fernet import Fernet

if __name__ == "__main__":
    print(Fernet.generate_key().decode("ascii"))
