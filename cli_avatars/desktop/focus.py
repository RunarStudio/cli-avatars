"""Focus the terminal that owns an avatar, or this process console.

``focus_console`` is unused. It stays until SPLIT.5. Both functions are
Windows ctypes. A failure is swallowed so a click still does nothing harmful.
"""

import ctypes


def _focus_console(self):
    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 5)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
    except Exception as e:
        print(f"[overlay] focus_console: {e}")


def _focus_linked_console(self, pid: int):
    try:
        import os, ctypes.wintypes
        candidates: set[int] = set()
        has_vscode = False

        seed = pid if pid else os.getpid()

        # Try psutil first; fall back to ctypes CreateToolhelp32Snapshot
        try:
            import psutil
            try:
                p = psutil.Process(seed)
                for _ in range(12):
                    candidates.add(p.pid)
                    if 'code' in (p.name() or '').lower():
                        has_vscode = True
                    p = p.parent()
                    if p is None:
                        break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            if has_vscode:
                for proc in psutil.process_iter(['pid', 'name']):
                    if (proc.info['name'] or '').lower() == 'code.exe':
                        candidates.add(proc.info['pid'])
        except ImportError:
            # ctypes fallback: walk parent chain via CreateToolhelp32Snapshot
            class PROCESSENTRY32(ctypes.Structure):
                _fields_ = [("dwSize", ctypes.c_ulong), ("cntUsage", ctypes.c_ulong),
                             ("th32ProcessID", ctypes.c_ulong), ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                             ("th32ModuleID", ctypes.c_ulong), ("cntThreads", ctypes.c_ulong),
                             ("th32ParentProcessID", ctypes.c_ulong), ("pcPriClassBase", ctypes.c_long),
                             ("dwFlags", ctypes.c_ulong), ("szExeFile", ctypes.c_char * 260)]
            snap = ctypes.windll.kernel32.CreateToolhelp32Snapshot(0x2, 0)
            parents, names = {}, {}
            e = PROCESSENTRY32(); e.dwSize = ctypes.sizeof(PROCESSENTRY32)
            if ctypes.windll.kernel32.Process32First(snap, ctypes.byref(e)):
                while True:
                    parents[e.th32ProcessID] = e.th32ParentProcessID
                    names[e.th32ProcessID] = e.szExeFile.decode('utf-8', errors='ignore').lower()
                    if not ctypes.windll.kernel32.Process32Next(snap, ctypes.byref(e)):
                        break
            ctypes.windll.kernel32.CloseHandle(snap)
            p = seed
            for _ in range(12):
                if p not in parents: break
                candidates.add(p)
                if 'code' in names.get(p, ''): has_vscode = True
                p = parents[p]

        found_hwnd: list = []
        WNDENUMPROC = ctypes.WINFUNCTYPE(
            ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

        def _cb(hwnd, _):
            wpid = ctypes.c_ulong(0)
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
            if wpid.value in candidates and ctypes.windll.user32.IsWindowVisible(hwnd):
                if ctypes.windll.user32.GetWindowTextLengthW(hwnd) > 0:
                    found_hwnd.append(hwnd)
            return True

        ctypes.windll.user32.EnumWindows(WNDENUMPROC(_cb), 0)

        if found_hwnd:
            hwnd = found_hwnd[0]
            if ctypes.windll.user32.IsIconic(hwnd):
                ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE only if minimized
            # AttachThreadInput bypasses Windows foreground-stealing prevention
            cur_thread = ctypes.windll.kernel32.GetCurrentThreadId()
            tgt_thread = ctypes.windll.user32.GetWindowThreadProcessId(hwnd, None)
            ctypes.windll.user32.AttachThreadInput(cur_thread, tgt_thread, True)
            ctypes.windll.user32.BringWindowToTop(hwnd)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            ctypes.windll.user32.AttachThreadInput(cur_thread, tgt_thread, False)
    except Exception:
        pass


def focus_console():
    return _focus_console(None)


def focus_linked_console(pid):
    return _focus_linked_console(None, pid)
