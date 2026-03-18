import dataclasses
import unittest
from typing import List, Optional
from unittest.mock import MagicMock, patch

from scaler.config.config_class import ConfigClass, _reconstruct_config

# ---------------------------------------------------------------------------
# Minimal stub configs for section= tests
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class _SimpleSchedulerConfig(ConfigClass):
    host: str = "localhost"
    port: int = 8516


@dataclasses.dataclass
class _SimpleWorkerConfig(ConfigClass):
    workers: int = 1


@dataclasses.dataclass
class _SectionTestConfig(ConfigClass):
    scheduler: Optional[_SimpleSchedulerConfig] = dataclasses.field(default=None, metadata=dict(section="scheduler"))
    workers: List[_SimpleWorkerConfig] = dataclasses.field(default_factory=list, metadata=dict(section="workers"))


class TestSectionMetadata(unittest.TestCase):
    """Tests the section= metadata path in ConfigClass / _reconstruct_config."""

    def _build(self, toml_data):
        return _reconstruct_config(_SectionTestConfig, {}, toml_data)

    def test_single_table_populates_optional(self) -> None:
        toml = {"scheduler": {"host": "192.168.1.1", "port": 9999}}
        config = self._build(toml)
        self.assertIsNotNone(config.scheduler)
        self.assertEqual(config.scheduler.host, "192.168.1.1")
        self.assertEqual(config.scheduler.port, 9999)

    def test_absent_section_gives_none(self) -> None:
        config = self._build({})
        self.assertIsNone(config.scheduler)

    def test_absent_list_section_gives_empty_list(self) -> None:
        config = self._build({})
        self.assertEqual(config.workers, [])

    def test_single_dict_in_list_section_gives_one_element(self) -> None:
        toml = {"workers": {"workers": 4}}
        config = self._build(toml)
        self.assertEqual(len(config.workers), 1)
        self.assertEqual(config.workers[0].workers, 4)

    def test_array_of_tables_gives_multiple_elements(self) -> None:
        toml = {"workers": [{"workers": 2}, {"workers": 8}]}
        config = self._build(toml)
        self.assertEqual(len(config.workers), 2)
        self.assertEqual(config.workers[0].workers, 2)
        self.assertEqual(config.workers[1].workers, 8)

    def test_both_sections_populated(self) -> None:
        toml = {"scheduler": {"host": "10.0.0.1", "port": 1234}, "workers": [{"workers": 3}]}
        config = self._build(toml)
        self.assertIsNotNone(config.scheduler)
        self.assertEqual(config.scheduler.host, "10.0.0.1")
        self.assertEqual(len(config.workers), 1)
        self.assertEqual(config.workers[0].workers, 3)


# ---------------------------------------------------------------------------
# Minimal _AIOConfig-like stub for end-to-end tests
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class _MiniAIOConfig(ConfigClass):
    scheduler: Optional[_SimpleSchedulerConfig] = dataclasses.field(default=None, metadata=dict(section="scheduler"))
    workers: List[_SimpleWorkerConfig] = dataclasses.field(default_factory=list, metadata=dict(section="workers"))


class TestAIOEndToEnd(unittest.TestCase):
    """End-to-end tests for the section= flow through ConfigClass.parse."""

    def _make_toml_data(self, data):
        """Return a mock _load_toml that yields the given data dict."""
        return patch("scaler.config.config_class._load_toml", return_value=data)

    @patch("sys.argv", ["scaler_aio", "--config", "test.toml"])
    def test_no_recognized_sections_exits(self) -> None:
        with self._make_toml_data({}):
            config = _MiniAIOConfig.parse("scaler_aio", "aio")
        self.assertIsNone(config.scheduler)
        self.assertEqual(config.workers, [])

    @patch("sys.argv", ["scaler_aio", "--config", "test.toml"])
    def test_scheduler_section_populated(self) -> None:
        toml = {"scheduler": {"host": "127.0.0.1", "port": 8516}}
        with self._make_toml_data(toml):
            config = _MiniAIOConfig.parse("scaler_aio", "aio")
        self.assertIsNotNone(config.scheduler)
        self.assertEqual(config.scheduler.host, "127.0.0.1")

    @patch("sys.argv", ["scaler_aio", "--config", "test.toml"])
    def test_workers_list_populated(self) -> None:
        toml = {"workers": [{"workers": 4}, {"workers": 8}]}
        with self._make_toml_data(toml):
            config = _MiniAIOConfig.parse("scaler_aio", "aio")
        self.assertEqual(len(config.workers), 2)

    @patch("sys.argv", ["scaler_aio", "--help"])
    def test_help_exits(self) -> None:
        with self.assertRaises(SystemExit):
            _MiniAIOConfig.parse("scaler_aio", "aio")


class TestAIOMain(unittest.TestCase):
    """Tests for scaler_aio main() process spawning logic."""

    def _run_main_with_toml(self, toml_data):
        from scaler.entry_points.aio import main

        with patch("scaler.config.config_class._load_toml", return_value=toml_data), patch(
            "multiprocessing.Process"
        ) as mock_process_cls:
            mock_proc = MagicMock()
            mock_process_cls.return_value = mock_proc
            with patch("sys.argv", ["scaler_aio", "--config", "test.toml"]):
                main()
        return mock_process_cls, mock_proc

    def test_no_sections_exits_with_code_1(self) -> None:
        from scaler.entry_points.aio import main

        with patch("scaler.config.config_class._load_toml", return_value={}), patch(
            "sys.argv", ["scaler_aio", "--config", "test.toml"]
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()
        self.assertEqual(ctx.exception.code, 1)
