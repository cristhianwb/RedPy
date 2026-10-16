import pystray
from PIL import Image, ImageDraw
import tkinter as tk
import sys
import os

class TrayIcon:
    """Gerenciador de ícone de bandeja para a aplicação."""
    
    def __init__(self, root, app):
        self.root = root
        self.app = app
        self.icon = None
        self.is_visible = True
        
        # Criar ícone
        self._create_icon()

    def get_resource_path(self, relative_path):
        """ Retorna o caminho absoluto do recurso, funciona para dev e para PyInstaller """
        if hasattr(sys, '_MEIPASS'):
            return os.path.join(sys._MEIPASS, relative_path)
        return os.path.join(os.path.abspath("."), 'icon', relative_path)
    
    def _create_icon(self):
        """Cria um ícone com relógio usando Pillow."""
        
        icon_path = self.get_resource_path("relogio.ico")
        img = Image.open(icon_path)
        
        # Criar menu de contexto
        menu = pystray.Menu(
            pystray.MenuItem("Mostrar", self._toggle_window),
            pystray.MenuItem("Ocultar", self._hide_window),
            pystray.MenuItem("Sair", self._quit_app)
        )
        
        self.icon = pystray.Icon("RedPy", img, "RedPy - Gestor de Horas", menu)
    
    def _toggle_window(self, icon=None, item=None):
        """Mostra ou oculta a janela."""
        if self.is_visible:
            self._hide_window()
        else:
            self._show_window()
    
    def _show_window(self, icon=None, item=None):
        """Mostra a janela principal."""
        self.root.deiconify()
        self.root.lift()
        self.root.focus()
        self.is_visible = True
    
    def _hide_window(self, icon=None, item=None):
        """Oculta a janela para a bandeja."""
        self.root.withdraw()
        self.is_visible = False
    
    def _quit_app(self, icon=None, item=None):
        """Fecha a aplicação."""
        self.root.after(0, self.app.close_application)
    
    def run(self):
        """Inicia o ícone de bandeja."""
        self.icon.run()
    
    def stop(self):
        """Para o ícone de bandeja."""
        if self.icon:
            self.icon.stop()
