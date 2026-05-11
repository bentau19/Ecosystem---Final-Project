#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/chrono.h>

#include "ServerNamedPipe.h"
#include "ClientNamedPipe.h"
#include "PipeException.h"

namespace py = pybind11;

// Static exception objects must outlive module init — keep them at translation-unit scope.
static py::exception<PipeException> *exc_base = nullptr;
static py::exception<PipeException> *exc_conn = nullptr;
static py::exception<PipeException> *exc_xfer = nullptr;
static py::exception<PipeException> *exc_time = nullptr;

PYBIND11_MODULE(pipe_module, m)
{
    // Register the three-level hierarchy: PipeError → PipeConnectionError / PipeTransferError
    exc_base = new py::exception<PipeException>(m, "PipeError", PyExc_RuntimeError);
    exc_conn = new py::exception<PipeException>(m, "PipeConnectionError", exc_base->ptr());
    exc_xfer = new py::exception<PipeException>(m, "PipeTransferError", exc_base->ptr());
    exc_time = new py::exception<PipeException>(m, "PipeTimeoutError", exc_base->ptr());

    // Single translator that uses PipeException::category() to pick the right subclass.
    py::register_exception_translator([](std::exception_ptr p)
                                      {
        try
        {
            std::rethrow_exception(p);
        }
        catch (const PipeException& e)
        {
            if (e.category() == PipeErrorCategory::Connection)
              PyErr_SetString(PyExc_ConnectionError, e.what());
            else if (e.category() == PipeErrorCategory::Timeout)
                        PyErr_SetString(PyExc_TimeoutError, e.what());
            else
            PyErr_SetString(PyExc_RuntimeError, e.what());
        } });

    py::class_<ServerNamedPipe>(m, "ServerNamedPipe")
        .def(py::init<int, int, std::string>(),
             py::arg("inputBufferSize"),
             py::arg("outputBufferSize"),
             py::arg("pipeName"))
        .def("__enter__", [](ServerNamedPipe &self)
             { return &self; })
        .def("__exit__", [](ServerNamedPipe &self, py::object, py::object, py::object)
             { self.close(); })
        .def("wait_for_client", &ServerNamedPipe::waitForClient, py::call_guard<py::gil_scoped_release>(),py::arg("timeout") = std::nullopt)
        .def("read", &ServerNamedPipe::read, py::call_guard<py::gil_scoped_release>(), py::arg("timeout") = std::nullopt)
        .def("close", &ServerNamedPipe::close)
        .def("disconnect", &ServerNamedPipe::disconnect);

    py::class_<ClientNamedPipe>(m, "ClientNamedPipe")
        .def(py::init<int, int, std::string>(),
             py::arg("inputBufferSize"),
             py::arg("outputBufferSize"),
             py::arg("pipeName"))
        .def("__enter__", [](ClientNamedPipe &self)
             { return &self; })
        .def("__exit__", [](ClientNamedPipe &self, py::object, py::object, py::object)
             { self.close(); })
        .def("write", &ClientNamedPipe::write, py::call_guard<py::gil_scoped_release>(), py::arg("data"), py::arg("timeout") = std::nullopt)
        .def("close", &ClientNamedPipe::close);
}