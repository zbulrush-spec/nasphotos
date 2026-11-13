"""Choose configuration storage without requiring user environment variables."""
import os
from pathlib import Path


def data_directory(*, container=None, mounts=None):
    explicit = os.environ.get('DATA_DIR')
    if explicit:
        return Path(explicit).resolve()
    if container is None:
        container = Path('/.dockerenv').exists()
    if not container:
        return Path('./data').resolve()
    if mounts is None:
        info = Path('/proc/self/mountinfo')
        mounts = {line.split()[4] for line in info.read_text().splitlines() if len(line.split()) > 5} if info.exists() else set()
    # Existing NAS installations bind /data. Reuse it, including empty installs,
    # even when Docker has automatically created the new /config volume.
    if '/data' in mounts or Path('/data/library.sqlite').is_file():
        return Path('/data')
    return Path('/config')
