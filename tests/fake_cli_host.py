"""Windows stand-in for the room-chat tests' fake ``claude`` binary.

Linux keeps a shebang script. Windows cannot ``CreateProcess`` that script
(``WinError 193``). Copying ``python.exe`` and importing a fake module from
a ``._pth`` file also fails: CPython rejects the runner's fixed ``-p`` in
``config_parse_cmdline`` before path config, ``site``, or ``sitecustomize``
runs, and a ``._pth`` file only honours the exact line ``import site``.

The stand-in is a tiny x64 console program (``STUB_EXE``) that waits briefly
so the runner can assign its kill-on-close Job, then starts

    python.exe -S -u <script> <the runner's argv[1:]>

with the same stdin, stdout, and stderr. ``-S`` skips a machine-wide
``sitecustomize``. The script records ``sys.argv`` after replacing ``argv[0]``
with the executable path from ``fake-claude.argv0``, which is the path the
runner launched. Rebuild ``STUB_EXE`` with the mingw command in ``STUB_C``.
"""

from __future__ import annotations

import base64
import hashlib
import os
import platform
import sys
from pathlib import Path

_STUB_SHA256 = "58f6af11ebea5ece835d6b39e6f65fa1bafe28d5e6def0905549690e3a89acce"
_STUB_B64 = """
TVqQAAMAAAAEAAAA//8AALgAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAgAAAAA4fug4AtAnNIbgBTM0hVGhpcyBwcm9ncmFtIGNhbm5vdCBiZSBydW4gaW4gRE9TIG1v
ZGUuDQ0KJAAAAAAAAABQRQAAZIYDABlmBGsAAAAAAAAAAPAALgILAgIpAAoAAAAGAAAAAAAAzBcA
AAAQAAAAAABAAQAAAAAQAAAAAgAABAAAAAAAAAAFAAIAAAAAAABAAAAABAAAMe0AAAMAYAEAACAA
AAAAAAAQAAAAAAAAAAAQAAAAAAAAEAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAMAAAgAMAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAA+DAAALgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAudGV4dAAA
AAAJAAAAEAAAAAoAAAAEAAAAAAAAAAAAAAAAAAAgAABgLnJkYXRhAACgAQAAACAAAAACAAAADgAA
AAAAAAAAAAAAAAAAQAAAQC5pZGF0YQAAgAMAAAAwAAAABAAAABAAAAAAAAAAAAAAAAAAAEAAAMAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
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
AOjD+f//SIuMJBgBAADotvn//0iLRCRYMdJMieGJVCQoRTHJRTHASInqSIlEJEAxwEyJbCRISIlE
JDhIiUQkMMdEJCABAAAA/xUKGgAASI0NIAoAAIXAD4RR/P//SIuMJAgBAABIjUH/SIP4/XcC/9ZI
i4wkEAEAAEiNQf9Ig/j9dwL/1kiLjCQYAQAASI1B/0iD+P13Av/Wg8r/SIuMJIAAAAD/FS4aAABI
i4wkgAAAAEiNVCR8/xW7GQAAhcB1CMdEJHwBAAAASIuMJIgAAAD/1kiLjCSAAAAA/9aLdCR8SItM
JFBJiegx0v8VrxkAAEiF23QQSItMJFBJidgx0v8VmhkAAEiBxEgJAACJ8FteX11BXEFdQV5BX8NX
McBWU0iD7DCJRCQs/xU5GQAASI1UJCxIicH/FbMZAABIiz0cGQAASIXAdAiLTCQshcl/E0iNDWYJ
AADoG/j//7kBAAAA6xhIicJIicPoNfr//0iJ2YnG/xU2GQAAifH/15CQ/yVaGQAAkJD/JUoZAACQ
kP8lOhkAAJCQ/yUqGQAAkJD/JRoZAACQkP8lChkAAJCQ/yX6GAAAkJD/JeoYAACQkP8l2hgAAJCQ
/yXKGAAAkJD/JboYAACQkP8lqhgAAJCQ/yWaGAAAkJD/JYoYAACQkP8lehgAAJCQ/yVqGAAAkJD/
JVoYAACQkP8lShgAAJCQ/yU6GAAAkJD/JSoYAACQkP8lyhgAAJCQDx+EAAAAAAD//////////wAA
AAAAAAAA//////////8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABcACIAAABm
YWtlLWNsYXVkZTogb3V0IG9mIG1lbW9yeQoAZmFrZS1jbGF1ZGU6IGNhbm5vdCBsb2NhdGUgaXRz
IG93biBwYXRoCgBmYWtlLWNsYXVkZTogcGF0aCBpcyB0b28gbG9uZwoAZmFrZS1jbGF1ZGU6IG1p
c3NpbmcgZmFrZS1jbGF1ZGUubGF1bmNoCgBmYWtlLWNsYXVkZTogbGF1bmNoIGZpbGUgaXMgbm90
IHV0Zi04CgBmYWtlLWNsYXVkZTogbGF1bmNoIGZpbGUgbmVlZHMgcHl0aG9uIGFuZCBzY3JpcHQg
cGF0aHMKAC0AUwAAAC0AdQAAAGZha2UtY2xhdWRlOiBjb21tYW5kIGxpbmUgaXMgdG9vIGxvbmcK
AGZha2UtY2xhdWRlOiBDcmVhdGVQcm9jZXNzIGZhaWxlZAoAZgBhAGsAZQAtAGMAbABhAHUAZABl
AC4AbABhAHUAbgBjAGgAAABmYWtlLWNsYXVkZTogY2Fubm90IHJlYWQgdGhlIGNvbW1hbmQgbGlu
ZQoAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEAwAAAAAAAA
AAAAAGAzAAD4MAAA6DAAAAAAAAAAAAAAdDMAAKAxAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACw
MQAAAAAAAL4xAAAAAAAAzDEAAAAAAADeMQAAAAAAAOwxAAAAAAAA/jEAAAAAAAASMgAAAAAAACgy
AAAAAAAAPjIAAAAAAABQMgAAAAAAAGAyAAAAAAAAbDIAAAAAAAB4MgAAAAAAAIoyAAAAAAAAljIA
AAAAAACsMgAAAAAAALgyAAAAAAAA0DIAAAAAAADYMgAAAAAAAO4yAAAAAAAAAAAAAAAAAAD6MgAA
AAAAAAAAAAAAAAAAsDEAAAAAAAC+MQAAAAAAAMwxAAAAAAAA3jEAAAAAAADsMQAAAAAAAP4xAAAA
AAAAEjIAAAAAAAAoMgAAAAAAAD4yAAAAAAAAUDIAAAAAAABgMgAAAAAAAGwyAAAAAAAAeDIAAAAA
AACKMgAAAAAAAJYyAAAAAAAArDIAAAAAAAC4MgAAAAAAANAyAAAAAAAA2DIAAAAAAADuMgAAAAAA
AAAAAAAAAAAA+jIAAAAAAAAAAAAAAAAAAI0AQ2xvc2VIYW5kbGUA1ABDcmVhdGVGaWxlVwDtAENy
ZWF0ZVByb2Nlc3NXAABsAUV4aXRQcm9jZXNzAOYBR2V0Q29tbWFuZExpbmVXACYCR2V0Q3VycmVu
dFByb2Nlc3MATgJHZXRFeGl0Q29kZVByb2Nlc3MAAIgCR2V0TW9kdWxlRmlsZU5hbWVXAADKAkdl
dFByb2Nlc3NIZWFwAADoAkdldFN0ZEhhbmRsZQAAXQNIZWFwQWxsb2MAYwNIZWFwRnJlZQAAnANJ
c1Byb2Nlc3NJbkpvYgAA6ANMb2NhbEZyZWUACgRNdWx0aUJ5dGVUb1dpZGVDaGFyAJAEUmVhZEZp
bGUAADAFU2V0SGFuZGxlSW5mb3JtYXRpb24AAH8FU2xlZXAA3AVXYWl0Rm9yU2luZ2xlT2JqZWN0
ABwGV3JpdGVGaWxlAAsAQ29tbWFuZExpbmVUb0FyZ3ZXAAAAMAAAADAAAAAwAAAAMAAAADAAAAAw
AAAAMAAAADAAAAAwAAAAMAAAADAAAAAwAAAAMAAAADAAAAAwAAAAMAAAADAAAAAwAAAAMAAAADAA
AEtFUk5FTDMyLmRsbAAAAAAUMAAAU0hFTEwzMi5kbGwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=
"""


