import win32gui
import win32api
import win32ts
import tkinter as tk

class WindowsPowerMonitor:
    """Classe para observar eventos de energia do Windows em apps Tkinter."""
    
    WM_WTSSESSION_CHANGE = 0x02B1
    WTS_SESSION_LOCK = 0x7
    WTS_SESSION_UNLOCK = 0x8

    def __init__(self, root):
        self.root = root
        self.is_suspended = False  # Estado de suspensão
        self.poll_after_id = None
        self.is_stopped = False
        
        # Criar a janela oculta para capturar as mensagens do SO
        self._create_hidden_window()
        
        # Iniciar o loop de verificação integrado ao mainloop do Tkinter
        self._poll_messages()

    def _create_hidden_window(self):
        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = self._wndproc
        wc.lpszClassName = f"PowerWatcher_{id(self)}" # Nome único
        hinst = wc.hInstance = win32api.GetModuleHandle(None)
        class_atom = win32gui.RegisterClass(wc)
        self.hwnd = win32gui.CreateWindow(
            class_atom, "Watcher", 0, 0, 0, 0, 0, 0, 0, hinst, None
        )
        win32ts.WTSRegisterSessionNotification(self.hwnd, win32ts.NOTIFY_FOR_THIS_SESSION)

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == self.WM_WTSSESSION_CHANGE:
            if wparam == self.WTS_SESSION_LOCK:
                self.is_suspended = True
                print("Windows foi suspenso")
            elif wparam == self.WTS_SESSION_UNLOCK:
                self.is_suspended = False
                print("Windows acordou")

        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def _poll_messages(self):
        """Verifica mensagens pendentes sem bloquear a UI."""
        if self.is_stopped:
            return
        win32gui.PumpWaitingMessages()
        self.poll_after_id = self.root.after(500, self._poll_messages)

    def stop(self):
        """Para o monitor e libera a janela oculta do Windows."""
        if self.is_stopped:
            return

        self.is_stopped = True
        if self.poll_after_id is not None:
            self.root.after_cancel(self.poll_after_id)
            self.poll_after_id = None
        win32ts.WTSUnRegisterSessionNotification(self.hwnd)
        win32gui.DestroyWindow(self.hwnd)

    