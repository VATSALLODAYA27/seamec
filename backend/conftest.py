import os
import tempfile

# Must be set before app.config is imported, so tests never touch the real database.
os.environ["SEAMEC_VAR_DIR"] = tempfile.mkdtemp(prefix="seamec-test-")
