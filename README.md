# lsort
An auto-formatter for large Python literals

Opt in by putting a ``# lsort`` comment on the same line as the opening brace:

Input:

    CONFIG = {  # lsort
        "b": 1,  # trailing comments travel with their entry
        # so do comment lines directly above an entry
        "a": 2,
    }

Output:

    CONFIG = {  # lsort
        # so do comment lines directly above an entry
        "a": 2,
        "b": 1,  # trailing comments travel with their entry
    }

Only dict literals carrying the marker comment are touched; nested dicts need their own marker.

Entries are sorted by the source text of their key.
