import unittest

from scripts.provision_demo_workspace import _needs_pipeline


class DemoProvisionerReadinessTests(unittest.TestCase):
    def test_existing_asset_without_chunks_requires_processing_and_indexing(self):
        self.assertTrue(_needs_pipeline(created=False, chunk_count=0))

    def test_existing_asset_with_chunks_is_ready_for_idempotent_reruns(self):
        self.assertFalse(_needs_pipeline(created=False, chunk_count=1))

    def test_new_workspace_requires_processing_and_indexing(self):
        self.assertTrue(_needs_pipeline(created=True, chunk_count=1))
