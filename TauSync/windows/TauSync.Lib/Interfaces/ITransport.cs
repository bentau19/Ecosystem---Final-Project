using System;

namespace TauSync.Interfaces
{

    public interface ITransport : IDisposable
    {

        void Connect(string targetId);


        void SendRaw(byte[] data);

        bool IsConnected();
    }
}