class FakeCliUnsupported(RuntimeError):
    """This Windows machine cannot host the x64 fake executable."""


class DirectoryLinkError(OSError):
    """A directory symlink and the junction fallback both failed."""


def stub_exe() -> bytes:
    """The x64 launcher, checked against the hash baked in at build time."""
    raw = base64.b64decode("".join(_STUB_B64.split()))
    found = hashlib.sha256(raw).hexdigest()
    if found != _STUB_SHA256:
        raise FakeCliUnsupported("embedded fake-claude.exe hash does not match")
    return raw



# Source for STUB_EXE. Not compiled here; Windows test hosts have no C compiler.
STUB_C = r"""
/*
 * Console PE the room-chat tests launch on Windows instead of a shebang script.
 *
 * CreateProcess cannot run a script. CPython also rejects the runner's fixed
 * "-p" before site, sitecustomize, or a ._pth "import" line can run, so the
 * process image itself must not be python.exe. This stub waits until the
 * runner has had a chance to put it in a kill-on-close Job, then starts
 * python.exe -S -u <script> <original argv[1:]> with the same stdio handles.
 *
 * Rebuild (host with mingw-w64):
 *   x86_64-w64-mingw32-gcc -Os -s -nostartfiles -nostdlib -fno-stack-protector \
 *     -ffreestanding -fno-ident -fno-asynchronous-unwind-tables \
 *     -Wl,-e,mainCRTStartup -Wl,--subsystem,console \
 *     fake_cli_stub.c -o fake_cli_stub.exe -lkernel32 -lshell32
 *
 * Quote self-test on Linux (no Windows headers):
 *   gcc -DQUOTE_SELFTEST -O2 -Wall -Wextra fake_cli_stub.c -o quote_selftest
 */

#ifdef QUOTE_SELFTEST
#include <stdio.h>
#include <stdlib.h>
/* Compile the self-test with -fshort-wchar so L"" matches Windows UTF-16. */
typedef wchar_t WCHAR;
typedef unsigned int DWORD;
#define ExitProcess(code) exit(code)
#else
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#endif

#define CMDLINE_MAX 32767

static void memzero(void *ptr, unsigned int n) {
    unsigned char *bytes = (unsigned char *)ptr;
    while (n--) {
        *bytes++ = 0;
    }
}

static unsigned int cstr_len(const char *text) {
    unsigned int n = 0;
    while (text[n]) {
        n++;
    }
    return n;
}

static int append_char(WCHAR *dst, DWORD *len, WCHAR ch) {
    if (*len + 1 >= CMDLINE_MAX) {
        return 0;
    }
    dst[(*len)++] = ch;
    dst[*len] = 0;
    return 1;
}

static int append_n(WCHAR *dst, DWORD *len, WCHAR ch, DWORD count) {
    while (count--) {
        if (!append_char(dst, len, ch)) {
            return 0;
        }
    }
    return 1;
}

static int append_wstr(WCHAR *dst, DWORD *len, const WCHAR *text) {
    while (*text) {
        if (!append_char(dst, len, *text++)) {
            return 0;
        }
    }
    return 1;
}

/* Same rules as CPython subprocess.list2cmdline. */
static int append_arg(WCHAR *dst, DWORD *len, const WCHAR *arg, int first) {
    DWORD bs = 0;
    int needquote = (arg[0] == 0);
    const WCHAR *scan = arg;

    if (!first && !append_char(dst, len, L' ')) {
        return 0;
    }
    for (; *scan; scan++) {
        if (*scan == L' ' || *scan == L'\t') {
            needquote = 1;
            break;
        }
    }
    if (needquote && !append_char(dst, len, L'"')) {
        return 0;
    }
    for (; *arg; arg++) {
        if (*arg == L'\\') {
            bs++;
            continue;
        }
        if (*arg == L'"') {
            if (!append_n(dst, len, L'\\', bs * 2) || !append_wstr(dst, len, L"\\\"")) {
                return 0;
            }
            bs = 0;
            continue;
        }
        if (bs && !append_n(dst, len, L'\\', bs)) {
            return 0;
        }
        bs = 0;
        if (!append_char(dst, len, *arg)) {
            return 0;
        }
    }
    if (bs && !append_n(dst, len, L'\\', bs)) {
        return 0;
    }
    if (needquote) {
        /* Trailing backslashes are written again so they do not escape the quote. */
        if (!append_n(dst, len, L'\\', bs) || !append_char(dst, len, L'"')) {
            return 0;
        }
    }
    return 1;
}

#ifdef QUOTE_SELFTEST
static void to_wide(const char *text, WCHAR *dst) {
    while (*text) {
        *dst++ = (unsigned char)*text++;
    }
    *dst = 0;
}

int main(int argc, char **argv) {
    WCHAR wide[64][512];
    WCHAR cmdline[CMDLINE_MAX];
    DWORD len = 0;
    int i;
    cmdline[0] = 0;
    if (argc < 2 || argc > 64) {
        return 2;
    }
    for (i = 1; i < argc; i++) {
        to_wide(argv[i], wide[i]);
        if (!append_arg(cmdline, &len, wide[i], i == 1)) {
            return 3;
        }
    }
    fwrite(cmdline, sizeof(WCHAR), len, stdout);
    return 0;
}
#else

static void note(const char *text) {
    DWORD wrote = 0;
    HANDLE err = GetStdHandle(STD_ERROR_HANDLE);
    if (!err || err == INVALID_HANDLE_VALUE) {
        return;
    }
    WriteFile(err, text, cstr_len(text), &wrote, NULL);
}

static void wait_for_job(void) {
    BOOL in_job = FALSE;
    int i;
    /* The runner assigns the Job after CreateProcess returns. Spawn Python
     * only once this process is in a job, or after a short grace period when
     * it was already inside some other job (Terminal, an IDE). */
    if (!IsProcessInJob(GetCurrentProcess(), NULL, &in_job)) {
        Sleep(100);
        return;
    }
    if (in_job) {
        Sleep(100);
        return;
    }
    for (i = 0; i < 50; i++) {
        Sleep(10);
        in_job = FALSE;
        if (!IsProcessInJob(GetCurrentProcess(), NULL, &in_job) || in_job) {
            return;
        }
    }
}

static int read_all(const WCHAR *path, char *buf, DWORD cap, DWORD *out_len) {
    HANDLE file;
    DWORD read = 0;
    file = CreateFileW(path, GENERIC_READ,
                       FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                       NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) {
        return 0;
    }
    if (!ReadFile(file, buf, cap - 1, &read, NULL)) {
        CloseHandle(file);
        return 0;
    }
    CloseHandle(file);
    buf[read] = 0;
    *out_len = read;
    return 1;
}

static WCHAR *skip_line(char *line, WCHAR *dst, DWORD cap) {
    char *end = line;
    int chars;
    while (*end && *end != '\n' && *end != '\r') {
        end++;
    }
    *end = 0;
    chars = MultiByteToWideChar(CP_UTF8, 0, line, -1, dst, (int)cap);
    if (chars <= 0) {
        return NULL;
    }
    return dst;
}

static void inherit(HANDLE handle) {
    if (!handle || handle == INVALID_HANDLE_VALUE) {
        return;
    }
    SetHandleInformation(handle, HANDLE_FLAG_INHERIT, HANDLE_FLAG_INHERIT);
}

static int run(int argc, WCHAR **argv) {
    WCHAR self[MAX_PATH];
    WCHAR launch_path[MAX_PATH];
    WCHAR python[MAX_PATH];
    WCHAR script[MAX_PATH];
    WCHAR *cmdline;
    char *raw;
    char *second;
    DWORD self_len;
    DWORD raw_len = 0;
    DWORD cmd_len = 0;
    DWORD exit_code = 1;
    int i;
    int status = 1;
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    const WCHAR *fixed[4];
    HANDLE heap = GetProcessHeap();

    cmdline = (WCHAR *)HeapAlloc(heap, HEAP_ZERO_MEMORY, CMDLINE_MAX * sizeof(WCHAR));
    raw = (char *)HeapAlloc(heap, HEAP_ZERO_MEMORY, 8192);
    if (!cmdline || !raw) {
        note("fake-claude: out of memory\n");
        goto done;
    }

    self_len = GetModuleFileNameW(NULL, self, MAX_PATH);
    if (!self_len || self_len >= MAX_PATH) {
        note("fake-claude: cannot locate its own path\n");
        goto done;
    }
    while (self_len && self[self_len - 1] != L'\\' && self[self_len - 1] != L'/') {
        self_len--;
    }
    if (!self_len || self_len + 20 >= MAX_PATH) {
        note("fake-claude: path is too long\n");
        goto done;
    }
    memzero(launch_path, sizeof(launch_path));
    for (i = 0; i < (int)self_len; i++) {
        launch_path[i] = self[i];
    }
    {
        const WCHAR suffix[] = L"fake-claude.launch";
        int pos = (int)self_len;
        for (i = 0; suffix[i]; i++) {
            launch_path[pos++] = suffix[i];
        }
        launch_path[pos] = 0;
    }
    if (!read_all(launch_path, raw, 8192, &raw_len)) {
        note("fake-claude: missing fake-claude.launch\n");
        goto done;
    }
    second = raw;
    while (*second && *second != '\n' && *second != '\r') {
        second++;
    }
    if (*second == '\r') {
        *second++ = 0;
    }
    if (*second == '\n') {
        second++;
    }
    if (!skip_line(raw, python, MAX_PATH) || !skip_line(second, script, MAX_PATH)) {
        note("fake-claude: launch file is not utf-8\n");
        goto done;
    }
    if (!python[0] || !script[0]) {
        note("fake-claude: launch file needs python and script paths\n");
        goto done;
    }

    wait_for_job();

    fixed[0] = python;
    fixed[1] = L"-S";
    fixed[2] = L"-u";
    fixed[3] = script;
    cmdline[0] = 0;
    for (i = 0; i < 4; i++) {
        if (!append_arg(cmdline, &cmd_len, fixed[i], i == 0)) {
            note("fake-claude: command line is too long\n");
            goto done;
        }
    }
    for (i = 1; i < argc; i++) {
        if (!append_arg(cmdline, &cmd_len, argv[i], 0)) {
            note("fake-claude: command line is too long\n");
            goto done;
        }
    }

    memzero(&si, sizeof(si));
    memzero(&pi, sizeof(pi));
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESTDHANDLES;
    si.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
    si.hStdOutput = GetStdHandle(STD_OUTPUT_HANDLE);
    si.hStdError = GetStdHandle(STD_ERROR_HANDLE);
    inherit(si.hStdInput);
    inherit(si.hStdOutput);
    inherit(si.hStdError);

    if (!CreateProcessW(python, cmdline, NULL, NULL, TRUE, 0, NULL, NULL, &si, &pi)) {
        note("fake-claude: CreateProcess failed\n");
        goto done;
    }
    /* Python inherited duplicates. Drop ours so its stdin read sees EOF
     * when the runner closes the pipe, instead of waiting on this process. */
    if (si.hStdInput && si.hStdInput != INVALID_HANDLE_VALUE) {
        CloseHandle(si.hStdInput);
    }
    if (si.hStdOutput && si.hStdOutput != INVALID_HANDLE_VALUE) {
        CloseHandle(si.hStdOutput);
    }
    if (si.hStdError && si.hStdError != INVALID_HANDLE_VALUE) {
        CloseHandle(si.hStdError);
    }
    WaitForSingleObject(pi.hProcess, INFINITE);
    if (!GetExitCodeProcess(pi.hProcess, &exit_code)) {
        exit_code = 1;
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    status = (int)exit_code;
done:
    if (cmdline) {
        HeapFree(heap, 0, cmdline);
    }
    if (raw) {
        HeapFree(heap, 0, raw);
    }
    return status;
}

void mainCRTStartup(void) {
    int argc = 0;
    WCHAR **argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    int code;
    if (!argv || argc < 1) {
        note("fake-claude: cannot read the command line\n");
        ExitProcess(1);
    }
    code = run(argc, argv);
    LocalFree(argv);
    ExitProcess((UINT)code);
}

#endif

"""

