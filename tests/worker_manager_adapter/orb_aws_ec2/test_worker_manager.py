import unittest

from scaler.worker_manager_adapter.orb_aws_ec2.worker_manager import ORBAWSEC2WorkerAdapter


class TestORBAWSEC2WorkerAdapterValidateRequirements(unittest.TestCase):
    def test_raises_when_opengris_scaler_missing(self):
        requirements = "boto3\nrequests>=2.0\n"
        with self.assertRaises(ValueError):
            ORBAWSEC2WorkerAdapter._validate_requirements(requirements)

    def test_passes_when_opengris_scaler_present(self):
        requirements = "boto3\nopengris-scaler>=1.0\n"
        ORBAWSEC2WorkerAdapter._validate_requirements(requirements)

    def test_passes_with_underscore_variant(self):
        requirements = "opengris_scaler\n"
        ORBAWSEC2WorkerAdapter._validate_requirements(requirements)

    def test_passes_with_extras(self):
        requirements = "opengris-scaler[orb]\n"
        ORBAWSEC2WorkerAdapter._validate_requirements(requirements)

    def test_ignores_comments_and_flags(self):
        requirements = "# opengris-scaler\n-r base.txt\nboto3\n"
        with self.assertRaises(ValueError):
            ORBAWSEC2WorkerAdapter._validate_requirements(requirements)
