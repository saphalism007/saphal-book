' Opens Chartered Book on Windows.
'
' Double click this file. No black console window appears. Anything the
' software wants to say is written to the log file in its data folder.
'
' To keep it to hand: right click this file, Send to, Desktop (create
' shortcut). Then right click the shortcut, Properties, Change Icon, and
' choose chartered_book\web\static\icons\icon-192.png if Windows offers it,
' or leave the default.

Option Explicit

Dim shell, fso, here, python, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

here = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = here

' pythonw runs without a console window. Plain python is the fallback.
python = FindPython(shell, fso)

If python = "" Then
    MsgBox "Python 3 was not found on this computer." & vbCrLf & vbCrLf & _
           "Install it free from python.org and tick the box that says" & vbCrLf & _
           "Add Python to PATH during installation. Then open Chartered Book again.", _
           vbExclamation, "Chartered Book"
    WScript.Quit 1
End If

command = """" & python & """ start.py --app --lan"
' The 0 hides the window. The False means do not wait for it to finish.
shell.Run command, 0, False

Function FindPython(sh, f)
    Dim candidates, candidate, found, localApp
    found = ""
    localApp = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%")

    ' Prefer pythonw, which has no console window of its own.
    candidates = Array( _
        localApp & "\Programs\Python\Python313\pythonw.exe", _
        localApp & "\Programs\Python\Python312\pythonw.exe", _
        localApp & "\Programs\Python\Python311\pythonw.exe", _
        localApp & "\Programs\Python\Python310\pythonw.exe", _
        "C:\Python313\pythonw.exe", _
        "C:\Python312\pythonw.exe", _
        "C:\Python311\pythonw.exe", _
        "C:\Program Files\Python313\pythonw.exe", _
        "C:\Program Files\Python312\pythonw.exe", _
        "C:\Program Files\Python311\pythonw.exe")

    For Each candidate In candidates
        If f.FileExists(candidate) Then
            FindPython = candidate
            Exit Function
        End If
    Next

    ' Then whatever is on the path.
    found = WhichOnPath(sh, f, "pythonw.exe")
    If found <> "" Then
        FindPython = found
        Exit Function
    End If
    found = WhichOnPath(sh, f, "python.exe")
    FindPython = found
End Function

Function WhichOnPath(sh, f, name)
    Dim parts, part, full
    WhichOnPath = ""
    parts = Split(sh.ExpandEnvironmentStrings("%PATH%"), ";")
    For Each part In parts
        If Len(Trim(part)) > 0 Then
            full = Trim(part)
            If Right(full, 1) <> "\" Then full = full & "\"
            full = full & name
            If f.FileExists(full) Then
                WhichOnPath = full
                Exit Function
            End If
        End If
    Next
End Function
