#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "ServerNamedPipe.h"
#include "ClientNamedPipe.h"
#include "PipeException.h"

namespace py = pybind11;

PYBIND11_MODULE(pipe_module, m)
{
    py::register_exception<PipeException>(
        m, "PipeError", PyExc_RuntimeError);

    py::register_exception_translator([](std::exception_ptr p)
    {
        try
        {
            std::rethrow_exception(p);
        }
        catch (const PipeException& e)
        {
            throw py::value_error(e.what());
        }
    });

    py::class_<ServerNamedPipe>(m, "ServerNamedPipe")
        .def(py::init<int, int, std::string>(),
             py::arg("inputBufferSize"),
             py::arg("outputBufferSize"),
             py::arg("pipeName"))
        .def("__enter__", [](ServerNamedPipe& self) { return &self; })
        .def("__exit__", [](ServerNamedPipe& self, py::object, py::object, py::object) { self.close(); })
        .def("wait_for_client", &ServerNamedPipe::waitForClient, py::call_guard<py::gil_scoped_release>())
        .def("read", &ServerNamedPipe::read, py::call_guard<py::gil_scoped_release>())
        .def("close", &ServerNamedPipe::close)
        .def("disconnect", &ServerNamedPipe::disconnect);

    py::class_<ClientNamedPipe>(m, "ClientNamedPipe")
        .def(py::init<int, int, std::string>(),
             py::arg("inputBufferSize"),
             py::arg("outputBufferSize"),
             py::arg("pipeName"))
        .def("__enter__", [](ClientNamedPipe& self) { return &self; })
        .def("__exit__", [](ClientNamedPipe& self, py::object, py::object, py::object) { self.close(); })
        .def("write", &ClientNamedPipe::write, py::call_guard<py::gil_scoped_release>())
        .def("close", &ClientNamedPipe::close);
}