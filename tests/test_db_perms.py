import os
import stat

from sentinel.core.db import Database


def test_db_file_is_owner_only(tmp_path):
    p = tmp_path / "sentinel.db"
    Database(str(p))
    mode = stat.S_IMODE(os.stat(p).st_mode)
    # žiadne práva pre skupinu/ostatných
    assert mode & 0o077 == 0, oct(mode)


def test_memory_db_does_not_crash():
    # :memory: nemá súbor → chmod sa preskočí bez chyby
    Database(":memory:")
