# Putting Saphal Book on a Windows computer

## Once, on each computer

1. Install Python from <https://www.python.org/downloads/>. During
   installation tick the box that says **Add Python to PATH**. This is the only
   thing that ever needs installing, and it is free.

2. Copy the whole **Saphal Book** folder onto the computer. Somewhere
   sensible, such as `C:\Saphal Book`. Do not put it in OneDrive, because
   OneDrive syncing a file that is being written to can corrupt it. Backups can
   go to OneDrive, the books themselves should not.

3. Open the folder and double click **Saphal Book.vbs**. The browser opens
   at the books. No black console window appears.

4. Right click **Saphal Book.vbs**, choose **Send to**, then **Desktop
   (create shortcut)**. Now it opens from the desktop.

   To give the shortcut the proper icon: right click the shortcut,
   **Properties**, **Change Icon**, then **Browse**, and pick
   `chartered_book\web\static\icons\icon-192.png`. If Windows will not accept a
   PNG, leave the default icon.

## Putting it on the taskbar

Open Saphal Book, then in Edge or Chrome open the menu and choose
**Install Saphal Book** or **Apps, Install this site as an app**. It then
has its own window and its own icon, and can be pinned to the taskbar like any
other program.

## The books

The books are kept in:

    C:\Users\<your name>\AppData\Local\Saphal Book

Backups go in the `backups` folder inside that. On the Backup and safety screen
you can name a second folder, such as your Google Drive or OneDrive folder, and
every backup is copied there as well.

## Stopping it

Saphal Book keeps running quietly after you close the browser, so it is
ready the next time. To stop it fully, open Task Manager, find **Python** or
**pythonw**, and end it. Or restart the computer.
