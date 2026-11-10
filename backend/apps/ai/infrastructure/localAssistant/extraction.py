"""Supervised parsers: 4 MB input, 256 MB child memory, 4 CPU/8 wall seconds."""
import json
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
from .documentWorker import valid_tables

MAX_BYTES = 4 * 1024 * 1024
FORMATS = {'.txt', '.md', '.csv', '.pdf', '.docx'}

def windows_job(process):
    import ctypes as c
    from ctypes import wintypes as w
    class Basic(c.Structure):
        _fields_ = [('processTime', c.c_longlong), ('jobTime', c.c_longlong), ('flags', w.DWORD), ('minWorking', c.c_size_t), ('maxWorking', c.c_size_t), ('active', w.DWORD), ('affinity', c.c_size_t), ('priority', w.DWORD), ('scheduling', w.DWORD)]
    class Io(c.Structure):
        _fields_ = [(name, c.c_ulonglong) for name in ['readOps', 'writeOps', 'otherOps', 'readBytes', 'writeBytes', 'otherBytes']]
    class Limits(c.Structure):
        _fields_ = [('basic', Basic), ('io', Io), ('processMemory', c.c_size_t), ('jobMemory', c.c_size_t), ('peakProcess', c.c_size_t), ('peakJob', c.c_size_t)]
    api = c.WinDLL('kernel32', use_last_error=True)
    api.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]; api.CreateJobObjectW.restype = w.HANDLE
    api.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]; api.SetInformationJobObject.restype = w.BOOL
    api.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]; api.AssignProcessToJobObject.restype = w.BOOL
    api.CloseHandle.argtypes = [w.HANDLE]; api.CloseHandle.restype = w.BOOL
    handle = api.CreateJobObjectW(None, None)
    if not handle:
        raise OSError('Parser isolation unavailable')
    limits = Limits(); limits.basic.flags = 0x2102  # memory + process CPU time + kill on close
    limits.basic.processTime = 4 * 10_000_000
    limits.processMemory = 256 * 1024 * 1024
    if not api.SetInformationJobObject(handle, 9, c.byref(limits), c.sizeof(limits)) or not api.AssignProcessToJobObject(handle, w.HANDLE(int(process._handle))):
        api.CloseHandle(handle)
        raise OSError('Parser isolation unavailable')
    return lambda: api.CloseHandle(handle)

def extract(data: bytes, name: str) -> list[dict]:
    suffix = Path(name).suffix.lower()
    if suffix not in FORMATS or not data or len(data) > MAX_BYTES:
        return []
    worker = Path(__file__).with_name('documentWorker.py')
    packages = []
    if suffix == '.pdf':
        for package in ('pypdfium2','pypdf'):
            spec = importlib.util.find_spec(package)
            if spec is None or not spec.origin:
                return []
            packages.append(str(Path(spec.origin).resolve().parent.parent))
    # Avoid a Windows venv redirector spawning a child before Job assignment.
    interpreter = getattr(sys, '_base_executable', None) or sys.executable
    process = subprocess.Popen([interpreter, '-I', str(worker), suffix] + packages, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    close_job = lambda: None
    try:
        # The child blocks on stdin until its Windows limits are installed.
        if os.name == 'nt':
            close_job = windows_job(process)
        output, _ = process.communicate(data, timeout=8)
        if process.returncode or len(output) > 200000:
            return []
        result = json.loads(output).get('segments', [])
        if not isinstance(result, list) or len(result) > 15:
            return []
        return [{**s, 'tables': valid_tables(s.get('tables', []))} for s in result if isinstance(s, dict) and isinstance(s.get('text'), str) and (s.get('page') is None or isinstance(s.get('page'), int))]
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate()
        close_job()
