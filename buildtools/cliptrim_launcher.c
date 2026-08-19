#define UNICODE
#define _UNICODE

#include <windows.h>
#include <shellapi.h>
#include <stddef.h>
#include <wchar.h>

static int append_char(wchar_t **cursor, size_t *remaining, wchar_t value) {
    if (*remaining <= 1) {
        return 0;
    }
    **cursor = value;
    *cursor += 1;
    *remaining -= 1;
    **cursor = L'\0';
    return 1;
}

static int append_quoted_arg(wchar_t **cursor, size_t *remaining, const wchar_t *arg) {
    size_t backslashes = 0;
    if (!append_char(cursor, remaining, L'"')) {
        return 0;
    }

    for (; *arg; ++arg) {
        if (*arg == L'\\') {
            backslashes += 1;
            continue;
        }
        if (*arg == L'"') {
            for (size_t i = 0; i < backslashes * 2 + 1; ++i) {
                if (!append_char(cursor, remaining, L'\\')) {
                    return 0;
                }
            }
            if (!append_char(cursor, remaining, L'"')) {
                return 0;
            }
        } else {
            for (size_t i = 0; i < backslashes; ++i) {
                if (!append_char(cursor, remaining, L'\\')) {
                    return 0;
                }
            }
            if (!append_char(cursor, remaining, *arg)) {
                return 0;
            }
        }
        backslashes = 0;
    }

    for (size_t i = 0; i < backslashes * 2; ++i) {
        if (!append_char(cursor, remaining, L'\\')) {
            return 0;
        }
    }
    return append_char(cursor, remaining, L'"');
}

static int fail_with_last_error(const wchar_t *message) {
    wchar_t detail[768];
    DWORD error = GetLastError();
    _snwprintf_s(detail, 768, _TRUNCATE, L"%ls\n\nWindows error: %lu", message, error);
    MessageBoxW(NULL, detail, L"ClipTrim", MB_OK | MB_ICONERROR);
    return 1;
}

int WINAPI WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR command_line, int show_command) {
    (void)instance;
    (void)previous;
    (void)command_line;
    (void)show_command;

    wchar_t root[32768];
    DWORD length = GetModuleFileNameW(NULL, root, 32768);
    if (length == 0 || length >= 32768) {
        return fail_with_last_error(L"Could not resolve the ClipTrim folder.");
    }

    wchar_t *separator = wcsrchr(root, L'\\');
    if (separator == NULL) {
        SetLastError(ERROR_BAD_PATHNAME);
        return fail_with_last_error(L"Could not resolve the ClipTrim folder.");
    }
    *separator = L'\0';

    wchar_t target[32768];
    int target_length = _snwprintf_s(
        target,
        32768,
        _TRUNCATE,
        L"%ls\\runtime\\ClipTrim.runtime.exe",
        root
    );
    if (target_length < 0 || GetFileAttributesW(target) == INVALID_FILE_ATTRIBUTES) {
        SetLastError(ERROR_FILE_NOT_FOUND);
        return fail_with_last_error(L"ClipTrim.runtime.exe was not found in the runtime folder.");
    }

    int argc = 0;
    wchar_t **argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    if (argv == NULL) {
        return fail_with_last_error(L"Could not read the ClipTrim command line.");
    }

    size_t command_capacity = wcslen(target) * 2 + 4;
    for (int i = 1; i < argc; ++i) {
        command_capacity += wcslen(argv[i]) * 2 + 5;
    }
    wchar_t *child_command = HeapAlloc(
        GetProcessHeap(),
        HEAP_ZERO_MEMORY,
        command_capacity * sizeof(wchar_t)
    );
    if (child_command == NULL) {
        LocalFree(argv);
        SetLastError(ERROR_NOT_ENOUGH_MEMORY);
        return fail_with_last_error(L"Could not allocate the ClipTrim command line.");
    }

    wchar_t *cursor = child_command;
    size_t remaining = command_capacity;
    int command_ok = append_quoted_arg(&cursor, &remaining, target);
    for (int i = 1; command_ok && i < argc; ++i) {
        command_ok = append_char(&cursor, &remaining, L' ')
            && append_quoted_arg(&cursor, &remaining, argv[i]);
    }
    LocalFree(argv);
    if (!command_ok) {
        HeapFree(GetProcessHeap(), 0, child_command);
        SetLastError(ERROR_INSUFFICIENT_BUFFER);
        return fail_with_last_error(L"The ClipTrim command line was too long.");
    }

    // The launcher is a GUI-subsystem executable, so Explorer creates no
    // console. When launched from PowerShell/cmd, attach to that console so
    // the Nuitka child can retain attach-console logging and Ctrl+C behavior.
    AttachConsole(ATTACH_PARENT_PROCESS);

    STARTUPINFOW startup = {0};
    PROCESS_INFORMATION process = {0};
    startup.cb = sizeof(startup);
    BOOL started = CreateProcessW(
        target,
        child_command,
        NULL,
        NULL,
        TRUE,
        0,
        NULL,
        root,
        &startup,
        &process
    );
    HeapFree(GetProcessHeap(), 0, child_command);
    if (!started) {
        return fail_with_last_error(L"Could not start ClipTrim from its runtime folder.");
    }

    CloseHandle(process.hThread);
    WaitForSingleObject(process.hProcess, INFINITE);
    DWORD exit_code = 1;
    GetExitCodeProcess(process.hProcess, &exit_code);
    CloseHandle(process.hProcess);
    return (int)exit_code;
}