FAKE_CLI = """\
#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# The Windows launcher is not Python, so argv[0] would otherwise be this
# script. The file is absent on Linux and the shebang script keeps the
# path the runner passed.
_argv0 = Path(__file__).resolve().with_name("fake-claude.argv0")
try:
    _text = _argv0.read_text(encoding="utf-8")
except OSError:
    _text = ""
if _text.strip("\\r\\n"):
    sys.argv[0] = _text.strip("\\r\\n")

ROOT = Path.cwd()
mode = (ROOT / "fake-cli-mode.txt").read_text(encoding="utf-8").strip()


def record() -> None:
    payload = {
        "argv": sys.argv,
        "cwd": os.getcwd(),
        "env_names": sorted(os.environ),
        "stdin": sys.stdin.read(),
    }
    (ROOT / "fake-cli-record.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    sys.stdout.write('{"type":"result","ok":true}\\n')
    sys.stdout.flush()


if mode == "record":
    record()
elif mode == "sleep":
    (ROOT / "parent.pid").write_text(str(os.getpid()), encoding="utf-8")
    time.sleep(60)
elif mode == "flood":
    line = b"x" * 200 + b"\\n"
    for _ in range(100000):
        sys.stdout.buffer.write(line)
        sys.stdout.buffer.flush()
    time.sleep(60)
elif mode == "flood-err":
    line = b"e" * 200 + b"\\n"
    for _ in range(100000):
        sys.stderr.buffer.write(line)
        sys.stderr.buffer.flush()
    time.sleep(60)
elif mode == "stderr-secret":
    sys.stderr.write("token=super-secret-value api_key=abcdefghi sk-secretvalue\\n")
    sys.stdout.write("ok\\n")
    sys.stdout.flush()
elif mode == "child":
    code = (
        "import os,time,pathlib; "
        "pathlib.Path('child.pid').write_text(str(os.getpid()), encoding='utf-8'); "
        "time.sleep(60)"
    )
    # -S keeps a machine sitecustomize from printing or exiting the grandchild.
    subprocess.Popen([sys.executable, "-S", "-c", code], cwd=str(ROOT))
    deadline = time.time() + 5
    while time.time() < deadline and not (ROOT / "child.pid").exists():
        time.sleep(0.02)
    (ROOT / "parent.pid").write_text(str(os.getpid()), encoding="utf-8")
    (ROOT / "ready").write_text("1", encoding="utf-8")
    time.sleep(60)
elif mode == "orphan":
    sys.stdout.write('{"type":"assistant"}\\n')
    sys.stdout.flush()
    code = (
        "import os,time,pathlib; "
        "pathlib.Path('child.pid').write_text(str(os.getpid()), encoding='utf-8'); "
        "pathlib.Path('ready').write_text('1', encoding='utf-8'); "
        "time.sleep(60)"
    )
    subprocess.Popen([sys.executable, "-S", "-c", code], cwd=str(ROOT))
    deadline = time.time() + 5
    while time.time() < deadline and not (ROOT / "ready").exists():
        time.sleep(0.02)
    (ROOT / "parent.pid").write_text(str(os.getpid()), encoding="utf-8")
else:
    sys.stderr.write("bad mode\\n")
    sys.exit(2)
"""


