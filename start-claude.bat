@echo off
setlocal EnableExtensions

echo Starting Claude Code...
echo.
echo If this is your first time, you'll need to authenticate.
echo.
echo Launching Claude Code...
echo ========================================
echo.

set "CLAUDE_BIN=%USERPROFILE%\.local\bin\claude.exe"
if exist "%CLAUDE_BIN%" goto run_native

echo Native claude not found at %CLAUDE_BIN%
echo Falling back to npx - may fail behind Norton SSL inspection...
npx @anthropic-ai/claude-code %*
goto end

:run_native
"%CLAUDE_BIN%" %*

:end
endlocal
