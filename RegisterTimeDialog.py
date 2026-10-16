import tkinter as tk
from tkinter import messagebox
from tkinter import ttk


class RegisterTimeDialog(tk.Toplevel):
    """Dialogo para revisar e confirmar o registro de horas."""

    def __init__(self, parent, registered_time, activities, task_id, task_title):
        super().__init__(parent)
        self.result = None
        self.activities = activities
        self.title(f"[{task_id}] - {task_title}")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        tk.Label(self, text="Tempo registrado (HH:MM:SS):").grid(
            row=0, column=0, padx=10, pady=(10, 4), sticky="w"
        )
        self.time_entry = tk.Entry(self, width=18)
        self.time_entry.insert(0, str(registered_time).split('.')[0])
        self.time_entry.grid(row=1, column=0, padx=10, sticky="ew")

        tk.Label(self, text="Atividade:").grid(
            row=2, column=0, padx=10, pady=(10, 4), sticky="w"
        )
        self.activity_combo = ttk.Combobox(self, state="readonly", width=39)
        self.activity_combo["values"] = [str(activity.name) for activity in activities]
        if activities:
            self.activity_combo.current(0)
        self.activity_combo.grid(row=3, column=0, padx=10, sticky="ew")

        tk.Label(self, text="Descrição:").grid(
            row=4, column=0, padx=10, pady=(10, 4), sticky="w"
        )
        self.description_entry = tk.Text(self, width=42, height=5)
        self.description_entry.grid(row=5, column=0, padx=10, sticky="ew")

        buttons = tk.Frame(self)
        buttons.grid(row=6, column=0, padx=10, pady=10, sticky="e")
        tk.Button(buttons, text="OK", command=self.confirm).pack(side="left", padx=4)
        tk.Button(buttons, text="Cancelar", command=self.cancel).pack(side="left")

        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.time_entry.focus_set()
        self._center_on_screen()

    def _center_on_screen(self):
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() - width) // 2
        y = (self.winfo_screenheight() - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")

    def confirm(self):
        try:
            hours, minutes, seconds = map(int, self.time_entry.get().strip().split(":"))
            if hours < 0 or not 0 <= minutes < 60 or not 0 <= seconds < 60:
                raise ValueError
        except ValueError:
            messagebox.showerror("Tempo inválido", "Informe o tempo no formato HH:MM:SS.", parent=self)
            return

        total_seconds = hours * 3600 + minutes * 60 + seconds
        if total_seconds <= 0:
            messagebox.showerror("Tempo inválido", "O tempo deve ser maior que zero.", parent=self)
            return
        if not self.activities:
            messagebox.showerror("Atividade indisponível", "Nenhuma atividade foi encontrada no Redmine.", parent=self)
            return

        self.result = {
            "seconds": total_seconds,
            "description": self.description_entry.get("1.0", "end-1c").strip(),
            "activity_id": self.activities[self.activity_combo.current()].id,
        }
        self.destroy()

    def cancel(self):
        self.result = None
        self.destroy()

    def show(self):
        self.wait_window()
        return self.result