def install_fake_cli(root: Path) -> Path:
    """Write the fake CLI and return the path the runner should launch.

    On Windows this is ``fake-claude.exe``. On every other platform it is
    the shebang script the suite has always used.
    """
    if sys.platform != "win32":
        script = root / "fake-claude"
        script.write_text(FAKE_CLI, encoding="utf-8", newline="\n")
        script.chmod(0o755)
        return script
    machine = platform.machine().lower()
    if machine not in {"amd64", "x86_64"}:
        raise FakeCliUnsupported(
            "the Windows fake CLI executable is built for x64, not "
            + (platform.machine() or "an unknown architecture")
        )
    exe = root / "fake-claude.exe"
    script = root / "fake-claude-script.py"
    script.write_text(FAKE_CLI, encoding="utf-8", newline="\n")
    python = str(Path(sys.executable).resolve())
    script_path = str(script.resolve())
    # The launcher's buffers are MAX_PATH characters, including the NUL.
    if len(python) >= 260 or len(script_path) >= 260:
        raise FakeCliUnsupported(
            "Python or the fake script path is longer than MAX_PATH, "
            "so the test launcher cannot start it"
        )
    exe.write_bytes(stub_exe())
    launch = root / "fake-claude.launch"
    launch.write_text(python + "\n" + script_path + "\n", encoding="utf-8", newline="\n")
    (root / "fake-claude.argv0").write_text(str(exe.resolve()), encoding="utf-8", newline="\n")
    return exe


