"""Offline guardrail tests; these never query Docker, AWS or FHIR."""
import subprocess
import unittest
from unittest.mock import patch
from demo_check import CheckError, command, permits_ipv4, sql_settings


class GuardrailTests(unittest.TestCase):
    def test_sql_requires_encryption_and_certificate_validation(self):
        good = "Data Source=example.test,1433;Encrypt=True;Trust Server Certificate=False;Password=not-printed"
        self.assertEqual(sql_settings(good), ("example.test", 1433))
        for bad in [good.replace("Encrypt=True", "Encrypt=False"),
                    good.replace("Certificate=False", "Certificate=True")]:
            with self.assertRaises(CheckError) as error:
                sql_settings(bad)
            self.assertNotIn("not-printed", str(error.exception))

    def test_changed_ip_and_wrong_port_are_denied(self):
        rule = {"IpProtocol": "tcp", "FromPort": 1433, "ToPort": 1433,
                "IpRanges": [{"CidrIp": "192.0.2.10/32"}]}
        self.assertTrue(permits_ipv4(rule, "192.0.2.10", 1433))
        self.assertFalse(permits_ipv4(rule, "192.0.2.11", 1433))
        self.assertFalse(permits_ipv4(rule, "192.0.2.10", 443))
        self.assertFalse(permits_ipv4({**rule, "IpProtocol": "udp"}, "192.0.2.10", 1433))

    def test_expired_aws_login_has_safe_remediation(self):
        result = subprocess.CompletedProcess([], 1, b"", b"session expired: confidential-value")
        with patch("demo_check.subprocess.run", return_value=result):
            with self.assertRaises(CheckError) as error:
                command(["aws", "sts", "get-caller-identity"])
        self.assertIn("aws login --profile firely-learning", str(error.exception))
        self.assertNotIn("confidential-value", str(error.exception))

    def test_unknown_cli_error_is_not_exposed(self):
        result = subprocess.CompletedProcess([], 1, b"", b"Password=confidential-value")
        with patch("demo_check.subprocess.run", return_value=result):
            with self.assertRaisesRegex(CheckError, "^command_failed$"):
                command(["aws", "sts", "get-caller-identity"])


if __name__ == "__main__":
    unittest.main()
