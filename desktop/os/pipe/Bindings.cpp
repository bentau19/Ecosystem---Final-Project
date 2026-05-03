#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "ServerNamedPipe.h"
#include "ClientNamedPipe.h"
#include "PipeException.h"

namespace py = pybind11;

static void translate_pipe_exception(const PipeException& e)
{
    switch (e.code)
    {
        case PipeErrorCode::ConnectionFailed:
            PyErr_SetString(PyExc_ConnectionError, e.what());
            break;

        case PipeErrorCode::ReadFailed:
        case PipeErrorCode::WriteFailed:
            PyErr_SetString(PyExc_IOError, e.what());
            break;

        case PipeErrorCode::BrokenPipe:
            PyErr_SetString(PyExc_BrokenPipeError, e.what());
            break;

        case PipeErrorCode::AccessDenied:
            PyErr_SetString(PyExc_PermissionError, e.what());
            break;

        default:
            PyErr_SetString(PyExc_RuntimeError, e.what());
            break;
    }
}

PYBIND11_MODULE(pipe_module, m)
{
    py::register_exception_translator([](std::exception_ptr p)
    {
        if (p)
        {
            try
            {
                std::rethrow_exception(p);
            }
            catch (const PipeException& e)
            {
                translate_pipe_exception(e);
            }
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