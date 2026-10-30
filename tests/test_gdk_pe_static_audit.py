"""Offline synthetic fixtures for Signal Sprint's pinned PE static-audit gate."""
import struct
import unittest

from package_identity_provisioner import ConflictError
from gdk_pe_static_audit import inspect_pe


def make_pe():
    data = bytearray(2048)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\x00\x00"
    struct.pack_into("<H", data, 0x84, 0x8664)
    struct.pack_into("<H", data, 0x86, 1)
    struct.pack_into("<H", data, 0x94, 240)
    opt = 0x98
    struct.pack_into("<H", data, opt, 0x20B)
    struct.pack_into("<H", data, opt + 68, 2)
    struct.pack_into("<I", data, opt + 108, 16)
    struct.pack_into("<II", data, opt + 120, 0x1000, 40)
    sec = opt + 240
    struct.pack_into("<IIII", data, sec + 8, 0x200, 0x1000, 0x200, 0x400)
    struct.pack_into("<IIIII", data, 0x400, 0, 0, 0, 0x1050, 0)
    data[0x450:0x45D] = b"KERNEL32.dll\x00"
    return bytes(data)


class PinnedPeAuditTests(unittest.TestCase):
    def test_valid_x64_gui_unsigned_direct_imports(self):
        result = inspect_pe(make_pe())
        self.assertEqual(result["machine"], "AMD64")
        self.assertEqual(result["direct_import_dlls"], ["KERNEL32.DLL"])
        self.assertEqual(result["vc_runtime_direct_imports"], [])
        self.assertTrue(result["dynamic_loads_and_runtime_compatibility_not_proven"])

    def test_reject_x86_machine(self):
        b = bytearray(make_pe())
        struct.pack_into("<H", b, 0x84, 0x14C)
        with self.assertRaisesRegex(ConflictError, "x64"):
            inspect_pe(bytes(b))

    def test_reject_console_subsystem(self):
        b = bytearray(make_pe())
        struct.pack_into("<H", b, 0x98 + 68, 3)
        with self.assertRaisesRegex(ConflictError, "Windows GUI"):
            inspect_pe(bytes(b))

    def test_reject_certificate_table(self):
        b = bytearray(make_pe())
        struct.pack_into("<II", b, 0x98 + 112 + 8 * 4, 0x500, 128)
        with self.assertRaisesRegex(ConflictError, "certificate"):
            inspect_pe(bytes(b))

    def test_reject_broken_import_rva(self):
        b = bytearray(make_pe())
        struct.pack_into("<II", b, 0x98 + 120, 0x9000, 40)
        with self.assertRaisesRegex(ConflictError, "RVA"):
            inspect_pe(bytes(b))

    def test_reject_truncated_pe(self):
        with self.assertRaises(ConflictError):
            inspect_pe(b"MZ" + b"\x00" * 30)

    def test_direct_vc_runtime_detection(self):
        b = bytearray(make_pe())
        b[0x450:0x45D] = b"VCRUNTIME.dll\x00"
        self.assertEqual(inspect_pe(bytes(b))["vc_runtime_direct_imports"], ["VCRUNTIME.DLL"])


if __name__ == "__main__":
    unittest.main()
