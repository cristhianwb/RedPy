import os
import pickle
import tkinter as tk
from tkinter import messagebox

import win32crypt
from redminelib import Redmine
from redminelib.exceptions import AuthError

CONFIG_FILE = 'config.pkl'


def load_config():
    """Lê URL e chave salvas em config.pkl. Retorna (url, api_key); cada um pode ser None."""
    try:
        with open(CONFIG_FILE, 'rb') as arquivo:
            config = pickle.load(arquivo)
    except (FileNotFoundError, EOFError, pickle.UnpicklingError):
        return None, None
    if not isinstance(config, dict):
        return None, None

    url = config.get('url')
    api_key = None
    try:
        # A chave é cifrada com DPAPI: só o mesmo usuário do Windows consegue decifrar
        _, data = win32crypt.CryptUnprotectData(config['api_key'], None, None, None, 0)
        api_key = data.decode('utf-8')
    except KeyError:
        pass
    except Exception as e:
        print(f"Não foi possível ler a chave salva: {type(e).__name__}")
    return url, api_key


def save_config(url, api_key):
    """Salva a URL e a chave (cifrada com DPAPI) em config.pkl."""
    encrypted = win32crypt.CryptProtectData(api_key.encode('utf-8'), 'RedPy', None, None, None, 0)
    with open(CONFIG_FILE, 'wb') as arquivo:
        pickle.dump({'url': url, 'api_key': encrypted}, arquivo)


def delete_config():
    """Remove a configuração salva."""
    try:
        os.remove(CONFIG_FILE)
    except FileNotFoundError:
        pass


def normalize_url(url):
    url = url.strip()
    if url and not url.endswith('/'):
        url += '/'
    return url


def validate_api_key(url, api_key):
    """Retorna True se a chave for aceita, False se o Redmine recusar.
    Erros de rede/URL são repassados para quem chamou."""
    try:
        Redmine(url, key=api_key).user.get('current')
        return True
    except AuthError:
        return False


class ApiKeyDialog(tk.Toplevel):
    """Diálogo para informar a URL do Redmine e a chave de API."""

    def __init__(self, parent, url=None, api_key=None, message=None):
        super().__init__(parent)
        self.result = None
        self.title("RedPy - Conexão com o Redmine")
        self.resizable(False, False)
        # Não usa transient(): a janela principal fica oculta até a chave ser validada
        self.attributes('-topmost', True)
        self.grab_set()

        tk.Label(
            self,
            text=message or "Informe a URL do Redmine e sua chave de API.",
            justify="left"
        ).grid(row=0, column=0, padx=10, pady=(10, 6), sticky="w")

        tk.Label(self, text="URL do Redmine:").grid(row=1, column=0, padx=10, sticky="w")
        self.url_entry = tk.Entry(self, width=48)
        self.url_entry.insert(0, url or "https://")
        self.url_entry.grid(row=2, column=0, padx=10, sticky="ew")

        tk.Label(self, text="Chave de API:").grid(row=3, column=0, padx=10, pady=(8, 0), sticky="w")
        tk.Label(
            self,
            text="Onde encontrar: Minha conta > Chave de acesso à API",
            font=("Segoe UI", 8),
            fg="#555"
        ).grid(row=4, column=0, padx=10, sticky="w")
        self.key_entry = tk.Entry(self, width=48, show="*")
        if api_key:
            self.key_entry.insert(0, api_key)
        self.key_entry.grid(row=5, column=0, padx=10, sticky="ew")
        self.key_entry.bind("<Return>", lambda event: self.confirm())

        self.show_key = tk.BooleanVar(value=False)
        tk.Checkbutton(
            self,
            text="Mostrar chave",
            variable=self.show_key,
            command=self._toggle_show
        ).grid(row=6, column=0, padx=6, sticky="w")

        buttons = tk.Frame(self)
        buttons.grid(row=7, column=0, padx=10, pady=10, sticky="e")
        tk.Button(buttons, text="OK", command=self.confirm).pack(side="left", padx=4)
        tk.Button(buttons, text="Cancelar", command=self.cancel).pack(side="left")

        self.protocol("WM_DELETE_WINDOW", self.cancel)
        (self.key_entry if url else self.url_entry).focus_set()
        self._center_on_screen()

    def _center_on_screen(self):
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() - width) // 2
        y = (self.winfo_screenheight() - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _toggle_show(self):
        self.key_entry.config(show="" if self.show_key.get() else "*")

    def confirm(self):
        url = normalize_url(self.url_entry.get())
        api_key = self.key_entry.get().strip()
        if not url.startswith(("https://", "http://")) or url in ("https://", "http://"):
            messagebox.showerror("URL inválida", "Informe a URL completa, ex.: https://redmine.suaempresa.com/", parent=self)
            return
        if not api_key:
            messagebox.showerror("Chave inválida", "Informe a chave de API.", parent=self)
            return

        self.config(cursor="watch")
        self.update_idletasks()
        try:
            is_valid = validate_api_key(url, api_key)
        except Exception as e:
            messagebox.showerror(
                "Falha de conexão",
                f"Não foi possível validar a chave no Redmine ({type(e).__name__}).\n"
                "Verifique a URL, a conexão/VPN e tente novamente.",
                parent=self
            )
            return
        finally:
            self.config(cursor="")

        if not is_valid:
            messagebox.showerror("Chave recusada", "O Redmine recusou a chave informada.", parent=self)
            return

        self.result = (url, api_key)
        self.destroy()

    def cancel(self):
        self.result = None
        self.destroy()

    def show(self):
        self.wait_window()
        return self.result


def get_redmine_config(root):
    """Retorna (url, api_key) válidos: os salvos em config.pkl ou novos pedidos ao usuário.
    Retorna None se o usuário cancelar."""
    message = None
    url, api_key = load_config()
    if url and api_key:
        try:
            if validate_api_key(url, api_key):
                return url, api_key
            message = "A chave salva foi recusada pelo Redmine.\nInforme uma nova chave de API."
        except Exception as e:
            # Sem rede: segue com a configuração salva, o app trata a falha depois
            print(f"Não foi possível validar a chave salva: {type(e).__name__}")
            return url, api_key

    result = ApiKeyDialog(root, url, api_key, message).show()
    if result is not None:
        save_config(*result)
    return result
