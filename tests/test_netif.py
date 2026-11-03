"""网卡枚举排序、默认选择与已保存选择回归。"""

import os
import unittest

from core.netif import (
    NetIf, apply_saved, default_binds, list_interfaces, loopback_rows,
    preferred_lan_ip, sort_interfaces, wildcard_row,
)


def make(name, address, family=4, kind="ethernet", up=True, private=True):
    return NetIf(name=name, address=address, family=family, kind=kind,
                 is_up=up, is_private=private)


class SortInterfacesTest(unittest.TestCase):
    def test_full_order(self):
        items = [
            *loopback_rows(),
            wildcard_row(),
            make("Wi-Fi", "10.0.0.7", kind="wifi"),
            make("以太网", "192.168.1.5"),
            make("VMware VMnet8", "192.168.38.1", kind="virtual"),
            make("ZeroTier", "fcef::1", family=6, kind="vpn"),
            make("Wi-Fi", "", up=False, kind="wifi"),
        ]
        ordered = sort_interfaces(items)
        addresses = [i.address for i in ordered]
        self.assertEqual(addresses[0], "192.168.1.5")
        self.assertEqual(addresses[1], "10.0.0.7")
        self.assertIn("192.168.38.1", addresses[:3])
        ipv6_index = addresses.index("fcef::1")
        virtual_index = addresses.index("192.168.38.1")
        wildcard_index = addresses.index("0.0.0.0")
        unavailable_index = addresses.index("")
        loopback_index = addresses.index("::1")
        self.assertLess(virtual_index, ipv6_index)
        self.assertLess(ipv6_index, wildcard_index)
        self.assertLess(wildcard_index, unavailable_index)
        self.assertLess(unavailable_index, loopback_index)
        self.assertEqual(addresses[-1], "127.0.0.1")

    def test_private_ipv4_before_public(self):
        items = [make("以太网", "8.8.8.8", private=False),
                 make("以太网", "192.168.1.5", private=True)]
        ordered = sort_interfaces(items)
        self.assertEqual([i.address for i in ordered], ["192.168.1.5", "8.8.8.8"])

    def test_loopback_always_last(self):
        items = [*loopback_rows(), make("以太网", "10.1.2.3")]
        self.assertEqual(sort_interfaces(items)[-1].address, "127.0.0.1")


class DefaultSelectionTest(unittest.TestCase):
    def test_prefers_first_connected_physical(self):
        items = [*loopback_rows(), wildcard_row(),
                 make("VMware", "192.168.56.1", kind="virtual"),
                 make("以太网", "192.168.1.5")]
        self.assertEqual(default_binds(items), ["192.168.1.5"])

    def test_skips_wildcard_and_unavailable(self):
        items = [*loopback_rows(), wildcard_row(),
                 make("Wi-Fi", "10.0.0.7", up=False, kind="wifi")]
        self.assertEqual(default_binds(items), ["127.0.0.1"])

    def test_only_loopback_falls_back_to_loopback(self):
        self.assertEqual(default_binds(loopback_rows()), ["127.0.0.1"])


class SavedSelectionTest(unittest.TestCase):
    def test_existing_saved_addresses_are_kept(self):
        items = [*loopback_rows(), make("以太网", "192.168.1.5"),
                 make("Wi-Fi", "10.0.0.7", kind="wifi")]
        selected, invalid = apply_saved(["10.0.0.7", "127.0.0.1"], items)
        self.assertEqual(selected, ["10.0.0.7", "127.0.0.1"])
        self.assertEqual(invalid, [])

    def test_invalid_saved_entries_are_reported_but_kept_selection(self):
        items = [*loopback_rows(), make("以太网", "192.168.1.5")]
        selected, invalid = apply_saved(["192.168.1.5", "10.9.9.9"], items)
        self.assertEqual(selected, ["192.168.1.5"])
        self.assertEqual(invalid, ["10.9.9.9"])

    def test_all_invalid_falls_back_to_default(self):
        items = [*loopback_rows(), make("以太网", "192.168.1.5")]
        selected, invalid = apply_saved(["10.9.9.9"], items)
        self.assertEqual(selected, ["192.168.1.5"])
        self.assertEqual(invalid, ["10.9.9.9"])

    def test_duplicate_saved_is_deduped(self):
        items = [*loopback_rows(), make("以太网", "192.168.1.5")]
        selected, _ = apply_saved(["192.168.1.5", "192.168.1.5"], items)
        self.assertEqual(selected, ["192.168.1.5"])


class LiveEnumerationTest(unittest.TestCase):
    def test_live_list_is_sorted_and_loopback_last(self):
        rows = list_interfaces()
        self.assertTrue(any(i.address == "0.0.0.0" for i in rows))
        loopbacks = [i for i in rows if i.is_loopback]
        self.assertGreaterEqual(len(loopbacks), 1)
        self.assertEqual(rows[-1].address, "127.0.0.1")
        addresses = [i.address for i in rows]
        wildcard = addresses.index("0.0.0.0")
        loopback = addresses.index("127.0.0.1")
        self.assertLess(wildcard, loopback)

    def test_default_matches_expectation(self):
        rows = list_interfaces()
        default = default_binds(rows)
        self.assertTrue(default)
        if any(i.is_up and not i.is_loopback and not i.is_wildcard and i.bindable
               for i in rows):
            self.assertFalse(all(a.startswith("127.") or a == "::1" for a in default))
        else:
            self.assertEqual(default, ["127.0.0.1"])

    def test_preferred_lan_ip(self):
        ip = preferred_lan_ip()
        self.assertTrue(ip)
        self.assertNotEqual(ip, "0.0.0.0")

    @unittest.skipUnless(os.name == "nt", "Windows 专属枚举")
    def test_windows_returns_adapter_names(self):
        rows = [i for i in list_interfaces() if not i.is_loopback and not i.is_wildcard]
        self.assertTrue(rows)
        self.assertTrue(any("·" in i.label for i in rows))
