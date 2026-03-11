#build file for PyInstaller
import PyInstaller.__main__ 

PyInstaller.__main__.run([
    'run_ui.py', #runs ui
    '--windowed', #boots windowed
    '--name=D.I.A.D', #name of app
    '--hidden-import=tkinter', #tkiner needs a hidden import, pyinstaller doesn't see it on its own
])