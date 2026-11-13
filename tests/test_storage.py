import os
import unittest
from pathlib import Path
from unittest.mock import patch
from storage import data_directory

class ConfigurationStorage(unittest.TestCase):
    @patch.dict(os.environ,{},clear=True)
    def test_new_container_uses_automatic_config_volume(self):
        self.assertEqual(data_directory(container=True,mounts={'/config','/media'}),Path('/config'))
    @patch.dict(os.environ,{},clear=True)
    def test_legacy_mount_is_not_replaced_by_new_anonymous_volume(self):
        self.assertEqual(data_directory(container=True,mounts={'/data','/config','/media'}),Path('/data'))
    @patch.dict(os.environ,{'DATA_DIR':'/custom/config'},clear=True)
    def test_existing_explicit_path_is_respected(self):
        self.assertEqual(data_directory(container=True,mounts={'/config'}),Path('/custom/config'))
    @patch.dict(os.environ,{},clear=True)
    def test_local_development_keeps_existing_directory(self):
        self.assertEqual(data_directory(container=False),Path('./data').resolve())
