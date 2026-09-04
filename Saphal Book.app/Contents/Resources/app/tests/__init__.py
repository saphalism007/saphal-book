"""
Tests run against their own books, never the real ones.

Pointing CHARTERED_BOOK_DATA at a scratch folder before anything imports the
database layer means a test can create and delete companies freely without ever
touching the books a business depends on.
"""

import os
import tempfile

if not os.environ.get("CHARTERED_BOOK_DATA"):
    os.environ["CHARTERED_BOOK_DATA"] = os.path.join(
        tempfile.gettempdir(), "chartered-book-tests")
