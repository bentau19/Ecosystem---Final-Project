using System;
using System.Threading.Tasks;
using TauSync.Models;

namespace TauSync.Interfaces
{
    /// <summary>
    /// Protocol handler — framing, parsing, and handshake (how data flows).
    /// Does not decide which transport or when to connect; that is IConnectionManager's role.
    /// Per TauSync Protocol Spec: 8-byte header (Length 4B + CorrelationID 3B + Flags 1B) + payload.
    /// </summary>
    public interface IProtocolHandler
    {
        /// <summary>
        /// Builds a TPack: 8-byte header (Length LE, CorrelationID 3B, Flags 1B) + payload.
        /// </summary>
        /// <param name="correlationId">Stream/channel ID (0 = control). C# uses odd IDs.</param>
        /// <param name="payload">Payload bytes (not encrypted in this pass).</param>
        /// <param name="flags">Flags byte (e.g. 0x01 for FIN). Default 0.</param>
        /// <returns>Complete TPack ready to send.</returns>
        byte[] BuildFrame(int correlationId, byte[] payload, byte flags = 0);

        /// <summary>
        /// Parses a complete TPack into CorrelationID, payload, and flags.
        /// </summary>
        /// <param name="rawPacket">Full TPack (8-byte header + payload).</param>
        /// <returns>(correlationId, payload, flags). Flags bit 0 = FIN.</returns>
        (int correlationId, byte[] payload, byte flags) ParseFrame(byte[] rawPacket);

        /// <summary>
        /// Sends a TransferRequest on the control channel (CorrelationID 0) and waits for OK/REJECT.
        /// </summary>
        /// <param name="request">The request to send (serialized as JSON in payload).</param>
        /// <param name="sendRaw">Delegate to send raw TPack.</param>
        /// <param name="receiveResponse">Delegate that returns the next control-channel payload (TPack with id 0).</param>
        /// <returns>True if response was "OK", false if "REJECT".</returns>
        Task<bool> SendHandshakeAsync(
            TransferRequest request,
            Func<byte[], Task> sendRaw,
            Func<Task<byte[]>> receiveResponse);
    }
}
