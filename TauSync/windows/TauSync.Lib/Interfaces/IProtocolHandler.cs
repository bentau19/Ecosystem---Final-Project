using System;
using System.Threading.Tasks;
using TauSync.Models;

namespace TauSync.Interfaces
{
    /// <summary>
    /// Protocol handler — framing, parsing, and handshake.
    /// Transport uses only this interface to read frames; no protocol constants in transport.
    /// </summary>
    public interface IProtocolHandler
    {
        /// <summary>Size in bytes of the fixed-length frame header.</summary>
        int GetHeaderSize();

        /// <summary>Given the header bytes, returns the payload length to read for this frame.</summary>
        int GetPayloadLength(byte[] header);

        /// <summary>True if this (targetId, flags) denotes a control frame (e.g. discovery/handshake).</summary>
        bool IsControlFrame(int targetId, byte flags);

        /// <summary>
        /// Builds a frame: header + payload. Format is protocol-specific.
        /// </summary>
        byte[] BuildFrame(int targetId, byte[] payload, byte flags = 0);

        /// <summary>
        /// Parses a complete frame (header + payload) into targetId, payload, and flags.
        /// </summary>
        (int targetId, byte[] payload, byte flags) ParseFrame(byte[] rawPacket);

        /// <summary>
        /// Sends a handshake request and waits for the response.
        /// </summary>
        /// <param name="request">The handshake request to send.</param>
        /// <param name="sendRaw">Delegate to send the raw frame (e.g. transport).</param>
        /// <param name="receiveResponse">Delegate to wait for and return the response payload (caller may apply timeout).</param>
        /// <returns>The parsed <see cref="TransferRequest"/> from the peer, or null if invalid/missing.</returns>
        Task<TransferRequest?> SendHandshakeAsync(
            TransferRequest request,
            Func<byte[], Task> sendRaw,
            Func<Task<byte[]>> receiveResponse);
    }
}