def write_cmd_shim(path: Path, target: Path) -> None:
    """Write a ``.cmd`` the runner can start.

    Windows ``CreateProcess`` runs a real batch file through ``cmd.exe``.
    The batch calls ``target`` and forwards the runner's fixed flags.
    Other platforms keep the shebang script, which ``execve`` can run
    whatever the suffix is.
    """
    if sys.platform != "win32":
        path.write_text(FAKE_CLI, encoding="utf-8", newline="\n")
        path.chmod(0o755)
        return
    exe = str(target)
    text = '@echo off\r\n"{}" %*\r\n'.format(exe)
    try:
        data = text.encode("ascii")
    except UnicodeEncodeError:
        data = text.encode("mbcs")
    path.write_bytes(data)


def link_directory(link: Path, target: Path) -> None:
    """Point ``link`` at the directory ``target``.

    Tries ``os.symlink(..., target_is_directory=True)``. When Windows
    refuses that with ``WinError 1314`` (no symlink privilege, and not
    running as admin), falls back to a directory junction. Raises
    ``DirectoryLinkError`` only when both fail.
    """
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except OSError as exc:
        if getattr(exc, "winerror", None) != 1314:
            raise
    if sys.platform != "win32":
        raise
    try:
        import _winapi

        # src is the existing directory; dst is the junction to create.
        _winapi.CreateJunction(os.fspath(target), os.fspath(link))
    except OSError as exc:
        raise DirectoryLinkError(
            "directory symlink needs SeCreateSymbolicLinkPrivilege "
            "(WinError 1314) and CreateJunction failed: " + str(exc)
        ) from exc
