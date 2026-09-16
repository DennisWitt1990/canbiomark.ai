"""Regression coverage for selecting cells before merging experiments."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

try:
    import anndata as ad
    import numpy as np
    import pandas as pd
except ImportError:
    ad = None

from app.domain.errors import ValidationError
from app.domain.experiment import CellTypeSelection
from app.services.cell_selection_service import CellSelectionService
from app.services.experiment_catalog_service import ExperimentCatalogService
from app.services.workspace_service import UserWorkspace


@unittest.skipIf(ad is None, 'Scientific dependencies required for H5AD integration tests')
class CellSelectionWorkflowTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        catalogue = root / 'catalogue'
        catalogue.mkdir()
        for suffix, name in [('a', 'Experiment A'), ('b', 'Experiment B')]:
            (catalogue / f'catalog_{suffix}.txt').write_text(f'{name};Tissue {suffix}\n')
            data = ad.AnnData(np.array([[1., 2.], [3., 4.], [5., 6.]]),
                obs=pd.DataFrame({'file_name': [name]*3, 'cell_type': ['T cell', 'B cell', 'T cell']}, index=[f'{suffix}{i}' for i in range(3)]),
                var=pd.DataFrame(index=['gene1', 'gene2']))
            data.write_h5ad(catalogue / f'combined_adata_{suffix}.h5ad')
        self.service = CellSelectionService(ExperimentCatalogService(catalogue))
        self.workspace = UserWorkspace('test', root / 'workspace')
        # Real H5AD I/O and concatenation, without importing plotting libraries.
        self.scanpy = SimpleNamespace(read_h5ad=ad.read_h5ad, concat=ad.concat)
        patcher = patch.dict(sys.modules, {'scanpy': self.scanpy})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_preview_reads_only_metadata_and_does_not_merge(self):
        def no_concat(*args, **kwargs):
            self.fail('Preview must not merge expression matrices')
        def read_metadata(path, **kwargs):
            self.assertEqual(kwargs, {'backed': 'r'})
            return ad.read_h5ad(path, **kwargs)
        self.scanpy.concat = no_concat
        self.scanpy.read_h5ad = read_metadata
        self.assertEqual(self.service.list_cell_types([0, 1]), {
            'Experiment A': ['B cell', 'T cell'], 'Experiment B': ['B cell', 'T cell']})
        self.assertFalse(self.workspace.root_directory.exists())

    def test_selected_types_are_kept_per_experiment(self):
        selection = CellTypeSelection.from_mapping({'Experiment A': ['T cell'], 'Experiment B': ['B cell']})
        result = self.service.create_selected_dataset(self.workspace, [0, 1], selection)
        data = ad.read_h5ad(self.workspace.resolve(result))
        self.assertEqual(list(data.obs_names), ['a0', 'a2', 'b1'])
        np.testing.assert_array_equal(data.X, [[1, 2], [5, 6], [3, 4]])
        self.assertEqual(set(data.obs['Sample.Characteristic.individual']), {'donor1'})
        self.assertFalse((self.workspace.cell_selection_directory / 'merged_experiments.h5ad').exists())

    def test_invalid_selections_cannot_create_dataset(self):
        for selection in [
            {'Experiment A': ['T cell']},
            {'Experiment A': ['missing'], 'Experiment B': ['B cell']},
            {'Experiment A': [], 'Experiment B': ['B cell']},
        ]:
            with self.subTest(selection=selection), self.assertRaises(ValidationError):
                self.service.create_selected_dataset(self.workspace, [0, 1], CellTypeSelection.from_mapping(selection))
            self.assertFalse(self.workspace.root_directory.exists())

    def test_duplicate_experiment_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.service.list_cell_types([0, 0])
