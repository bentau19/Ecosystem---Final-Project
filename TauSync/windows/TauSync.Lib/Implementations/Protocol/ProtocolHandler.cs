using System;
using System.Text;
using System.Threading.Tasks;
using TauSync.Core;
using TauSync.Interfaces;
using TauSync.Models;

namespace TauSync.Implementations.Protocol
{
    /// <summary>
    /// Implements TauSync TPack: 8-byte header (Length 4B LE + CorrelationID 3B + Flags 1B) + payload.
    /// Handshake on control channel (CorrelationID 0). No encryption in this implementation.
    /// </summary>
    public class ProtocolHandler : IProtocolHandler
    {
        /// <inheritdoc />
        public byte[] BuildFrame(int correlationId, byte[] payload, byte flags = 0)
        {
            if (payload == null)
                throw new ArgumentNullException(nameof(payload));
            if (correlationId < 0 || correlationId > 0xFFFFFF)
                throw new ArgumentOutOfRangeException(nameof(correlationId), "CorrelationID must fit in 3 bytes (0..0xFFFFFF).");

            byte[] header = new byte[CoreConfig.TPackHeaderSize];
            int len = payload.Length;
            header[0] = (byte)(len & 0xFF);
            header[1] = (byte)((len >> 8) & 0xFF);
            header[2] = (byte)((len >> 16) & 0xFF);
            header[3] = (byte)((len >> 24) & 0xFF);
            header[4] = (byte)(correlationId & 0xFF);
            header[5] = (byte)((correlationId >> 8) & 0xFF);
            header[6] = (byte)((correlationId >> 16) & 0xFF);
            header[7] = flags;

            byte[] frame = new byte[CoreConfig.TPackHeaderSize + payload.Length];
            Buffer.BlockCopy(header, 0, frame, 0, CoreConfig.TPackHeaderSize);
            Buffer.BlockCopy(payload, 0, frame, CoreConfig.TPackHeaderSize, payload.Length);
            return frame;
        }

        /// <summary>
        /// Parses a complete TPack into CorrelationID, payload, and flags.
        /// </summary>
        public (int correlationId, byte[] payload, byte flags) ParseFrame(byte[] rawPacket)
        {
            if (rawPacket == null)
                throw new ArgumentNullException(nameof(rawPacket));
            if (rawPacket.Length < CoreConfig.TPackHeaderSize)
                throw new ArgumentException($"Packet too small: need at least {CoreConfig.TPackHeaderSize} bytes.", nameof(rawPacket));

            int length = rawPacket[0] | (rawPacket[1] << 8) | (rawPacket[2] << 16) | (rawPacket[3] << 24);
            int correlationId = rawPacket[4] | (rawPacket[5] << 8) | (rawPacket[6] << 16);
            byte flags = rawPacket[7];

            if (rawPacket.Length != CoreConfig.TPackHeaderSize + length)
                throw new ArgumentException($"Packet length mismatch: header says payload length {length}, total bytes {rawPacket.Length}.");

            byte[] payload = new byte[length];
            if (length > 0)
                Buffer.BlockCopy(rawPacket, CoreConfig.TPackHeaderSize, payload, 0, length);
            return (correlationId, payload, flags);
        }

        /// <inheritdoc />
        public async Task<bool> SendHandshakeAsync(
            TransferRequest request,
            Func<byte[], Task> sendRaw,
            Func<Task<byte[]>> receiveResponse)
        {
            if (request == null)
                throw new ArgumentNullException(nameof(request));
            if (sendRaw == null)
                throw new ArgumentNullException(nameof(sendRaw));
            if (receiveResponse == null)
                throw new ArgumentNullException(nameof(receiveResponse));
            if (!request.IsValid())
                throw new ArgumentException("TransferRequest is invalid.", nameof(request));

            string json = System.Text.Json.JsonSerializer.Serialize(request);
            byte[] jsonBytes = Encoding.UTF8.GetBytes(json);
            byte[] frame = BuildFrame(CoreConfig.ControlChannelId, jsonBytes);
            await sendRaw(frame).ConfigureAwait(false);

            byte[] responsePayload = await receiveResponse().ConfigureAwait(false);
            var response = System.Text.Json.JsonSerializer.Deserialize<TransferRequest>(Encoding.UTF8.GetString(responsePayload));
            return response?.Status?.ToUpperInvariant() == "OK";
        }
    }
}
