#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/chrono.h>

#include "ServerNamedPipe.h"
#include "ClientNamedPipe.h"
#include "PipeException.h"

namespace py = pybind11;

// Static exception objects must outlive module init — keep them at translation-unit scope.
static py::exception<PipeException>* exc_base = nullptr;
static py::exception<PipeException>* exc_conn = nullptr;
static py::exception<PipeException>* exc_xfer = nullptr;
static py::exception<PipeException>* exc_time = nullptr;

PYBIND11_MODULE(pipe_module, m)
{
    // Register the three-level hierarchy: PipeError -> PipeConnectionError / PipeTransferError
    exc_base = new py::exception<PipeException>(m, "PipeError",          PyExc_RuntimeError);
    exc_conn = new py::exception<PipeException>(m, "PipeConnectionError", exc_base->ptr());
    exc_xfer = new py::exception<PipeException>(m, "PipeTransferError",   exc_base->ptr());
    exc_time = new py::exception<PipeException>(m, "PipeTimeoutError",    exc_base->ptr());

    // Single translator that uses PipeException::category() to pick the right subclass.
    py::register_exception_translator([](std::exception_ptr p)
    {
        try
        {
            std::rethrow_exception(p);
        }
        catch (const PipeException& e)
        {
            if      (e.category() == PipeErrorCategory::Connection)
                PyErr_SetString(PyExc_ConnectionError, e.what());
            else if (e.category() == PipeErrorCategory::Timeout)
                PyErr_SetString(PyExc_TimeoutError, e.what());
            else
                PyErr_SetString(PyExc_RuntimeError, e.what());
        }
    });

    // ── ServerNamedPipe ───────────────────────────────────────────────────────
    py::class_<ServerNamedPipe>(m, "ServerNamedPipe")
        .def(py::init<int, int, std::string, bool>(),
             py::arg("input_buffer_size"),
             py::arg("output_buffer_size"),
             py::arg("pipe_name"),
             py::arg("byte_stream") = false)
        .def("__enter__", [](ServerNamedPipe& self) { return &self; })
        .def("__exit__",  [](ServerNamedPipe& self, py::object, py::object, py::object)
             { self.close(); })
        .def("wait_for_client", &ServerNamedPipe::waitForClient,
             py::call_guard<py::gil_scoped_release>(),
             py::arg("timeout") = std::nullopt)
        // read() — one message (message-mode) or up to buffer size (byte-stream).
        // GIL released only around the blocking call; py::bytes built with GIL held.
        .def("read",
             [](ServerNamedPipe& self, std::optional<std::chrono::milliseconds> timeout)
             {
                 std::string result;
                 {
                     py::gil_scoped_release release;
                     result = self.read(timeout);
                 }
                 return py::bytes(result);
             },
             py::arg("timeout") = std::nullopt)
        // read_exact(n) — block until exactly n bytes arrive; for byte-stream frame parsing.
        .def("read_exact",
             [](ServerNamedPipe& self, size_t n,
                std::optional<std::chrono::milliseconds> timeout)
             {
                 std::string result;
                 {
                     py::gil_scoped_release release;
                     result = self.readExact(n, timeout);
                 }
                 return py::bytes(result);
             },
             py::arg("n"),
             py::arg("timeout") = std::nullopt)
        // write(data) — send bytes to the connected client.
        .def("write",
             [](ServerNamedPipe& self, const std::string& data,
                std::optional<std::chrono::milliseconds> timeout)
             {
                 py::gil_scoped_release release;
                 self.write(data, timeout);
             },
             py::arg("data"),
             py::arg("timeout") = std::nullopt)
        .def("close",      &ServerNamedPipe::close)
        .def("disconnect", &ServerNamedPipe::disconnect);

    // ── ClientNamedPipe ───────────────────────────────────────────────────────
    py::class_<ClientNamedPipe>(m, "ClientNamedPipe")
        .def(py::init<int, int, std::string, bool>(),
             py::arg("input_buffer_size"),
             py::arg("output_buffer_size"),
             py::arg("pipe_name"),
             py::arg("duplex") = false)
        .def("__enter__", [](ClientNamedPipe& self) { return &self; })
        .def("__exit__",  [](ClientNamedPipe& self, py::object, py::object, py::object)
             { self.close(); })
        .def("write",
             &ClientNamedPipe::write,
             py::call_guard<py::gil_scoped_release>(),
             py::arg("data"),
             py::arg("timeout") = std::nullopt)
        // read_exact(n) — only meaningful when duplex=True.
        .def("read_exact",
             [](ClientNamedPipe& self, size_t n,
                std::optional<std::chrono::milliseconds> timeout)
             {
                 std::string result;
                 {
                     py::gil_scoped_release release;
                     result = self.readExact(n, timeout);
                 }
                 return py::bytes(result);
             },
             py::arg("n"),
             py::arg("timeout") = std::nullopt)
        .def("close", &ClientNamedPipe::close);
}
