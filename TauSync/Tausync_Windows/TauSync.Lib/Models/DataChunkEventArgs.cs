using System;

namespace TauSync.Models
{
    /// <summary>
    /// Event arguments for data chunk received events (for Python UI).
    /// </summary>
    public class DataChunkEventArgs : EventArgs
    {
        public byte[] Chunk { get; }
        public bool IsFinal { get; }

        public DataChunkEventArgs(byte[] chunk, bool isFinal)
        {
            Chunk = chunk ?? throw new ArgumentNullException(nameof(chunk));
            IsFinal = isFinal;
        }
    }
}
