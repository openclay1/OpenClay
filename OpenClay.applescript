-- OpenClay.applescript
-- Minimal AppleScript wrapper for OpenClay.
-- All startup logic lives in launcher.sh (bundled at build time by create_app.sh).
-- on idle keeps the applet alive in the Dock so Cmd+Q / right-click Quit works.

on run
    set appDir to POSIX path of (path to me)
    set launcherPath to appDir & "Contents/Resources/launcher.sh"
    try
        do shell script "bash " & quoted form of launcherPath
    on error
        set msg to "OpenClay couldn't start." & return & return & "Make sure Ollama is installed and Python 3.10+ is available." & return & "Details: /tmp/openclay.log"
        display dialog msg buttons {"OK"} default button "OK" with icon stop with title "OpenClay"
    end try
end run

on idle
    -- Keeps the applet alive in the Dock between the run handler returning
    -- and the user quitting. Returns seconds before idle fires again.
    return 60
end idle

on quit
    -- Gracefully stop clay_server.py; leave Ollama running.
    try
        do shell script "if [ -f /tmp/openclay_server.pid ]; then kill \"$(cat /tmp/openclay_server.pid)\" 2>/dev/null || true; rm -f /tmp/openclay_server.pid; fi"
    end try
    continue quit
end quit
