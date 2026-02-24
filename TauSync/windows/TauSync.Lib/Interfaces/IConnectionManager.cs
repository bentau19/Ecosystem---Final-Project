using System;
using TauSync.Models;
using TauSync.Core;
namespace TauSync.Interfaces
{

    public interface IConnectionManager : IDisposable
    {

        void SmartSend(TransferRequest req);

        void HandleIncoming(byte[] rawData);

        public String GetStatus();

        void SwitchStatus(ConnectionStatus status);
        
        event EventHandler<TransferRequest> RequestReceived;

        event EventHandler<Exception> ErrorOccurred;
    }
}
