using System;

namespace TauSync.Models
{
    /// <summary>
    /// Event arguments for streaming chunk events.
    /// </summary>
    public class StreamChunkEventArgs : EventArgs
    {
        public byte[] Chunk { get; }
        public int BytesRead { get; }
        public bool IsFinal { get; }

        public StreamChunkEventArgs(byte[] chunk, int bytesRead, bool isFinal)
        {
            Chunk = chunk ?? throw new ArgumentNullException(nameof(chunk));
            BytesRead = bytesRead;
            IsFinal = isFinal;
        }
    }
}
