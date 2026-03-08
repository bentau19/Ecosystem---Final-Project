using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using System.Threading.Channels;

namespace TauSync.Implementations.Management
{
    /// <summary>
    /// A stream that is written to by the routing handler (incoming TPack payloads) and read from by the client (e.g. Python).
    /// Blocks on Read when no data until more data is written or the stream is completed (FIN).
    /// Uses <see cref="Channel{T}"/> for async-native waiting without blocking a thread in ReadAsync.
    /// </summary>
    internal sealed class BackBufferedStream : Stream
    {
        private readonly Channel<byte[]> _channel = Channel.CreateUnbounded<byte[]>(new UnboundedChannelOptions { SingleReader = false, SingleWriter = false });
        private byte[]? _currentChunk;
        private int _currentOffset;
        private bool _completed;
        private bool _disposed;

        public override bool CanRead => true;
        public override bool CanSeek => false;
        public override bool CanWrite => true;
        public override long Length => throw new NotSupportedException();
        public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }

        /// <summary>
        /// Appends a payload chunk (called by the registered handler when TPack arrives).
        /// </summary>
        public void WriteChunk(byte[] chunk)
        {
            if (chunk == null || chunk.Length == 0) return;
            if (_disposed || _completed) return;
            _channel.Writer.TryWrite(chunk);
        }

        /// <summary>
        /// Marks the stream as complete (FIN received); no more chunks will be written.
        /// </summary>
        public void Complete()
        {
            _completed = true;
            _channel.Writer.Complete();
        }

        public override int Read(byte[] buffer, int offset, int count)
        {
            if (buffer == null) throw new ArgumentNullException(nameof(buffer));
            if (offset < 0 || count < 0 || offset + count > buffer.Length)
                throw new ArgumentOutOfRangeException(nameof(buffer));
            if (_disposed) throw new ObjectDisposedException(nameof(BackBufferedStream));

            int totalRead = 0;
            while (count > 0)
            {
                if (_currentChunk != null)
                {
                    int toCopy = Math.Min(count, _currentChunk.Length - _currentOffset);
                    Buffer.BlockCopy(_currentChunk, _currentOffset, buffer, offset, toCopy);
                    offset += toCopy;
                    count -= toCopy;
                    totalRead += toCopy;
                    _currentOffset += toCopy;
                    if (_currentOffset >= _currentChunk.Length)
                        _currentChunk = null;
                    continue;
                }

                if (_channel.Reader.TryRead(out byte[]? next))
                {
                    _currentChunk = next;
                    _currentOffset = 0;
                    continue;
                }

                if (_completed)
                    return totalRead;

                try
                {
                    _currentChunk = _channel.Reader.ReadAsync(CancellationToken.None).AsTask().GetAwaiter().GetResult();
                    _currentOffset = 0;
                }
                catch (ChannelClosedException)
                {
                    return totalRead;
                }
            }
            return totalRead;
        }

        public override async Task<int> ReadAsync(byte[] buffer, int offset, int count, CancellationToken cancellationToken)
        {
            if (buffer == null) throw new ArgumentNullException(nameof(buffer));
            if (offset < 0 || count < 0 || offset + count > buffer.Length)
                throw new ArgumentOutOfRangeException(nameof(buffer));
            if (_disposed) throw new ObjectDisposedException(nameof(BackBufferedStream));

            int totalRead = 0;
            while (count > 0)
            {
                if (_currentChunk != null)
                {
                    int toCopy = Math.Min(count, _currentChunk.Length - _currentOffset);
                    Buffer.BlockCopy(_currentChunk, _currentOffset, buffer, offset, toCopy);
                    offset += toCopy;
                    count -= toCopy;
                    totalRead += toCopy;
                    _currentOffset += toCopy;
                    if (_currentOffset >= _currentChunk.Length)
                        _currentChunk = null;
                    continue;
                }

                if (_channel.Reader.TryRead(out byte[]? next))
                {
                    _currentChunk = next;
                    _currentOffset = 0;
                    continue;
                }

                if (_completed)
                    return totalRead;

                try
                {
                    _currentChunk = await _channel.Reader.ReadAsync(cancellationToken).ConfigureAwait(false);
                    _currentOffset = 0;
                }
                catch (ChannelClosedException)
                {
                    return totalRead;
                }
            }
            return totalRead;
        }

        public override void Write(byte[] buffer, int offset, int count) => WriteChunk(CopySlice(buffer, offset, count));
        public override void Flush() { }
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();

        private static byte[] CopySlice(byte[] buffer, int offset, int count)
        {
            var copy = new byte[count];
            Buffer.BlockCopy(buffer, offset, copy, 0, count);
            return copy;
        }

        protected override void Dispose(bool disposing)
        {
            if (_disposed) return;
            _disposed = true;
            _channel.Writer.Complete();
            base.Dispose(disposing);
        }
    }
}
