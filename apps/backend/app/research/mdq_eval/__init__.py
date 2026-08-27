"""MDQ-001 K-criteria evaluation.

Every governed K-value must be downstream of the section 7.1 admissibility decision — a K-value
computed over an inadmissible partition is not evidence, it is a number. That rule is enforced
structurally: `gate.require_admissible` is the only mint for the token an evidentiary result needs.

K3 is implemented in full (its metric is frozen and self-contained). K1 is implemented as a frame and
returns NOT EVALUABLE with a precise reason until its governed inputs exist. K5 cannot contribute to
the GO floor (signed section 8.4) and K6 is event-contingent, so neither is implemented here.
"""
