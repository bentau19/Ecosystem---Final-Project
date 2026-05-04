from . import pipe_module

Client = pipe_module.ClientNamedPipe
Server = pipe_module.ServerNamedPipe

PipeError = pipe_module.PipeError
PipeConnectionError = pipe_module.PipeConnectionError
PipeTransferError = pipe_module.PipeTransferError
