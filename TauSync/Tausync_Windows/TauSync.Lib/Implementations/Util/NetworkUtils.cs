using System;
using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;

namespace TauSync.Implementations.Util
{
    /// <summary>
    /// Network helpers shared by the hybrid session setup. Kept tiny and dependency-free so the
    /// Java side can mirror it line-for-line.
    /// </summary>
    public static class NetworkUtils
    {
        /// <summary>
        /// Finds this machine's local IPv4 address to advertise in WIFI_CONNECT_READY. Picks an
        /// interface that is up, not loopback, not a tunnel, and not a Bluetooth PAN adapter, with a
        /// routable (non link-local) IPv4 address. Wireless interfaces are preferred over wired so a
        /// laptop on Wi-Fi advertises the address the peer can actually reach.
        /// </summary>
        /// <returns>The chosen IPv4 address, or null when none is available (caller falls back).</returns>
        public static string? GetLocalWifiIpAddress()
        {
            string? wiredFallback = null;

            foreach (NetworkInterface adapter in NetworkInterface.GetAllNetworkInterfaces())
            {
                if (!IsUsableAdapter(adapter))
                    continue;

                string? ipv4 = FirstRoutableIpv4(adapter);
                if (ipv4 == null)
                    continue;

                if (adapter.NetworkInterfaceType == NetworkInterfaceType.Wireless80211)
                    return ipv4;
                wiredFallback ??= ipv4;
            }

            return wiredFallback;
        }

        // Substrings that identify virtual/host-only adapters whose addresses are not reachable
        // from a phone on the same LAN: Hyper-V internal/NAT switches, VMware host-only, VirtualBox.
        private static readonly string[] VirtualAdapterKeywords =
        [
            "bluetooth", "hyper-v", "vmware", "virtualbox", "vethernet", "virtual"
        ];

        private static bool IsUsableAdapter(NetworkInterface adapter)
        {
            if (adapter.OperationalStatus != OperationalStatus.Up)
                return false;
            if (adapter.NetworkInterfaceType is NetworkInterfaceType.Loopback or NetworkInterfaceType.Tunnel)
                return false;

            string description = adapter.Description.ToLowerInvariant();
            string name        = adapter.Name.ToLowerInvariant();
            foreach (string kw in VirtualAdapterKeywords)
                if (description.Contains(kw) || name.Contains(kw))
                    return false;

            return true;
        }

        private static string? FirstRoutableIpv4(NetworkInterface adapter)
        {
            foreach (UnicastIPAddressInformation info in adapter.GetIPProperties().UnicastAddresses)
            {
                if (info.Address.AddressFamily != AddressFamily.InterNetwork)
                    continue;
                if (IPAddress.IsLoopback(info.Address))
                    continue;

                byte[] o = info.Address.GetAddressBytes();
                // 169.254.x.x — link-local (unconfigured APIPA), not routable.
                if (o[0] == 169 && o[1] == 254) continue;
                // 172.16–31.x.x — Hyper-V NAT and similar host-only ranges.
                // Real Wi-Fi on a home/office LAN is 192.168.x.x or 10.x.x.x.
                if (o[0] == 172 && o[1] >= 16 && o[1] <= 31) continue;

                return info.Address.ToString();
            }
            return null;
        }
    }
}
